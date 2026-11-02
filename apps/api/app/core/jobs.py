"""Run background jobs (ingest, apply recipe, models) outside the API process.

On a 512 MB instance one job on a large file needs ~250 MB on top of the API. Run inside
the API process, that memory stays fragmented after the job and the next job stacks on top
until the instance is killed — and every request in flight gets a 502 with no CORS headers.

``JOB_RUNNER=fork`` (Docker image): at startup, while the API is still single-threaded, a
small "zygote" process is forked. For each job the zygote forks a fresh child that runs it and
exits, so all of the job's memory goes back to the OS and libraries are shared copy-on-write.
If a job still exceeds the limit, the kernel kills that child (the largest process) — the API
keeps serving and the job is marked failed with ``job.out_of_memory``. Jobs run one at a time.

``JOB_RUNNER=inline`` (default; tests and local development): the job runs in the calling
thread, as before.
"""

from __future__ import annotations

import importlib
import logging
import os
import signal
import socket
import threading
import uuid
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)


def _resolve(target: str) -> Callable[[uuid.UUID], Any]:
    module, _, name = target.partition(":")
    return getattr(importlib.import_module(module), name)


def _run_child(target: str, job_id: str) -> None:
    """Grandchild: fresh DB connections, run the job, exit without touching the parent's state."""
    code = 0
    try:
        from app.db.session import engine

        engine.dispose(close=False)  # never reuse the parent's pooled connections
        _resolve(target)(uuid.UUID(job_id))
    except BaseException:  # noqa: BLE001 — reported to the parent through the exit code
        log.exception("job %s (%s) crashed", job_id, target)
        code = 1
    finally:
        logging.shutdown()
        os._exit(code)


def _zygote_loop(sock: socket.socket) -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # Ctrl-C / shutdown goes to the API
    stream = sock.makefile("rwb", buffering=0)
    for line in stream:  # one request per line: "<module:function> <job uuid>"
        target, job_id = line.decode().split()
        pid = os.fork()
        if pid == 0:
            stream.close()
            sock.close()
            _run_child(target, job_id)
        _, status = os.waitpid(pid, 0)
        stream.write(f"{status}\n".encode())
    os._exit(0)  # the API closed the socket


class _ForkRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stream: Any = None
        self._pid: int | None = None

    def start(self) -> None:
        """Call once, before the API starts threads (forking a threaded process is unsafe)."""
        ours, theirs = socket.socketpair()
        pid = os.fork()
        if pid == 0:
            ours.close()
            try:
                _zygote_loop(theirs)
            finally:
                os._exit(0)
        theirs.close()
        self._pid, self._stream = pid, ours.makefile("rwb", buffering=0)
        log.info("job runner: zygote process %s", pid)

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self._stream = None

    def run(self, target: str, job_id: uuid.UUID) -> None:
        with self._lock:  # one job at a time keeps the peak predictable
            if self._stream is None:
                log.warning("job runner not started; running %s inline", target)
                _resolve(target)(job_id)
                return
            try:
                self._stream.write(f"{target} {job_id}\n".encode())
                reply = self._stream.readline()
            except OSError:
                reply = b""
            if not reply:  # the zygote itself is gone: run here rather than lose the job
                log.error("job runner zygote %s is gone; running %s inline", self._pid, target)
                self._stream = None
                _resolve(target)(job_id)
                return
            status = int(reply)
        if os.WIFSIGNALED(status):
            sig = os.WTERMSIG(status)
            code = "job.out_of_memory" if sig == signal.SIGKILL else "job.crashed"
            log.error("job %s (%s) killed by signal %s", job_id, target, sig)
            mark_failed(job_id, code)
        elif os.WEXITSTATUS(status) != 0:
            mark_failed(job_id, "job.crashed")


def mark_failed(job_id: uuid.UUID, code: str) -> None:
    """Record a failure the job could not record itself (it was killed)."""
    from app.db.models import Dataset, DatasetStatus, Job, JobStatus, JobType
    from app.db.session import SessionLocal
    from app.services.datasets import now

    with SessionLocal() as session:
        job = session.get(Job, job_id)
        if job is None or job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
            return
        job.status, job.error_code, job.finished_at = JobStatus.FAILED, code, now()
        if job.type == JobType.INGEST and job.dataset_id:
            ds = session.get(Dataset, job.dataset_id)
            if ds is not None:
                ds.status = DatasetStatus.FAILED
        session.commit()


_fork_runner = _ForkRunner()
_mode = "inline"


def start(mode: str) -> None:
    global _mode
    _mode = mode
    if mode == "fork":
        _fork_runner.start()


def stop() -> None:
    if _mode == "fork":
        _fork_runner.stop()


def run(target: str, job_id: uuid.UUID) -> None:
    """Run ``target`` ("package.module:function", taking the job id) for ``job_id``."""
    if _mode == "fork":
        _fork_runner.run(target, job_id)
    else:
        _resolve(target)(job_id)

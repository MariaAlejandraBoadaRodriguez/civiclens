"""Background job runner (app/core/jobs.py): phases, the fork runner and OOM-killed jobs."""

import os
import subprocess
import sys
import textwrap
import uuid
from pathlib import Path

from app.core import jobs
from app.db.models import Job, JobStatus, JobType
from app.db.session import SessionLocal
from tests.job_targets import MARKERS

API_DIR = Path(__file__).resolve().parent.parent


def _job() -> uuid.UUID:
    with SessionLocal() as session:
        job = Job(type=JobType.MODEL_RUN, status=JobStatus.RUNNING, input_json={})
        session.add(job)
        session.commit()
        return job.id


def _status(job_id: uuid.UUID) -> tuple[str, str | None]:
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        return job.status.value, job.error_code


def _run_forked(*runs: tuple[tuple[str, ...], uuid.UUID]) -> None:
    """Start the fork runner in a fresh, single-threaded interpreter (as uvicorn does at
    startup) and run the given phases there."""
    calls = "\n".join(
        f"jobs.run({phases!r}, uuid.UUID({str(job_id)!r}))" for phases, job_id in runs
    )
    code = (
        textwrap.dedent(
            """
        import uuid
        from app.core import jobs
        jobs.start("fork")
        """
        )
        + calls
        + "\njobs.stop()\n"
    )
    subprocess.run([sys.executable, "-c", code], cwd=API_DIR, env=os.environ, check=True)


def test_inline_runner_runs_every_phase_in_order() -> None:
    job_id = _job()
    jobs.run(("tests.job_targets:write_marker", "tests.job_targets:write_marker"), job_id)
    assert len(list(MARKERS.glob(f"{job_id}.*"))) == 1  # same process both times
    assert (MARKERS / f"{job_id}.{os.getpid()}").exists()


def test_fork_runner_runs_each_phase_in_its_own_process() -> None:
    job_id = _job()
    _run_forked((("tests.job_targets:write_marker", "tests.job_targets:write_marker"), job_id))
    pids = {p.suffix for p in MARKERS.glob(f"{job_id}.*")}
    assert len(pids) == 2 and f".{os.getpid()}" not in pids


def test_job_killed_for_memory_is_marked_failed_and_the_runner_keeps_going() -> None:
    killed, crashed, after = _job(), _job(), _job()
    _run_forked(
        (("tests.job_targets:killed",), killed),
        (("tests.job_targets:crash",), crashed),
        (("tests.job_targets:write_marker",), after),
    )
    assert _status(killed) == ("failed", "job.out_of_memory")
    assert _status(crashed) == ("failed", "job.crashed")
    assert list(MARKERS.glob(f"{after}.*")), "the next job still ran"


def test_a_phase_is_skipped_after_an_earlier_phase_failed() -> None:
    job_id = _job()
    with SessionLocal() as session:
        session.get(Job, job_id).status = JobStatus.FAILED
        session.commit()
    ran = []
    jobs.run_phase(job_id, "job.crashed", lambda *_: ran.append(1), finish=True)
    assert not ran and _status(job_id)[0] == "failed"


def test_errors_are_localized() -> None:
    from app.i18n.loader import Translator

    for code in ("job.out_of_memory", "job.crashed"):
        en, es = Translator("en")(f"errors.{code}.title"), Translator("es")(f"errors.{code}.title")
        assert en != es and not en.startswith("errors.")

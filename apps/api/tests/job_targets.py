"""Job functions used by tests/test_jobs.py (imported by name, like the real job phases)."""

import os
import signal
import uuid
from pathlib import Path

MARKERS = Path(os.environ["DATA_DIR"]) / "job-markers"


def write_marker(job_id: uuid.UUID) -> None:
    MARKERS.mkdir(parents=True, exist_ok=True)
    (MARKERS / f"{job_id}.{os.getpid()}").write_text("done")


def killed(job_id: uuid.UUID) -> None:
    """What the kernel's OOM killer does to a job that exceeds the memory limit."""
    os.kill(os.getpid(), signal.SIGKILL)


def crash(job_id: uuid.UUID) -> None:
    raise RuntimeError("boom")

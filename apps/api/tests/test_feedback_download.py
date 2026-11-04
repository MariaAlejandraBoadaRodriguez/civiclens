"""PR "feedback + clean download": job phases with progress, and downloading the cleaned data."""

import io
import uuid

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core import jobs
from app.db.models import Job
from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)
CSV = (
    "region;product;units;price;sold_on\n"
    + "\n".join(
        f"R{i % 3};P{i % 5};{i};{i * 1.5:.2f};2024-0{i % 9 + 1}-1{i % 9}" for i in range(60)
    )
    + "\nR1;P1;1;1.50;2024-01-11\nR1;P1;1;1.50;2024-01-11\n"  # a duplicate
).encode()


def _upload() -> dict:
    r = client.post("/api/v1/datasets", files={"file": ("sales.csv", CSV, "text/csv")})
    assert r.status_code == 202, r.text
    return r.json()


def test_ingest_job_reports_every_phase_and_ends_at_100(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, int | None]] = []
    original = jobs.report_progress

    def spy(job_id: uuid.UUID, phase: str) -> None:
        original(job_id, phase)
        with SessionLocal() as session:
            job = session.get(Job, job_id)
            seen.append((job.phase, job.progress))

    for module in ("app.services.datasets", "app.core.jobs"):
        monkeypatch.setattr(f"{module}.report_progress", spy)
    body = _upload()
    job = client.get(f"/api/v1/jobs/{body['job']['id']}", headers={"Accept-Language": "es"}).json()
    assert job["status"] == "succeeded" and job["progress"] == 100 and job["phase"] == "done"
    assert job["phase_label"] == "Terminado"
    phases = [p for p, _ in seen]
    assert (
        phases[:1] == ["profiling"] and "detecting_issues" in phases and "building_model" in phases
    )
    progress = [p for _, p in seen]
    assert progress == sorted(progress) and all(0 < p < 100 for p in progress)


def test_progress_labels_are_localized() -> None:
    with SessionLocal() as session:
        job = Job(type="ingest", status="running", phase="profiling", progress=30)
        session.add(job)
        session.commit()
        job_id = job.id
    en = client.get(f"/api/v1/jobs/{job_id}").json()
    es = client.get(f"/api/v1/jobs/{job_id}", headers={"Accept-Language": "es"}).json()
    assert en["progress"] == es["progress"] == 30 and en["phase"] == es["phase"] == "profiling"
    assert en["phase_label"] == "Profiling the columns"
    assert es["phase_label"] == "Perfilando las columnas"


def test_apply_job_reports_its_phases() -> None:
    dataset = _upload()["dataset"]["id"]
    steps = [{"op": "drop_duplicates", "args": {}}]
    r = client.post(
        f"/api/v1/datasets/{dataset}/recipes/apply", json={"recipe": {"name": "d", "steps": steps}}
    )
    job = client.get(r.headers["location"]).json()
    assert job["status"] == "succeeded" and job["progress"] == 100
    assert job["result"]["rows_after"] == job["result"]["rows_before"] - 1


@pytest.mark.parametrize("fmt", ["csv", "parquet"])
def test_download_cleaned_data_follows_the_applied_recipe(fmt: str) -> None:
    dataset = _upload()["dataset"]["id"]
    before = client.get(f"/api/v1/datasets/{dataset}/download?format={fmt}")
    assert before.status_code == 200 and before.headers["x-civiclens-origin"] == "recommended"
    assert "sales-recommended" in before.headers["content-disposition"]
    steps = [{"op": "drop_duplicates", "args": {}}]
    r = client.post(
        f"/api/v1/datasets/{dataset}/recipes/apply", json={"recipe": {"name": "d", "steps": steps}}
    )
    assert client.get(r.headers["location"]).json()["status"] == "succeeded"
    after = client.get(f"/api/v1/datasets/{dataset}/download?format={fmt}")
    assert after.headers["x-civiclens-origin"] == "clean"
    assert "sales-cleaned" in after.headers["content-disposition"]
    read = pd.read_csv if fmt == "csv" else pd.read_parquet
    frame = read(io.BytesIO(after.content))
    assert len(frame) == 61  # 62 rows minus the duplicate
    assert {"region", "product", "units"} <= set(frame.columns)


def test_download_errors() -> None:
    assert client.get("/api/v1/datasets/nope/download").status_code == 404
    dataset = _upload()["dataset"]["id"]
    assert client.get(f"/api/v1/datasets/{dataset}/download?format=xlsx").status_code == 422

"""/api/v1/datasets + /api/v1/jobs end to end (SQLite + temp data dir, see conftest)."""

import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.seed.registry import SEEDS
from app.main import app

client = TestClient(app)


@pytest.mark.parametrize("slug", sorted(SEEDS))
def test_seed_ingests_and_profiles(slug: str) -> None:
    """DoD 5a: all three seed files ingest (CSV, XLSX, JSON demo versions)."""
    r = client.get(f"/api/v1/datasets/{slug}/profile")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dataset"]["slug"] == slug
    assert body["read"]["format"] == SEEDS[slug].format
    assert body["rows"] >= 10_000
    assert 0 <= body["quality"]["score"] <= 100
    mapped = {c["canonical_field"] for c in body["columns"]}
    assert {
        "signed_date",
        "amount_original",
        "supplier_name",
        "entity_name",
        "contract_id",
    } <= mapped
    assert body["data_lang_label"] in {"es", "fr", "mixed"}
    if slug == "secop_co":
        checks = [c["source_header"] for c in body["columns"] if c["needs_check"]]
        assert checks == ["Modalidad de Contratación (SECOP)"]
        assert {p["kind"] for p in body["pii"]} >= {"email", "phone"}


def test_seed_lookup_by_id_and_listing() -> None:
    listing = client.get("/api/v1/datasets").json()["items"]
    assert [d["slug"] for d in listing[:3]] == list(SEEDS)
    seed_id = listing[0]["id"]
    assert client.get(f"/api/v1/datasets/{seed_id}").json()["slug"] == "secop_co"


def test_same_request_in_en_and_es_has_identical_machine_fields() -> None:
    en = client.get("/api/v1/datasets/secop_co/profile", headers={"Accept-Language": "en"})
    es = client.get(
        "/api/v1/datasets/secop_co/profile", headers={"Accept-Language": "es-CO,es;q=0.9"}
    )
    assert en.headers["content-language"] == "en" and es.headers["content-language"] == "es"
    a, b = en.json(), es.json()
    assert a["quality"] == b["quality"]
    assert [c["canonical_field"] for c in a["columns"]] == [
        c["canonical_field"] for c in b["columns"]
    ]
    labels = {
        c["canonical_field"]: (c["label"], d["label"])
        for c, d in zip(a["columns"], b["columns"], strict=True)
    }
    assert labels["signed_date"] == ("Signed date", "Fecha de firma")
    assert a["dataset"]["name"] == "Colombia · Public contracts"
    assert b["dataset"]["name"] == "Colombia · Contratos públicos"
    # data values are never translated
    assert a["columns"][0]["top_values"] == b["columns"][0]["top_values"]


def test_unsupported_language_falls_back_to_english() -> None:
    r = client.get("/api/v1/datasets/nope", headers={"Accept-Language": "fr-CA"})
    assert r.headers["content-language"] == "en"


@pytest.mark.parametrize(
    ("lang", "title"), [("en", "Dataset not found"), ("es", "Conjunto de datos no encontrado")]
)
def test_not_found_is_localized_problem(lang: str, title: str) -> None:
    r = client.get("/api/v1/datasets/does-not-exist", headers={"Accept-Language": lang})
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["code"] == "dataset.not_found" and body["title"] == title
    assert body["params"] == {"dataset_id": "does-not-exist"}


def _upload(name: str, data: bytes, lang: str = "en"):
    return client.post(
        "/api/v1/datasets", files={"file": (name, data)}, headers={"Accept-Language": lang}
    )


def _csv() -> bytes:
    rows = "\n".join(f"C-{i};12/0{1 + i % 9}/2024;{i}.234,56;ACME S.A.S." for i in range(40))
    return ("id_contrato;fecha_de_firma;valor_del_contrato;proveedor\n" + rows).encode("cp1252")


def _xlsx() -> bytes:
    buf = io.BytesIO()
    pd.DataFrame({"Contract date": ["2024-01-02"] * 5, "Contract value": ["10.5"] * 5}).to_excel(
        buf, index=False
    )
    return buf.getvalue()


@pytest.mark.parametrize(
    ("name", "data", "fmt"),
    [
        ("contracts.csv", _csv(), "csv"),
        ("contracts.xlsx", _xlsx(), "xlsx"),
        (
            "contracts.json",
            b'{"contrats": [{"date_signature": "2024-01-02", "contrat_montant": "1 234,5"}]}',
            "json",
        ),
    ],
)
def test_upload_runs_ingest_job(name: str, data: bytes, fmt: str) -> None:
    r = _upload(name, data)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["dataset"]["format"] == fmt and body["dataset"]["expires_at"]
    assert r.headers["location"] == f"/api/v1/jobs/{body['job']['id']}"
    job = client.get(r.headers["location"]).json()  # TestClient ran the background task
    assert job["status"] == "succeeded", job
    profile = client.get(f"/api/v1/datasets/{body['dataset']['id']}/profile").json()
    assert profile["read"]["format"] == fmt
    assert profile["dataset"]["status"] == "profiled"


def test_upload_rejects_unsupported_type_in_spanish() -> None:
    r = _upload("macro.xlsm", b"PK\x03\x04xl/", lang="es")
    assert r.status_code == 415
    assert r.json()["code"] == "ingest.unsupported_format"
    assert r.json()["title"] == "Tipo de archivo no admitido"


def test_upload_rejects_empty_file() -> None:
    assert _upload("empty.csv", b"  ").json()["code"] == "ingest.empty_file"


def test_upload_rejects_too_large(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "upload_max_mb", 0)
    r = _upload("big.csv", b"a,b\n1,2\n")
    assert r.status_code == 413
    assert r.json()["params"] == {"limit_mb": 0}


def test_broken_file_fails_job_with_stable_code() -> None:
    r = _upload("broken.json", b'{"a": [1, 2')
    job = client.get(r.headers["location"], headers={"Accept-Language": "es"}).json()
    assert job["status"] == "failed"
    assert job["error"]["code"] == "ingest.unreadable"
    assert job["error"]["title"] == "No pudimos leer este archivo"


def test_unknown_job_is_404() -> None:
    assert client.get("/api/v1/jobs/not-a-uuid").json()["code"] == "job.not_found"


def test_profile_matches_openapi_contract() -> None:
    """Required fields of the Profile and ColumnProfile schemas are present (openapi.yaml)."""
    from pathlib import Path

    import yaml

    spec = yaml.safe_load((Path(__file__).resolve().parents[3] / "openapi.yaml").read_text())
    schemas = spec["components"]["schemas"]
    body = client.get("/api/v1/datasets/contracts_qc/profile").json()
    assert set(schemas["Profile"]["required"]) <= set(body)
    assert set(schemas["Dataset"]["required"]) <= set(body["dataset"])
    for column in body["columns"]:
        assert set(schemas["ColumnProfile"]["required"]) <= set(column)

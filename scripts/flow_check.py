"""Run the CivicLens user flows against a live API and fail on any server error.

Standard library only, so it runs on a bare CI runner or a laptop.

Modes:
  full   Every flow on the three seeds: upload + ingest of the dirty demo file, profile,
         issues, a recipe preview for every option of every issue, apply the recommended
         recipe (job), star schema, the 12 guided queries, KPIs, both models (jobs), the
         executive report (HTML EN + ES, PDF), the BI export and the dashboard (one dataset and
         all three, every period). With --fixtures, also every acceptance fixture (any kind of
         table): upload, ingest, apply the recommended recipe, the table `data`, every generated
         question (each must return rows), KPIs, the domain step, the four generic models (target
         model, anomalies, segments, forecast), the dashboard overview with its findings, a custom
         chart, the report (HTML EN + ES, PDF) and BI export; procurement-only views must answer
         409, never 5xx.
         Used by CI against the Docker image limited to 512 MB.
  smoke  /health and one recipe preview per seed. Used after each production deploy.

Any 5xx, network error (e.g. the instance restarted), failed job or missing CORS header
fails the run. Exit code 0 = all good.

Usage:
  python scripts/flow_check.py --base http://127.0.0.1:8000 --mode full --files data/demo
  python scripts/flow_check.py --base http://127.0.0.1:8000 --mode full --fixtures data/fixtures
  python scripts/flow_check.py --base https://civiclens-api.onrender.com --mode smoke \\
      --origin https://civiclens-eosin.vercel.app
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

SEEDS = ("secop_co", "contracts_ca", "contracts_qc")


class FlowError(Exception):
    pass


class Client:
    def __init__(self, base: str, origin: str | None, timeout: float, lang: str) -> None:
        self.base, self.origin, self.timeout, self.lang = base.rstrip("/"), origin, timeout, lang
        self.calls = 0

    def request(self, method: str, path: str, body: Any = None, *, raw: bytes | None = None,
                content_type: str = "application/json", ok: tuple[int, ...] = (200,)) -> Any:
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        headers = {"Accept-Language": self.lang, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = content_type
        if self.origin:
            headers["Origin"] = self.origin
        for attempt in range(4):
            req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
            self.calls += 1
            started = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as res:  # noqa: S310
                    status, payload, hdrs = res.status, res.read(), res.headers
            except urllib.error.HTTPError as exc:
                status, payload, hdrs = exc.code, exc.read(), exc.headers
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                raise FlowError(f"{method} {path}: no answer ({exc}) — did the instance restart?") from exc
            if status != 429 or 429 in ok or attempt == 3:
                break
            # The API's per-minute rate limit (heavy routes): wait as told, like a real client.
            wait = min(float(hdrs.get("retry-after") or 30), 65)
            log(f"    rate limited on {method} {path}: waiting {wait:.0f} s")
            time.sleep(wait)
        ms = int((time.perf_counter() - started) * 1000)
        if status >= 500:
            raise FlowError(f"{method} {path}: HTTP {status} after {ms} ms: {payload[:300]!r}")
        if status not in ok:
            raise FlowError(f"{method} {path}: HTTP {status}, expected {ok}: {payload[:300]!r}")
        if self.origin and hdrs.get("access-control-allow-origin") != self.origin:
            raise FlowError(f"{method} {path}: no CORS header for {self.origin}")
        return json.loads(payload) if payload and payload[:1] in (b"{", b"[") else payload

    def get(self, path: str, **kw: Any) -> Any:
        return self.request("GET", path, **kw)

    def post(self, path: str, body: Any = None, **kw: Any) -> Any:
        return self.request("POST", path, body, **kw)

    def wait_job(self, job: dict[str, Any], what: str, limit_s: float = 300) -> dict[str, Any]:
        deadline = time.time() + limit_s
        while time.time() < deadline:
            state = self.get(f"/api/v1/jobs/{job['id']}")
            if state["status"] == "succeeded":
                return state
            if state["status"] == "failed":
                raise FlowError(f"{what}: job failed: {state.get('error')}")
            time.sleep(1)
        raise FlowError(f"{what}: job still running after {limit_s:.0f} s")


def log(msg: str) -> None:
    print(msg, flush=True)


def recommended(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [s for i in issues for o in i["options"] if o["recommended"] for s in o["steps"]]


def previews(c: Client, slug: str, data: dict[str, Any], every_option: bool) -> int:
    """What the Cleaning Studio sends: the recipe decided so far + the option being looked at."""
    decided: list[dict[str, Any]] = []
    sent = 0
    for issue in data["issues"]:
        options = issue["options"] if every_option else issue["options"][:1]
        for option in options:
            c.post("/api/v1/recipes/preview",
                   {"steps": decided + option["steps"], "columns": data["columns"], "name": slug})
            sent += 1
        best = next((o for o in issue["options"] if o["recommended"]), issue["options"][0])
        decided += best["steps"]
        if not every_option:
            break
    return sent


def upload(c: Client, path: Path) -> str:
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"{path.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode()
    body += path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    accepted = c.post("/api/v1/datasets", raw=body, ok=(202,),
                      content_type=f"multipart/form-data; boundary={boundary}")
    c.wait_job(accepted["job"], f"ingest {path.name}")
    return accepted["dataset"]["id"]


def full(c: Client, files: Path | None) -> None:
    # Demo files written by scripts/make_dirty.py; manifest.json names each seed's file.
    manifest = json.loads((files / "manifest.json").read_text()) if files is not None else {}
    for slug in SEEDS:
        t0 = time.perf_counter()
        if files is not None:
            uploaded = upload(c, files / manifest[slug]["file"])
            c.get(f"/api/v1/datasets/{uploaded}/profile")
            c.get(f"/api/v1/datasets/{uploaded}/issues")
            log(f"  {slug}: upload + ingest + issues OK ({uploaded})")
        c.get(f"/api/v1/datasets/{slug}/profile")
        data = c.get(f"/api/v1/datasets/{slug}/issues")
        n = previews(c, slug, data, every_option=True)
        log(f"  {slug}: {len(data['issues'])} issues, {n} recipe previews OK")
        job = c.post(f"/api/v1/datasets/{slug}/recipes/apply",
                     {"recipe": {"name": f"ci-{slug}", "steps": recommended(data["issues"])}},
                     ok=(202,))
        c.wait_job(job, f"apply recipe {slug}")
        c.get(f"/api/v1/datasets/{slug}/issues")
        log(f"  {slug}: recommended recipe applied")
        c.get(f"/api/v1/datasets/{slug}/schema")
        guided = c.get("/api/v1/guided-queries")["items"]
        for q in guided:
            c.post("/api/v1/query", {"dataset_id": slug, "sql": q["sql"]})
        c.get(f"/api/v1/kpis/{slug}")
        log(f"  {slug}: star schema, {len(guided)} guided queries, KPIs OK")
        for model in ("red_flags", "forecast"):
            job = c.post(f"/api/v1/models/{model}/run", {"dataset_id": slug}, ok=(202,))
            c.wait_job(job, f"{model} {slug}")
            c.get(f"/api/v1/models/{model}/latest?dataset_id={slug}")
        log(f"  {slug}: red flags + forecast OK")
        for lang in ("en", "es"):  # executive report, in each UI language
            html = c.get(f"/api/v1/reports/{slug}?lang={lang}")
            if f'<html lang="{lang}">'.encode() not in html:
                raise FlowError(f"report {slug}: not rendered in {lang}")
        pdf = c.get(f"/api/v1/reports/{slug}?lang=es&format=pdf")
        if not pdf.startswith(b"%PDF"):
            raise FlowError(f"report {slug}: PDF expected")
        for fmt in ("csv", "parquet"):
            if not c.get(f"/api/v1/datasets/{slug}/export?format={fmt}").startswith(b"PK"):
                raise FlowError(f"export {slug}: zip expected")
        for period in ("all", "12m", "fy"):
            c.get(f"/api/v1/dashboard?dataset_id={slug}&period={period}")
        log(f"  {slug}: report EN + ES + PDF, BI export, dashboard OK "
            f"({time.perf_counter() - t0:.0f} s)")
    every = "&".join(f"dataset_id={s}" for s in SEEDS)
    for period in ("all", "12m", "fy"):
        c.get(f"/api/v1/dashboard?{every}&period={period}&category=services")
    log("  dashboard across the three jurisdictions OK")


FIXTURE_SUFFIXES = (".csv", ".xlsx", ".json")


def any_dataset(c: Client, folder: Path) -> None:
    """Every stage on files that are not procurement data (owner requirement: any table)."""
    for path in sorted(p for p in folder.iterdir() if p.suffix in FIXTURE_SUFFIXES):
        t0 = time.perf_counter()
        ds = upload(c, path)
        c.get(f"/api/v1/datasets/{ds}/profile")
        data = c.get(f"/api/v1/datasets/{ds}/issues")
        previews(c, path.name, data, every_option=False)
        job = c.post(f"/api/v1/datasets/{ds}/recipes/apply",
                     {"recipe": {"name": f"ci-{path.stem}", "steps": recommended(data["issues"])}},
                     ok=(202,))
        c.wait_job(job, f"apply recipe {path.name}")
        schema = c.get(f"/api/v1/datasets/{ds}/schema")
        if not schema["data_columns"] or schema["tables"][0]["name"] != "data":
            raise FlowError(f"{path.name}: no table data")
        guided = c.get(f"/api/v1/guided-queries?dataset_id={ds}")["items"]
        if len(guided) < 5:
            raise FlowError(f"{path.name}: only {len(guided)} generated questions")
        for q in guided:
            if not c.post("/api/v1/query", {"dataset_id": ds, "sql": q["sql"]})["rows"]:
                raise FlowError(f"{path.name}: question {q['query_id']} returned no rows")
        kpis = c.get(f"/api/v1/kpis/{ds}")["items"]
        if len(kpis) < 5 or any(k["value"] is None for k in kpis):
            raise FlowError(f"{path.name}: KPIs missing or empty")
        domain = c.get(f"/api/v1/datasets/{ds}/domain")
        verdicts = []
        for model in ("target_model", "anomalies", "segments", "forecast"):
            job = c.post(f"/api/v1/models/{model}/run", {"dataset_id": ds}, ok=(202,))
            c.wait_job(job, f"{model} {path.name}")
            result = c.get(f"/api/v1/models/{model}/latest?dataset_id={ds}")
            if not result["card"].get("verdict") and result.get("status") != "ok":
                raise FlowError(f"{path.name}: {model} gave no result and no explanation")
            verdicts.append(f"{model}={result.get('status')}")
        if not c.get(f"/api/v1/datasets/{ds}/export?format=parquet").startswith(b"PK"):
            raise FlowError(f"export {path.name}: zip expected")
        overview = c.get(f"/api/v1/datasets/{ds}/overview")
        if len(overview["sections"]) < 2 or not all(x["finding"] for x in overview["sections"]):
            raise FlowError(f"{path.name}: dashboard overview without findings")
        dim = overview["dimensions"][0]["name"]
        c.post(f"/api/v1/datasets/{ds}/chart", {"dimension": dim})
        for lang in ("en", "es"):
            if f'<html lang="{lang}">'.encode() not in c.get(f"/api/v1/reports/{ds}?lang={lang}"):
                raise FlowError(f"report {path.name}: not rendered in {lang}")
        if not c.get(f"/api/v1/reports/{ds}?lang=es&format=pdf").startswith(b"%PDF"):
            raise FlowError(f"report {path.name}: PDF expected")
        if domain["pack"] != "government":  # the procurement dashboard: a clear 409
            c.get(f"/api/v1/dashboard?dataset_id={ds}", ok=(409,))
            c.post("/api/v1/models/red_flags/run", {"dataset_id": ds}, ok=(409,))
        log(f"  {path.name}: {len(schema['data_columns'])} columns, {len(guided)} questions, "
            f"{len(kpis)} KPIs, domain {domain['pack']}, {' '.join(verdicts)} "
            f"({time.perf_counter() - t0:.0f} s)")


def smoke(c: Client) -> None:
    for slug in SEEDS:
        data = c.get(f"/api/v1/datasets/{slug}/issues")
        previews(c, slug, data, every_option=False)
        log(f"  {slug}: issues + recipe preview OK")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--base", required=True, help="API base URL")
    p.add_argument("--mode", choices=("full", "smoke"), default="full")
    p.add_argument("--files", type=Path, help="Folder with the dirty demo files (full mode)")
    p.add_argument("--fixtures", type=Path,
                   help="Folder of acceptance fixtures (any kind of table) to run end to end")
    p.add_argument("--origin", help="Web origin whose CORS header every answer must carry")
    p.add_argument("--lang", default="en")
    p.add_argument("--wait", type=float, default=0, help="Seconds to wait for /health first")
    p.add_argument("--timeout", type=float, default=120)
    args = p.parse_args(argv)

    c = Client(args.base, args.origin, args.timeout, args.lang)
    deadline = time.time() + args.wait
    while True:
        try:
            health = c.get("/health")
            break
        except FlowError as exc:
            if time.time() >= deadline:
                log(f"FAIL /health: {exc}")
                return 1
            time.sleep(3)
    log(f"health OK: {health}")
    started = time.perf_counter()
    try:
        if args.mode == "smoke":
            smoke(c)
        elif args.fixtures is not None and args.files is None:
            any_dataset(c, args.fixtures)
        else:
            full(c, args.files)
            if args.fixtures is not None:
                any_dataset(c, args.fixtures)
    except FlowError as exc:
        log(f"FAIL after {c.calls} calls: {exc}")
        return 1
    log(f"OK: {args.mode} flow, {c.calls} calls in {time.perf_counter() - started:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

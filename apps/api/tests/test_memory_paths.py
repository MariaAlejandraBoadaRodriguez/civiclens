"""The memory-lean paths return exactly what the straightforward pandas code returns."""

import hashlib
import io
import random

import numpy as np
import pandas as pd
import pytest

from app.core.cleaning.ops import duplicated_rows, output_hash
from app.core.ingest.locale_parse import normalize_token
from app.core.ingest.reader import _from_frame, _from_rows, read_any
from app.services import storage

VALUES = ["a", "A ", "b", None, "", "Á", "1", "1.0", "x y", "x  y"]


def _random_frame(rng: random.Random, rows: int, cols: int) -> pd.DataFrame:
    return pd.DataFrame(
        {f"c{j}": [rng.choice(VALUES) for _ in range(rows)] for j in range(cols)}, dtype=object
    )


@pytest.mark.parametrize("keep", ["first", "last", False])
def test_duplicated_rows_matches_pandas(keep: str | bool) -> None:
    rng = random.Random(7)
    for _ in range(150):
        df = _random_frame(rng, rng.randint(0, 40), rng.randint(1, 4))
        columns = list(df.columns)
        exact = df.astype(str).duplicated(keep=keep).to_numpy()
        assert (duplicated_rows(df, columns, near=False, keep=keep) == exact).all()
        normalized = df.astype(str).map(normalize_token)
        near = normalized.duplicated(keep=keep).to_numpy()
        assert (duplicated_rows(df, columns, near=True, keep=keep) == near).all()


def test_duplicated_rows_without_columns_marks_nothing() -> None:
    assert not duplicated_rows(pd.DataFrame(index=range(3)), [], near=False, keep="first").any()


def test_output_hash_is_the_hash_of_the_whole_csv() -> None:
    rng = random.Random(3)
    df = _random_frame(rng, 5000, 3).assign(n=np.arange(5000) / 7)
    text = df.to_csv(index=False, lineterminator="\n", date_format="%Y-%m-%dT%H:%M:%S", na_rep="")
    expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert output_hash(df) == output_hash(df, chunk_rows=777) == expected
    assert (
        output_hash(df.iloc[:0])
        == hashlib.sha256(df.iloc[:0].to_csv(index=False, lineterminator="\n").encode()).hexdigest()
    )


def test_read_parquet_matches_pandas(tmp_path) -> None:
    df = pd.DataFrame(
        {
            "name": ["Ana", None, "Ana", "Émile", "", "Ana"],
            "amount": ["1.234,5", "2", None, "2", "2", "x"],
            "flag": [True, False, None, True, True, False],
        }
    )
    path = tmp_path / "staged.parquet"
    storage.write_parquet(df[["name", "amount"]], path)
    df[["flag"]].assign(name=df["name"]).to_parquet(tmp_path / "mixed.parquet", index=False)
    for p in (path, tmp_path / "mixed.parquet"):
        expected = pd.read_parquet(p).astype(object)
        expected = expected.where(expected.notna(), None)
        got = storage.read_parquet(p)
        assert got.equals(expected) and list(got.columns) == list(expected.columns)
    shared = storage.read_parquet(path)["name"]
    assert shared[0] is shared[2]  # one object per distinct value


def test_from_frame_matches_from_rows() -> None:
    rng = random.Random(11)
    for _ in range(40):
        width = rng.randint(2, 5)
        title = [["Report 2024"] + [""] * (width - 1), [""] * width]
        header = [[f"Col {j}" for j in range(width)]]
        body = [
            [rng.choice(["", "1", "abc", "2,5"]) for _ in range(width)]
            for _ in range(rng.randint(0, 80))
        ]
        rows = (title if rng.random() < 0.5 else []) + header + body
        expected, idx = _from_rows([list(r) for r in rows])
        got, got_idx = _from_frame(pd.DataFrame(rows, dtype=object))
        assert got_idx == idx
        assert got.reset_index(drop=True).equals(expected.reset_index(drop=True))


def test_csv_reader_keeps_encoding_and_delimiter() -> None:
    text = "Título;Valor\n" + "".join(f"Entidad {i % 3};{i},5\n" for i in range(200))
    df, info = read_any(text.encode("cp1252"), "datos.csv")
    assert info.delimiter == ";" and df.shape == (200, 2)
    assert df.iloc[0, 0] == "Entidad 0" and df.iloc[5, 1] == "5,5"
    assert df.iloc[0, 0] is df.iloc[3, 0]  # values interned per column


def test_utf8_json_is_read_from_bytes() -> None:
    raw = '{"contrats": [{"fournisseur": "Société Énergie", "montant": "1 234,5"}]}'
    df, info = read_any(io.BytesIO(raw.encode()).getvalue(), "contrats.json")
    assert df.iloc[0]["fournisseur"] == "Société Énergie" and info.records_path == "contrats"

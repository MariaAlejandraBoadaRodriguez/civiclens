"""Data Quality Score (0–100) = mean of completeness, uniqueness, validity, consistency.

Equal weights: a reader can recompute the score from the four bars. Deterministic integers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class QualityScore:
    score: int
    completeness: int
    uniqueness: int
    validity: int
    consistency: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def _pct(x: float) -> int:
    return max(0, min(100, round(x * 100)))


def compute(
    completeness: float, uniqueness: float, validity: float, consistency: float
) -> QualityScore:
    """Each input is a 0–1 share (see ``profiler.profile_frame``):

    - completeness: non-null cells in canonical columns
    - uniqueness: 1 − max(exact duplicate rows, duplicate contract keys)
    - validity: rows whose canonical typed values all parse (dates, numbers, currency codes)
    - consistency: rows whose canonical values use the dominant notation / spelling
    """
    parts = [_pct(completeness), _pct(uniqueness), _pct(validity), _pct(consistency)]
    return QualityScore(round(sum(parts) / 4), *parts)

"""5.9 splits the labelled cohort in two, so the two parts must be a partition.

The section's whole argument is that a metric over the pooled cohort is
dominated by one part. That only follows if the parts are disjoint and cover
the cohort: a gap would drop patients from both tables silently, and an overlap
would double-count them into both. The boundary is inclusive below and
exclusive above, which is exactly the kind of thing an edit flips.

The cutoff itself is shared with 5.8 rather than restated, so it is checked
here against `growth.PANEL_SPLIT_YEARS` too.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports"))

from ppoc_eda.probes.growth import PANEL_SPLIT_YEARS
from ppoc_eda.probes.joint import PANEL_SPLIT_YEARS as JOINT_SPLIT

OUT = Path(__file__).resolve().parents[2] / "reports" / "ppoc-eda"

EARLY = "t-pre-heights-early"
LATE = "t-pre-heights-late"


def test_both_sections_cut_at_the_same_number() -> None:
    """5.9 imports the cutoff; a local copy would drift from 5.8 unnoticed."""
    assert JOINT_SPLIT is PANEL_SPLIT_YEARS


def _finding() -> dict | None:
    path = OUT / "findings.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return next((f for part in data["parts"] for f in part["findings"]
                 if f["id"] == "joint.label"), None)


def _table(f: dict, table_id: str) -> list[dict]:
    return next(t["rows"] for t in f["tables"] if t["id"] == table_id)


def test_the_two_parts_partition_the_labelled_cohort() -> None:
    f = _finding()
    if f is None:
        pytest.skip("report has not been built, or 5.9 is absent")
    v = f["values"]
    assert v["early_n"] + v["late_n"] == v["total"], (
        "the two strata do not cover the labelled cohort exactly"
    )
    assert abs(v["early_share"] + v["late_share"] - 100.0) < 1e-6


def test_each_part_table_sums_to_its_stratum() -> None:
    """The band tables are the strata, so their totals have to agree."""
    f = _finding()
    if f is None:
        pytest.skip("report has not been built, or 5.9 is absent")
    v = f["values"]
    for table_id, expected in ((EARLY, v["early_n"]), (LATE, v["late_n"])):
        rows = _table(f, table_id)
        assert rows, f"{table_id} is empty"
        assert sum(r["patients"] for r in rows) == expected, (
            f"{table_id} does not sum to its stratum count"
        )
        assert abs(sum(r["share"] for r in rows) - 100.0) < 0.05


def test_the_trajectory_finding_is_concentrated_in_the_later_part() -> None:
    """The section's conclusion, asserted rather than left to the prose.

    If this ever fails the split has stopped separating anything and the
    two-part structure is no longer earning its place.
    """
    f = _finding()
    if f is None:
        pytest.skip("report has not been built, or 5.9 is absent")
    v = f["values"]
    assert v["late_traj_share"] > v["early_traj_share"]
    assert v["traj_in_late"] > 50.0, (
        "most trajectory-bearing patients are no longer in the later stratum"
    )

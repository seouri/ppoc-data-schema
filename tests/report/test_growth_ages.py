"""5.8 publishes a distribution per tracked code, so it answers to two rules.

The small-cell rule reaches it twice: once for the patient counts, and once for
the four age statistics, which describe the same patients and must disappear
with them. The other rule is arithmetic — a min above a median, or a mean
outside the range, means the row's columns came from different populations,
which is what a mismatched panel or a stale column filter looks like.

The panel itself is checked here too. 5.7 and 5.8 read it from the augmented
layer's column names, and `dx_age_years` without a trailing underscore is the
panel-wide age rather than a code; picking it up would invent an ICD-10 code
named for the column.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports"))

from ppoc_eda.context import SUPPRESS_BELOW, Context
from ppoc_eda.probes.growth import PANEL_SPLIT_YEARS, tracked_codes

OUT = Path(__file__).resolve().parents[2] / "reports" / "ppoc-eda"

#: Row keys counting patients, and the four statistics describing those patients.
COUNT_KEYS = ("patients", "aged")
AGE_KEYS = ("min", "median", "mean", "max")


def _context(setup: str) -> Context:
    con = duckdb.connect(":memory:")
    con.execute(setup)
    return Context(con=con, bundle=Path("/nonexistent"))


def test_the_panel_is_read_from_the_code_columns_only() -> None:
    """`dx_age_years` is the panel-wide age; only the suffixed columns are codes."""
    ctx = _context(
        "CREATE TABLE patients_augmented AS SELECT 1 AS dx_age_years, "
        "2 AS dx_age_years_e10, 3 AS dx_age_years_q87_1, 4 AS visits_count")
    assert tracked_codes(ctx) == [
        ("dx_age_years_e10", "E10"), ("dx_age_years_q87_1", "Q87.1")]


BIRTH = "t-growth-ages-birth"
CHILDHOOD = "t-growth-ages-childhood"


def _finding() -> dict | None:
    path = OUT / "findings.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return next((f for part in data["parts"] for f in part["findings"]
                 if f["id"] == "growth.ages"), None)


def _rows() -> list[tuple[str, dict]]:
    path = OUT / "findings.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [(table["id"], row)
            for part in data["parts"] for f in part["findings"]
            if f["id"] == "growth.ages"
            for table in f.get("tables", []) for row in table["rows"]]


def test_no_row_carries_a_count_below_the_threshold() -> None:
    rows = _rows()
    if not rows:
        pytest.skip("report has not been built, or 5.8 is absent")
    assert len(rows) > 10, f"only {len(rows)} rows found; the section shrank"
    offenders = [(table, key, row[key]) for table, row in rows for key in COUNT_KEYS
                 if isinstance(row.get(key), int) and 0 < row[key] < SUPPRESS_BELOW]
    assert not offenders, f"counts below the suppression threshold: {offenders}"


def test_an_age_statistic_is_withheld_whenever_its_count_is() -> None:
    """The four statistics describe the patients `aged` counts, so they share its fate."""
    rows = _rows()
    if not rows:
        pytest.skip("report has not been built, or 5.8 is absent")
    offenders = [(table, key) for table, row in rows for key in AGE_KEYS
                 if row.get("aged") is None and row.get(key) is not None]
    assert not offenders, f"age statistics published without their count: {offenders}"


def test_every_row_is_internally_consistent() -> None:
    """min <= median <= max and min <= mean <= max, on every published row.

    No claim about mean against median: the skew runs both ways across this
    panel, so an assertion either way would be wrong on some code.
    """
    rows = _rows()
    if not rows:
        pytest.skip("report has not been built, or 5.8 is absent")
    checked = 0
    for table, row in rows:
        if any(row.get(k) is None for k in AGE_KEYS):
            continue
        lo, med, mean, hi = (row[k] for k in AGE_KEYS)
        assert lo <= med <= hi, f"{table}/{row['code']}: median {med} outside [{lo}, {hi}]"
        assert lo <= mean <= hi, f"{table}/{row['code']}: mean {mean} outside [{lo}, {hi}]"
        checked += 1
    assert checked > 10, f"only {checked} rows carried a full quartet"


def test_the_aged_count_never_exceeds_the_subtree_count() -> None:
    """An age is established for a subset of the patients carrying the code."""
    rows = _rows()
    if not rows:
        pytest.skip("report has not been built, or 5.8 is absent")
    offenders = [(row["code"], row["aged"], row["patients"]) for _, row in rows
                 if isinstance(row.get("aged"), int)
                 and isinstance(row.get("patients"), int)
                 and row["aged"] > row["patients"]]
    assert not offenders, f"more patients with an age than carrying the code: {offenders}"


def _panel(table_id: str) -> list[dict]:
    return [row for table, row in _rows() if table == table_id]


def test_the_two_panels_are_disjoint_and_ordered_by_median() -> None:
    """The split is the section's whole claim, so it is checked, not trusted.

    Disjoint and exhaustive against the split, and each panel ordered by the
    statistic that assigned it — a table ordered some other way makes the
    prose's "no code sits near the line" impossible to see.
    """
    if _finding() is None:
        pytest.skip("report has not been built, or 5.8 is absent")
    birth, childhood = _panel(BIRTH), _panel(CHILDHOOD)
    assert birth and childhood, "one of the two panels is empty"
    for row in birth:
        assert row["median"] < PANEL_SPLIT_YEARS, f"{row['code']} is in the wrong panel"
    for row in childhood:
        assert row["median"] >= PANEL_SPLIT_YEARS, f"{row['code']} is in the wrong panel"
    for panel, name in ((birth, BIRTH), (childhood, CHILDHOOD)):
        medians = [r["median"] for r in panel]
        assert medians == sorted(medians), f"{name} is not ordered by median"
    codes = [r["code"] for r in birth + childhood]
    assert len(codes) == len(set(codes)), "a code appears in both panels"


def test_the_published_band_around_the_split_is_empty() -> None:
    """5.8 claims any boundary inside the band gives these same two panels.

    That is only true if no code's median lies inside it, and the two published
    edges are the real ones. Both halves are asserted here because the claim is
    what justifies splitting the table at all.
    """
    f = _finding()
    if f is None:
        pytest.skip("report has not been built, or 5.8 is absent")
    lo, hi = f["values"]["band_lo"], f["values"]["band_hi"]
    assert lo == max(r["median"] for r in _panel(BIRTH))
    assert hi == min(r["median"] for r in _panel(CHILDHOOD))
    assert lo < PANEL_SPLIT_YEARS <= hi, "the split does not sit inside its own band"
    inside = [r["code"] for _, r in _rows()
              if r.get("median") is not None and lo < r["median"] < hi]
    assert not inside, f"codes sit inside the band the section calls empty: {inside}"

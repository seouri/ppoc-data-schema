"""The shortcut sections emit counts, so they answer to the small-cell rule.

`context.suppress` is the single place the rule lives, and 5.13 and 5.14 reach
it by two different routes: a screen whose support floor keeps every value well
above the threshold, and named cohorts and columns whose counts are suppressed
one at a time. Both routes are exercised here against an in-memory fixture, and
the built report is checked for any count that escaped them — including the ones
`findings.json` carries without displaying.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports"))

from ppoc_eda.context import SUPPRESS_BELOW, Context
from ppoc_eda.probes import shortcuts

OUT = Path(__file__).resolve().parents[2] / "reports" / "ppoc-eda"

#: Row keys that count records. Everything else a shortcut table carries is a
#: rate, a rank statistic, or a label, and none of those is a cell the rule is
#: about.
COUNT_KEYS = ("patients", "flagged")

SMALL = SUPPRESS_BELOW - 5
LARGE = SUPPRESS_BELOW + 2


def _context(setup: str) -> Context:
    con = duckdb.connect(":memory:")
    con.execute(setup)
    return Context(con=con, bundle=Path("/nonexistent"))


def _label_rows(n: int) -> str:
    values = ", ".join(f"('p{i}', {i % 2}, 0)" for i in range(n))
    return (f"CREATE TABLE {shortcuts.LABEL_TABLE} AS "
            f"SELECT * FROM (VALUES {values}) t(patient_id, dx, workup)")


def _numeric_rows(n: int) -> str:
    values = ", ".join(f"('p{i}', {i % 2}, {i}, 1)" for i in range(n))
    return (f"CREATE TABLE {shortcuts.NUMERIC_TABLE} AS SELECT * FROM (VALUES "
            f"{values}) t(patient_id, growth_dx_flag, value, long_record)")


def test_the_screen_floor_sits_above_the_suppression_threshold() -> None:
    """5.13's screened values need no suppression because of this inequality.

    Lower `SUPPORT` under the threshold and the screen starts emitting counts
    the rule forbids, with nothing in the screen itself to catch it.
    """
    assert shortcuts.SUPPORT >= SUPPRESS_BELOW


@pytest.mark.parametrize("n,expected", [(SMALL, None), (LARGE, LARGE)])
def test_a_named_cohort_suppresses_its_patient_count(n: int, expected: int | None) -> None:
    """5.13's named candidates are not screened, so each is suppressed itself."""
    ctx = _context(_label_rows(n))
    row = shortcuts._cohort(
        ctx, f"SELECT patient_id FROM {shortcuts.LABEL_TABLE}", 14.0, 0.5, "test")
    assert row["patients"] == expected


@pytest.mark.parametrize("n,expected", [(SMALL, None), (LARGE, LARGE)])
def test_a_numeric_column_suppresses_its_patient_count(n: int, expected: int | None) -> None:
    """5.14 scores whole columns, and reports how many patients backed each."""
    ctx = _context(_numeric_rows(n))
    row = shortcuts._score(ctx, "value", "`value`")
    assert row is not None and row["patients"] == expected


def test_the_built_report_carries_no_small_count_in_these_sections() -> None:
    """Including counts `findings.json` serializes without displaying them.

    A table row reaches the JSON whole, so a key that no column renders is
    published all the same. `flagged` is one: 5.13 keeps it to compute a share.
    """
    path = OUT / "findings.json"
    if not path.is_file():
        pytest.skip("report has not been built")
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = [(f["id"], table["id"], row)
            for part in data["parts"] for f in part["findings"]
            if f["id"].startswith("shortcuts.")
            for table in f.get("tables", []) for row in table["rows"]]
    # Without this the test passes when the sections are absent or renamed.
    assert len(rows) > 20, f"only {len(rows)} shortcut rows found; the ids changed"

    offenders = [
        (finding, table, key, row[key])
        for finding, table, row in rows for key in COUNT_KEYS
        if isinstance(row.get(key), int) and 0 < row[key] < SUPPRESS_BELOW
    ]
    assert not offenders, f"counts below the suppression threshold: {offenders}"

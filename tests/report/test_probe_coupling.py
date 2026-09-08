"""The shortcut audit borrows two definitions; these keep the borrowing real.

5.13 and 5.14 are only comparable with 5.10 because they screen against the
same index event. The coupling is a single import, which is exactly the kind of
thing a later edit dissolves by pasting the SQL where it is used. These tests
fail when that happens, rather than leaving two sections quietly measuring two
different things.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

PROBES = Path(__file__).resolve().parents[2] / "reports" / "ppoc_eda" / "probes"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports"))

from ppoc_eda.probes import joint, shortcuts

#: Every substring the workup index matches on, taken from the SQL itself so
#: that adding a pattern there is what drives these tests rather than a list
#: maintained beside it.
LIKE_PATTERN = re.compile(r"LIKE\s+'%([^']*)%'")


def _workup_patterns() -> set[str]:
    found = {p.strip().upper() for p in LIKE_PATTERN.findall(joint.WORKUP_INDEX)}
    # A rewrite that this regex cannot read would otherwise pass every test
    # below by matching nothing at all.
    assert len(found) >= 2, f"parsed {found} out of WORKUP_INDEX; the shape changed"
    return found


def test_shortcuts_imports_the_workup_index_rather_than_restating_it() -> None:
    """A pasted copy drifts the moment 5.10's definition is edited."""
    tree = ast.parse((PROBES / "shortcuts.py").read_text(encoding="utf-8"))
    imported = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "joint"
        and any(alias.name == "WORKUP_INDEX" for alias in node.names)
        for node in ast.walk(tree)
    )
    assert imported, "shortcuts.py no longer imports WORKUP_INDEX from joint.py"

    assigned = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "WORKUP_INDEX" for t in node.targets)
    ]
    assert not assigned, "shortcuts.py rebinds WORKUP_INDEX, shadowing 5.10's definition"


def test_the_two_modules_agree_on_the_index_at_runtime() -> None:
    assert shortcuts.WORKUP_INDEX == joint.WORKUP_INDEX


def test_every_value_inside_the_index_has_its_workup_lift_withheld() -> None:
    """A value that *is* the index scores the maximum by construction.

    5.13 and 5.14 withhold the workup column for those values instead of
    printing a number that measured nothing. The check is behavioural: each
    pattern the index matches on must make `_defines_index` true, so adding a
    marker to WORKUP_INDEX without adding it to INDEX_TERMS fails here.
    """
    for pattern in _workup_patterns():
        assert shortcuts._defines_index(f"a {pattern} b"), (
            f"WORKUP_INDEX matches {pattern!r} but INDEX_TERMS does not cover it, "
            "so its row would report the base rate's maximum as a measurement"
        )


def test_the_withholding_is_not_indiscriminate() -> None:
    """The guard above passes trivially if `_defines_index` always says yes."""
    assert not shortcuts._defines_index("Levothyroxine Sodium")
    assert not shortcuts._defines_index("Endocrinology")

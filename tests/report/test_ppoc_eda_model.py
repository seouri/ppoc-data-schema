"""Unit tests for the report's data model and chart primitives."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports"))

from ppoc_eda import charts
from ppoc_eda.context import Context
from ppoc_eda.findings import Finding, TemplateError


def test_template_resolves_from_values() -> None:
    f = Finding(id="t", part="1.1", title="t", values={"n": 1234})
    assert f.render("{n:,} rows") == "1,234 rows"


def test_template_rejects_an_unknown_name() -> None:
    f = Finding(id="t", part="1.1", title="t", values={"n": 1})
    with pytest.raises(TemplateError):
        f.render("{missing} rows")


def test_suppression_hides_small_cells_but_keeps_zero() -> None:
    assert Context.suppress(0) == 0
    assert Context.suppress(9) is None
    assert Context.suppress(10) == 10
    assert Context.suppress(None) is None


def test_nice_ticks_cover_the_range() -> None:
    ticks = charts.nice_ticks(0, 97)
    assert ticks[0] <= 0 and ticks[-1] >= 97
    assert len(ticks) >= 3


@pytest.mark.parametrize("kind,data", [
    ("funnel", {"steps": [{"label": "a", "value": 10}, {"label": "b", "value": 4}]}),
    ("bar", {"categories": ["x", "y"], "series": [{"name": "s", "values": [1, 2]}]}),
    ("line", {"x": ["1", "2"], "series": [{"name": "s", "values": [1.0, 2.0]}]}),
    ("hist", {"edges": [0, 1, 2], "counts": [3, 4]}),
    ("heatmap", {"rows": ["r"], "columns": ["c"], "cells": [[1.0]]}),
])
def test_every_chart_kind_emits_labelled_svg(kind: str, data: dict) -> None:
    svg = charts.render(kind, data)
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "aria-label=" in svg and "<title>" in svg


def test_chart_text_is_escaped() -> None:
    svg = charts.render("bar", {"categories": ["<script>"],
                                "series": [{"name": "a&b", "values": [1]}]})
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg

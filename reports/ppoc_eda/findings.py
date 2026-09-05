"""The report's data model.

A `Finding` owns its numbers; its prose owns only templates. Rendering resolves
`{name}` placeholders against the finding's `values`, so a number cannot reach
an output without passing through `findings.json` first. That is the whole
anti-drift mechanism: there is no code path that writes a literal figure into
prose.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)[^{}]*\}")


class TemplateError(ValueError):
    """A template referenced a value the finding does not carry."""


@dataclass
class Column:
    key: str
    label: str
    fmt: str = ""          # a format spec, e.g. ",.1f"; "" means str()
    suffix: str = ""       # e.g. "%", " cm"
    align: str = "left"    # left | right


@dataclass
class Table:
    id: str
    caption: str
    columns: list[Column]
    rows: list[dict[str, Any]]
    note: str = ""

    def cell(self, row: dict[str, Any], col: Column) -> str:
        value = row.get(col.key)
        if value is None:
            return "—"
        text = format(value, col.fmt) if col.fmt else str(value)
        return text + col.suffix


@dataclass
class Figure:
    """A chart. `data` is raw and serialized; the SVG is drawn at render time."""

    id: str
    caption: str
    kind: str              # bar | grouped_bar | line | heatmap | step | funnel | hist
    data: dict[str, Any]
    alt: str = ""


@dataclass
class Para:
    """A prose paragraph. `text` is a format template over the finding's values."""

    text: str
    role: str = "body"     # body | implication | method | warning


@dataclass
class Code:
    text: str
    lang: str = "sql"


Block = Para | Table | Figure | Code


@dataclass
class Artifact:
    """A row in the artifact catalogue."""

    name: str
    kind: str              # capture | derivation | linkage | selection | documentation
    scale: str             # a template over the finding's values
    recoverable: str


@dataclass
class Finding:
    id: str                # stable slug, e.g. "snapshot.identity"
    part: str              # "1.1"
    title: str
    values: dict[str, Any] = field(default_factory=dict)
    blocks: list[Block] = field(default_factory=list)
    artifact: Artifact | None = None

    @property
    def anchor(self) -> str:
        return "f-" + self.id.replace(".", "-").replace("_", "-")

    def render(self, text: str) -> str:
        """Resolve a template against this finding's values."""
        missing = [n for n in PLACEHOLDER.findall(text) if n not in self.values]
        if missing:
            raise TemplateError(f"{self.id}: template references {missing}")
        return text.format(**self.values)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id, "part": self.part, "title": self.title,
            "values": self.values,
        }
        tables = [
            {"id": b.id, "caption": b.caption,
             "columns": [c.key for c in b.columns], "rows": b.rows}
            for b in self.blocks if isinstance(b, Table)
        ]
        figures = [
            {"id": b.id, "caption": b.caption, "kind": b.kind, "data": b.data}
            for b in self.blocks if isinstance(b, Figure)
        ]
        if tables:
            out["tables"] = tables
        if figures:
            out["figures"] = figures
        if self.artifact:
            out["artifact"] = {
                "name": self.artifact.name, "kind": self.artifact.kind,
                "scale": self.render(self.artifact.scale),
                "recoverable": self.artifact.recoverable,
            }
        return out


def stabilize(value: Any, digits: int = 12) -> Any:
    """Round floats so a rebuild of an unchanged snapshot compares equal.

    DuckDB sums in parallel, so an aggregate like avg() can differ in its last
    few bits between runs on identical data. Left alone that defeats the
    change-detection gate and churns the committed binaries. Rounding to
    `digits` significant figures removes the scheduling noise while staying far
    finer than anything the report displays, and it is applied to the finding
    itself so the JSON and the prose still carry exactly the same number.
    """
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return value
        return float(f"%.{digits}g" % value)
    if isinstance(value, dict):
        return {k: stabilize(v, digits) for k, v in value.items()}
    if isinstance(value, list):
        return [stabilize(v, digits) for v in value]
    return value


# ---------------------------------------------------------------------------
# Probe registry
# ---------------------------------------------------------------------------

_PROBES: dict[str, Any] = {}


def probe(name: str, part: str):
    """Register a probe. Order within the report is by `part`, then name."""

    def wrap(fn):
        if name in _PROBES:
            raise ValueError(f"duplicate probe {name}")
        fn.probe_name, fn.probe_part = name, part
        _PROBES[name] = fn
        return fn

    return wrap


def registered() -> dict[str, Any]:
    return dict(_PROBES)


def part_key(part: str) -> tuple:
    """Sort '10.2' after '9.1' rather than before it."""
    return tuple(int(x) if x.isdigit() else 0 for x in part.split("."))

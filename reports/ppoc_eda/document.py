"""Assemble registered probe output into the report's part structure."""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field

from .context import Context
from .findings import Finding, part_key, registered

PARTS: list[tuple[str, str, str]] = [
    ("0", "How to use this report",
     "Three ways in, depending on what you came for."),
    ("1", "The snapshot",
     ("What this extract contains, how it was built, and what its construction "
      "forecloses.")),
    ("2", "Checklist coverage",
     ("Every item of the general EHR EDA checklist, mapped to what this snapshot "
      "can and cannot support.")),
    ("3", "Integrity",
     "Keys, linkage, the age axis, missingness, terminology, and capture."),
    ("4", "Anthropometrics",
     "The richest and most artifact-prone measurements in the extract."),
    ("5", "Other clinical domains",
     "Diagnoses, laboratory results, medications, referrals, and demographics."),
    ("6", "Field index",
     "Every column, with its population, range, and the findings that govern it."),
    ("7", "Artifact catalogue",
     "One row per known artifact, with its scale and whether it can be repaired."),
    ("8", "Methods and limitations",
     "How these figures were computed and what would invalidate them."),
]


@dataclass
class Part:
    number: str
    title: str
    lede: str = ""
    findings: list[Finding] = field(default_factory=list)

    @property
    def anchor(self) -> str:
        return f"part-{self.number}"


@dataclass
class Document:
    title: str
    subtitle: str
    parts: list[Part]

    def all_findings(self) -> list[Finding]:
        return [f for p in self.parts for f in p.findings]


def load_probes() -> None:
    """Import every module under probes/ so its @probe decorators register."""
    from . import probes
    for info in pkgutil.iter_modules(probes.__path__):
        importlib.import_module(f"{probes.__name__}.{info.name}")


def build(ctx: Context, only: str | None = None) -> Document:
    load_probes()
    found: list[Finding] = []
    for name, fn in sorted(registered().items()):
        if only and not name.startswith(only):
            continue
        found.extend(fn(ctx))
    found.sort(key=lambda f: (part_key(f.part), f.id))

    parts = [Part(n, t, lede) for n, t, lede in PARTS]
    index = {p.number: p for p in parts}
    for f in found:
        top = f.part.split(".")[0]
        if top not in index:
            raise ValueError(f"{f.id}: part {f.part} has no top-level home")
        index[top].findings.append(f)
    return Document(
        title="PPOC pediatric EHR snapshot: an exploratory data analysis",
        subtitle=(
            "A project-neutral reference for anyone analysing this extract. Every "
            "figure is measured from the delivered bundle; the report states what "
            "the data support, what they do not, and which checks this extract "
            "cannot answer at all."
        ),
        parts=[p for p in parts if p.findings],
    )

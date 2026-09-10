"""Render the finding set to Markdown: the pull-request-reviewable mirror."""

from __future__ import annotations

import re

from ..findings import Code, Figure, Finding, Para, Table


def _slug(heading: str) -> str:
    """The anchor a Markdown viewer derives from a heading, GitHub's rules."""
    return re.sub(r"[^a-z0-9 -]", "", heading.lower()).replace(" ", "-")


def _contents(doc) -> list[str]:
    """A way into the mirror. The HTML has a sticky nav; this file had none."""
    out = ["## Contents", ""]
    for part in doc.parts:
        head = f"{part.number}. {part.title}"
        out.append(f"- [{head}](#{_slug(head)})")
        for f in part.findings:
            sub = f"{f.part} {f.title}"
            out.append(f"  - [{sub}](#{_slug(sub)})")
    return out + [""]


def _cell(text: str) -> str:
    """A pipe inside a cell ends it. Escape or the row grows extra columns.

    This fired once in the committed report — a `beyond |5|` column label emitted
    a seven-cell header over a five-cell separator, and the threshold silently
    vanished from the rendered table while the HTML stayed correct.
    """
    return text.replace("|", "\\|")


def _table(f: Finding, block: Table) -> list[str]:
    head = [_cell(c.label) for c in block.columns]
    out = [f"**{f.render(block.caption)}**", "",
           "| " + " | ".join(head) + " |",
           "| " + " | ".join("---" for _ in head) + " |"]
    for row in block.rows:
        out.append("| " + " | ".join(_cell(block.cell(row, c))
                                    for c in block.columns) + " |")
    out.append("")
    if block.note:
        out += [f.render(block.note), ""]
    return out


def render(doc) -> str:
    lines = [f"# {doc.title}", "", doc.subtitle, ""] + _contents(doc)
    for part in doc.parts:
        lines += [f"## {part.number}. {part.title}", ""]
        if part.lede:
            lines += [part.lede, ""]
        for f in part.findings:
            lines += [f"### {f.part} {f.title}", ""]
            for block in f.blocks:
                if isinstance(block, Para):
                    lines += [f.render(block.text), ""]
                elif isinstance(block, Table):
                    lines += _table(f, block)
                elif isinstance(block, Figure):
                    lines += [(f"*Figure — {f.render(block.caption)}. "
                               f"Rendered in `index.html` at `#{block.id}`.*"), ""]
                elif isinstance(block, Code):
                    lines += [f"```{block.lang}", block.text, "```", ""]
    return "\n".join(lines).rstrip() + "\n"

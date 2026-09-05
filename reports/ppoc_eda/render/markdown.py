"""Render the finding set to Markdown: the pull-request-reviewable mirror."""

from __future__ import annotations

from ..findings import Code, Figure, Finding, Para, Table


def _table(f: Finding, block: Table) -> list[str]:
    head = [c.label for c in block.columns]
    out = [f"**{f.render(block.caption)}**", "",
           "| " + " | ".join(head) + " |",
           "| " + " | ".join("---" for _ in head) + " |"]
    for row in block.rows:
        out.append("| " + " | ".join(block.cell(row, c) for c in block.columns) + " |")
    out.append("")
    if block.note:
        out += [f.render(block.note), ""]
    return out


def render(doc) -> str:
    lines = [f"# {doc.title}", "", doc.subtitle, ""]
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

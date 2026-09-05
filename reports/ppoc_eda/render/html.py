"""Render the finding set to a single self-contained HTML file."""

from __future__ import annotations

import html
from typing import Any

from .. import charts
from ..findings import Code, Figure, Finding, Para, Table
from .style import CSS

TOGGLE_JS = """
(function(){var b=document.querySelector('.themetoggle');if(!b)return;
b.addEventListener('click',function(){var r=document.documentElement;
var d=getComputedStyle(r).getPropertyValue('--surface-0').trim()==='#121211';
r.setAttribute('data-theme',d?'light':'dark');});})();
"""


def e(text: Any) -> str:
    return html.escape(str(text), quote=True)


def _inline(text: str) -> str:
    """Escape, then re-enable the small markdown subset the prose uses."""
    out = e(text)
    while "**" in out:
        out = out.replace("**", "<strong>", 1)
        if "**" in out:
            out = out.replace("**", "</strong>", 1)
        else:
            out += "</strong>"
    parts, i = out.split("`"), 1
    while i < len(parts):
        parts[i] = "<code>" + parts[i] + "</code>"
        i += 2
    out = "".join(parts)
    while "*" in out:
        out = out.replace("*", "<em>", 1)
        if "*" in out:
            out = out.replace("*", "</em>", 1)
        else:
            out += "</em>"
    return out


def _table(f: Finding, block: Table) -> str:
    head = "".join(
        f'<th class="{"num" if c.align == "right" else ""}">{e(c.label)}</th>'
        for c in block.columns
    )
    body = []
    for row in block.rows:
        cells = "".join(
            f'<td class="{"num" if c.align == "right" else ""}">{e(block.cell(row, c))}</td>'
            for c in block.columns
        )
        body.append(f"<tr>{cells}</tr>")
    note = f"<p class='method'>{_inline(f.render(block.note))}</p>" if block.note else ""
    return (f'<div class="tablewrap" id="{e(block.id)}"><table>'
            f"<caption>{_inline(f.render(block.caption))}</caption>"
            f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody>"
            f"</table></div>{note}")


def _figure(f: Finding, block: Figure) -> str:
    svg = charts.render(block.kind, block.data)
    return (f'<figure id="{e(block.id)}">{svg}'
            f"<figcaption>{_inline(f.render(block.caption))}</figcaption></figure>")


def _blocks(f: Finding) -> str:
    out = []
    for block in f.blocks:
        if isinstance(block, Para):
            cls = {"body": "", "implication": "implication",
                   "method": "method", "warning": "warning"}[block.role]
            attr = f' class="{cls}"' if cls else ""
            out.append(f"<p{attr}>{_inline(f.render(block.text))}</p>")
        elif isinstance(block, Table):
            out.append(_table(f, block))
        elif isinstance(block, Figure):
            out.append(_figure(f, block))
        elif isinstance(block, Code):
            out.append(f"<pre><code>{e(block.text)}</code></pre>")
    return "".join(out)


def render(doc) -> str:
    """`doc` is a Document from ppoc_eda.document."""
    toc, body = [], []
    for part in doc.parts:
        toc.append(f'<a class="part" href="#{e(part.anchor)}">'
                   f"{e(part.number)} {e(part.title)}</a>")
        body.append(f'<h2 id="{e(part.anchor)}">'
                    f"{e(part.number)}. {e(part.title)}</h2>")
        if part.lede:
            body.append(f'<p class="lede">{_inline(part.lede)}</p>')
        for f in part.findings:
            toc.append(f'<a href="#{e(f.anchor)}">{e(f.part)} {e(f.title)}</a>')
            body.append(f'<section class="finding" id="{e(f.anchor)}">'
                        f"<h3>{e(f.part)} {e(f.title)}</h3>{_blocks(f)}</section>")
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{e(doc.title)}</title>"
        f'<meta name="description" content="{e(doc.subtitle)}">'
        f"<style>{CSS}</style></head><body>"
        '<button class="themetoggle" type="button">theme</button>'
        '<div class="wrap">'
        f'<nav class="toc"><h2>Contents</h2>{"".join(toc)}</nav>'
        f"<main><h1>{e(doc.title)}</h1>"
        f'<p class="lede">{_inline(doc.subtitle)}</p>'
        f'{"".join(body)}</main></div>'
        f"<script>{TOGGLE_JS}</script></body></html>\n"
    )

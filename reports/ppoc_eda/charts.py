"""Hand-rolled SVG chart primitives.

No plotting dependency: the vocabulary this report needs is small, and emitting
SVG directly means the marks inherit the page's CSS custom properties, so one
palette definition serves light mode, dark mode, and the print stylesheet.

Palette and mark rules follow the dataviz reference instance. The three
categorical slots used here were validated with `scripts/validate_palette.js`
under `--pairs all` in both modes; light-mode slot 3 sits below 3:1 contrast, so
the relief rule applies and every figure ships beside its own data table.
"""

from __future__ import annotations

import html
import math
from typing import Any

W = 760                     # viewBox width; the SVG scales to its container
PAD = {"l": 64, "r": 20, "t": 16, "b": 40}
BAR_RADIUS = 4              # rounded data-end
GAP = 2                     # surface gap between adjacent fills


def esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    """Round tick values covering [lo, hi]."""
    if hi <= lo:
        return [lo]
    raw = (hi - lo) / max(count, 1)
    mag = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 2.5, 5, 10):
        if raw <= mag * mult:
            stepsize = mag * mult
            break
    else:
        stepsize = mag * 10
    start = math.floor(lo / stepsize) * stepsize
    end = math.ceil(hi / stepsize) * stepsize
    out, value = [], start
    while value <= end + stepsize * 1e-9:
        if value >= lo - stepsize * 1e-9:
            out.append(round(value, 10))
        value += stepsize
    return out or [lo, hi]


def fmt_tick(value: float) -> str:
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:g}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:g}k"
    if value == int(value):
        return str(int(value))
    return f"{value:g}"


def _open(height: int, title: str, desc: str) -> list[str]:
    return [
        (f'<svg class="vx" viewBox="0 0 {W} {height}" width="100%" height="auto" '
         f'role="img" preserveAspectRatio="xMidYMid meet" '
         f'aria-label="{esc(title)}">'),
        f"<title>{esc(title)}</title><desc>{esc(desc)}</desc>",
    ]


def _yaxis(parts: list[str], ticks: list[float], y_of, x0: int, x1: int,
           suffix: str = "") -> None:
    """Grid lines and tick labels. The suffix carries the unit onto the axis, so a
    percentage does not read as a bare count."""
    for t in ticks:
        y = y_of(t)
        parts.append(f'<line class="vx-grid" x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}"/>')
        parts.append(f'<text class="vx-tick" x="{x0 - 8}" y="{y + 4:.1f}" '
                     f'text-anchor="end">{fmt_tick(t)}{esc(suffix)}</text>')


def _legend(parts: list[str], series: list[str], y: int) -> None:
    x = PAD["l"]
    for i, name in enumerate(series):
        parts.append(f'<rect class="vx-swatch" x="{x}" y="{y - 9}" width="10" height="10" '
                     f'rx="2" fill="var(--series-{i + 1})"/>')
        parts.append(f'<text class="vx-label" x="{x + 15}" y="{y}">{esc(name)}</text>')
        x += 22 + int(7.0 * len(name))


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def funnel(data: dict) -> str:
    """Ordinal stages narrowing to a final population."""
    steps = data["steps"]
    top = max(s["value"] for s in steps)
    row_h, gap = 44, 10
    height = PAD["t"] + len(steps) * (row_h + gap) + PAD["b"]
    parts = _open(height, data.get("title", "Funnel"),
                  f"{len(steps)} stages from {top:,} to {steps[-1]['value']:,}.")
    # One hue, not an ordinal ramp: width already encodes the magnitude, and a
    # ramp would put the on-bar label over both light and dark fills, which no
    # single text token can serve at adequate contrast.
    # Reserve room on the right for the value label, which sits outside the bar.
    inner = W - PAD["l"] - PAD["r"] - 92
    for i, s in enumerate(steps):
        y = PAD["t"] + i * (row_h + gap)
        w = max(2.0, inner * s["value"] / top)
        parts.append(
            f'<g class="vx-mark"><title>{esc(s["label"])}: {s["value"]:,}</title>'
            f'<rect x="{PAD["l"]}" y="{y}" width="{w:.1f}" height="{row_h - GAP}" '
            f'rx="{BAR_RADIUS}" fill="var(--series-1)"/></g>'
        )
        parts.append(f'<text class="vx-value" x="{PAD["l"] + w + 8:.1f}" y="{y + 18}">'
                     f'{s["value"]:,}</text>')
        parts.append(f'<text class="vx-label" x="{PAD["l"] + 12}" y="{y + 19}" '
                     f'style="fill:var(--on-mark);font-weight:600">'
                     f'{esc(s["label"])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def bars(data: dict) -> str:
    """Vertical bars; one or more series per category (grouped)."""
    cats = data["categories"]
    series = data["series"]                     # [{"name": str, "values": [...]}, ...]
    suffix = data.get("suffix", "")
    height = data.get("height", 300)
    show_legend = len(series) > 1
    plot_b = height - PAD["b"] - (18 if show_legend else 0)
    hi = max((v for s in series for v in s["values"] if v is not None), default=1)
    ticks = nice_ticks(0, hi)
    top = max(ticks)

    def y_of(v: float) -> float:
        return plot_b - (plot_b - PAD["t"]) * (v / top if top else 0)

    parts = _open(height, data.get("title", "Bar chart"),
                  f"{len(cats)} categories, {len(series)} series.")
    _yaxis(parts, ticks, y_of, PAD["l"], W - PAD["r"], suffix)
    inner = (W - PAD["l"] - PAD["r"]) / max(len(cats), 1)
    bw = (inner * 0.68) / len(series)
    for ci, cat in enumerate(cats):
        base = PAD["l"] + ci * inner + inner * 0.16
        for si, s in enumerate(series):
            v = s["values"][ci]
            if v is None:
                continue
            y, h = y_of(v), plot_b - y_of(v)
            parts.append(
                f'<g class="vx-mark"><title>{esc(cat)} · {esc(s["name"])}: '
                f'{v:,.4g}{esc(suffix)}</title>'
                f'<rect x="{base + si * bw:.1f}" y="{y:.1f}" '
                f'width="{max(bw - GAP, 1):.1f}" height="{max(h, 0.5):.1f}" '
                f'rx="{BAR_RADIUS}" fill="var(--series-{si + 1})"/></g>'
            )
        parts.append(f'<text class="vx-tick" x="{PAD["l"] + ci * inner + inner / 2:.1f}" '
                     f'y="{plot_b + 16}" text-anchor="middle">{esc(cat)}</text>')
    parts.append(f'<line class="vx-axis" x1="{PAD["l"]}" y1="{plot_b}" '
                 f'x2="{W - PAD["r"]}" y2="{plot_b}"/>')
    if show_legend:
        _legend(parts, [s["name"] for s in series], height - 6)
    parts.append("</svg>")
    return "".join(parts)


def line(data: dict) -> str:
    """One or more series over an ordered x axis, direct-labelled at the end."""
    xs = data["x"]
    series = data["series"]
    suffix = data.get("suffix", "")
    height = data.get("height", 300)
    plot_b = height - PAD["b"] - (16 if len(series) > 1 else 0)
    vals = [v for s in series for v in s["values"] if v is not None]
    ticks = nice_ticks(min(vals + [0]), max(vals or [1]))
    lo, top = min(ticks), max(ticks)

    def y_of(v: float) -> float:
        span = (top - lo) or 1
        return plot_b - (plot_b - PAD["t"]) * ((v - lo) / span)

    label_series = len(series) > 1
    reserve = (14 + max((7.0 * len(s["name"]) for s in series), default=0)
               if label_series else 8)

    def x_of(i: int) -> float:
        n = max(len(xs) - 1, 1)
        return PAD["l"] + (W - PAD["l"] - PAD["r"] - reserve) * (i / n)

    parts = _open(height, data.get("title", "Line chart"),
                  f"{len(series)} series over {len(xs)} points.")
    _yaxis(parts, ticks, y_of, PAD["l"], W - PAD["r"], suffix)
    for si, s in enumerate(series):
        pts = [(x_of(i), y_of(v)) for i, v in enumerate(s["values"]) if v is not None]
        if not pts:
            continue
        d = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
        parts.append(f'<path class="vx-line" d="{d}" stroke="var(--series-{si + 1})"/>')
        for (x, y), v in zip(pts, [v for v in s["values"] if v is not None], strict=False):
            parts.append(f'<g class="vx-mark"><title>{esc(s["name"])}: {v:,.4g}{esc(suffix)}'
                         f'</title><circle class="vx-dot" cx="{x:.1f}" cy="{y:.1f}" r="4" '
                         f'fill="var(--series-{si + 1})"/></g>')
        if label_series:
            lx, ly = pts[-1]
            parts.append(f'<text class="vx-label" x="{lx + 8:.1f}" y="{ly + 4:.1f}" '
                         f'style="fill:var(--series-{si + 1})">'
                         f'{esc(s["name"])}</text>')
    stride = max(1, len(xs) // 9)
    for i, xv in enumerate(xs):
        if i % stride:
            continue
        parts.append(f'<text class="vx-tick" x="{x_of(i):.1f}" y="{plot_b + 16}" '
                     f'text-anchor="middle">{esc(xv)}</text>')
    parts.append(f'<line class="vx-axis" x1="{PAD["l"]}" y1="{plot_b}" '
                 f'x2="{W - PAD["r"]}" y2="{plot_b}"/>')
    if label_series:
        _legend(parts, [s["name"] for s in series], height - 4)
    parts.append("</svg>")
    return "".join(parts)


def step(data: dict) -> str:
    """A retention/survival style step curve."""
    d = dict(data)
    d.setdefault("title", "Step chart")
    return line(d)


def hist(data: dict) -> str:
    """Binned counts, with optional vertical reference lines."""
    edges, counts = data["edges"], data["counts"]
    height = data.get("height", 300)
    plot_b = height - PAD["b"]
    ticks = nice_ticks(0, max(counts or [1]))
    top = max(ticks)
    lo, hi = edges[0], edges[-1]

    def y_of(v: float) -> float:
        return plot_b - (plot_b - PAD["t"]) * (v / top if top else 0)

    def x_of(v: float) -> float:
        return PAD["l"] + (W - PAD["l"] - PAD["r"]) * ((v - lo) / ((hi - lo) or 1))

    parts = _open(height, data.get("title", "Histogram"), f"{len(counts)} bins.")
    _yaxis(parts, ticks, y_of, PAD["l"], W - PAD["r"])
    for i, c in enumerate(counts):
        x0, x1 = x_of(edges[i]), x_of(edges[i + 1])
        y = y_of(c)
        parts.append(
            f'<g class="vx-mark"><title>{edges[i]:,.4g} to {edges[i + 1]:,.4g}: {c:,}</title>'
            f'<rect x="{x0:.1f}" y="{y:.1f}" width="{max(x1 - x0 - GAP, 0.6):.1f}" '
            f'height="{max(plot_b - y, 0.5):.1f}" rx="1" fill="var(--series-1)"/></g>'
        )
    for mark in data.get("marks", []):
        x = x_of(mark["at"])
        parts.append(f'<line class="vx-rule" x1="{x:.1f}" y1="{PAD["t"]}" x2="{x:.1f}" '
                     f'y2="{plot_b}"/>')
        parts.append(f'<text class="vx-rule-label" x="{x + 5:.1f}" '
                     f'y="{PAD["t"] + 12}">{esc(mark["label"])}</text>')
    for t in nice_ticks(lo, hi, 6):
        parts.append(f'<text class="vx-tick" x="{x_of(t):.1f}" y="{plot_b + 16}" '
                     f'text-anchor="middle">{fmt_tick(t)}</text>')
    parts.append(f'<line class="vx-axis" x1="{PAD["l"]}" y1="{plot_b}" '
                 f'x2="{W - PAD["r"]}" y2="{plot_b}"/>')
    parts.append("</svg>")
    return "".join(parts)


def heatmap(data: dict) -> str:
    """Sequential magnitude over rows x columns, one hue light to dark."""
    rows, cols, cells = data["rows"], data["columns"], data["cells"]
    suffix = data.get("suffix", "")
    cell_h = data.get("cell_height", 18)
    left = data.get("label_width", 210)
    height = PAD["t"] + len(rows) * cell_h + 54
    cw = (W - left - PAD["r"]) / max(len(cols), 1)
    hi = max((v for row in cells for v in row if v is not None), default=1) or 1
    parts = _open(height, data.get("title", "Heatmap"),
                  f"{len(rows)} rows by {len(cols)} columns.")
    for ri, rname in enumerate(rows):
        y = PAD["t"] + ri * cell_h
        parts.append(f'<text class="vx-tick" x="{left - 8}" y="{y + cell_h - 5}" '
                     f'text-anchor="end">{esc(rname)}</text>')
        for ci in range(len(cols)):
            v = cells[ri][ci]
            x = left + ci * cw
            if v is None:
                parts.append(f'<rect x="{x:.1f}" y="{y}" width="{cw - GAP:.1f}" '
                             f'height="{cell_h - GAP}" rx="2" fill="var(--surface-2)"/>')
                continue
            shade = min(6, round(6 * (v / hi)))
            parts.append(
                f'<g class="vx-mark"><title>{esc(rname)} · {esc(cols[ci])}: '
                f'{v:,.4g}{esc(suffix)}</title>'
                f'<rect x="{x:.1f}" y="{y}" width="{cw - GAP:.1f}" '
                f'height="{cell_h - GAP}" rx="2" fill="var(--seq-{shade})"/></g>'
            )
    for ci, cname in enumerate(cols):
        parts.append(f'<text class="vx-tick" x="{left + ci * cw + cw / 2:.1f}" '
                     f'y="{PAD["t"] + len(rows) * cell_h + 16}" '
                     f'text-anchor="middle">{esc(cname)}</text>')
    parts.append(f'<text class="vx-label" x="{left}" '
                 f'y="{PAD["t"] + len(rows) * cell_h + 40}">0</text>')
    for s in range(7):
        parts.append(f'<rect x="{left + 18 + s * 16}" '
                     f'y="{PAD["t"] + len(rows) * cell_h + 30}" width="14" height="10" '
                     f'rx="2" fill="var(--seq-{s})"/>')
    parts.append(f'<text class="vx-label" x="{left + 18 + 7 * 16 + 6}" '
                 f'y="{PAD["t"] + len(rows) * cell_h + 40}">{fmt_tick(hi)}{esc(suffix)}</text>')
    parts.append("</svg>")
    return "".join(parts)


RENDERERS = {"funnel": funnel, "bar": bars, "grouped_bar": bars, "line": line,
             "step": step, "hist": hist, "heatmap": heatmap}


def render(kind: str, data: dict) -> str:
    if kind not in RENDERERS:
        raise ValueError(f"unknown chart kind {kind!r}")
    return RENDERERS[kind](data)

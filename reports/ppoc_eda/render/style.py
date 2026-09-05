"""The report's stylesheet: theme tokens, layout, and the print rules.

Colour tokens are the dataviz reference instance. Light values live on bare
`:root`; the dark values are declared twice, once under `prefers-color-scheme`
guarded so an explicit light stamp still wins, and once under an explicit dark
stamp so the toggle wins in both directions.
"""

LIGHT = {
    "--surface-0": "#ffffff", "--surface-1": "#fcfcfb", "--surface-2": "#f0efec",
    "--border": "#dcdbd6", "--text-primary": "#0b0b0b",
    "--text-secondary": "#52514e", "--text-muted": "#77756e",
    "--series-1": "#2a78d6", "--series-2": "#eb6834", "--series-3": "#1baf7a",
    "--on-mark": "#ffffff", "--accent": "#2a78d6",
    "--seq-0": "#cde2fb", "--seq-1": "#9ec5f4", "--seq-2": "#6da7ec",
    "--seq-3": "#3987e5", "--seq-4": "#256abf", "--seq-5": "#184f95",
    "--seq-6": "#0d366b",
    "--warn-bg": "#fdf2ec", "--warn-border": "#eb6834",
}
DARK = {
    "--surface-0": "#121211", "--surface-1": "#1a1a19", "--surface-2": "#26261f",
    "--border": "#383835", "--text-primary": "#ffffff",
    "--text-secondary": "#c3c2b7", "--text-muted": "#98978d",
    "--series-1": "#3987e5", "--series-2": "#d95926", "--series-3": "#199e70",
    "--on-mark": "#ffffff", "--accent": "#6da7ec",
    # Sequential inverts on a dark surface: near-zero recedes toward the ground.
    "--seq-0": "#184f95", "--seq-1": "#1c5cab", "--seq-2": "#256abf",
    "--seq-3": "#3987e5", "--seq-4": "#6da7ec", "--seq-5": "#9ec5f4",
    "--seq-6": "#cde2fb",
    "--warn-bg": "#2a1c14", "--warn-border": "#d95926",
}


def _vars(tokens: dict[str, str]) -> str:
    return "".join(f"{k}:{v};" for k, v in tokens.items())


CSS = f"""
:root {{ {_vars(LIGHT)} color-scheme: light; }}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{ {_vars(DARK)} color-scheme: dark; }}
}}
:root[data-theme="dark"] {{ {_vars(DARK)} color-scheme: dark; }}

* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--surface-0); color: var(--text-primary);
  font: 16px/1.62 ui-sans-serif, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  -webkit-text-size-adjust: 100%;
}}
.wrap {{ display: grid; grid-template-columns: 292px minmax(0, 1fr); gap: 40px;
        max-width: 1240px; margin: 0 auto; padding: 0 24px; }}
nav.toc {{ position: sticky; top: 0; align-self: start; max-height: 100vh;
           overflow-y: auto; padding: 28px 0 40px; font-size: 13.5px; }}
nav.toc h2 {{ font-size: 12px; letter-spacing: .08em; text-transform: uppercase;
              color: var(--text-muted); margin: 0 0 10px; }}
nav.toc a {{ display: block; padding: 3px 8px; color: var(--text-secondary);
             text-decoration: none; border-left: 2px solid transparent; }}
nav.toc a:hover {{ color: var(--accent); border-left-color: var(--accent); }}
nav.toc a.part {{ margin-top: 12px; font-weight: 650; color: var(--text-primary); }}
main {{ min-width: 0; padding: 28px 0 96px; }}

h1 {{ font-size: 30px; line-height: 1.25; margin: 8px 0 4px; letter-spacing: -.01em; }}
h2 {{ font-size: 23px; margin: 56px 0 6px; padding-top: 14px;
      border-top: 1px solid var(--border); letter-spacing: -.01em; }}
h3 {{ font-size: 17.5px; margin: 34px 0 6px; }}
p {{ margin: 12px 0; max-width: 74ch; }}
a {{ color: var(--accent); }}
code {{ font: 13.5px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
        background: var(--surface-2); padding: 1px 5px; border-radius: 4px; }}
pre {{ background: var(--surface-2); padding: 14px 16px; border-radius: 8px;
       overflow-x: auto; font-size: 13px; }}
.lede {{ color: var(--text-secondary); max-width: 74ch; }}

.finding {{ margin: 0 0 8px; }}
.implication {{ background: var(--surface-2); border-left: 3px solid var(--accent);
                padding: 12px 16px; border-radius: 0 8px 8px 0; max-width: 74ch; }}
.method {{ color: var(--text-secondary); font-size: 14.5px; max-width: 74ch; }}
.warning {{ background: var(--warn-bg); border-left: 3px solid var(--warn-border);
            padding: 12px 16px; border-radius: 0 8px 8px 0; max-width: 74ch; }}

.tablewrap {{ overflow-x: auto; margin: 18px 0; }}
table {{ border-collapse: collapse; font-size: 14px; width: 100%; }}
caption {{ caption-side: top; text-align: left; color: var(--text-secondary);
           font-size: 13.5px; padding-bottom: 7px; }}
th, td {{ padding: 7px 12px; border-bottom: 1px solid var(--border);
          white-space: nowrap; }}
th {{ text-align: left; font-weight: 620; color: var(--text-secondary);
      font-size: 12.5px; letter-spacing: .03em; text-transform: uppercase; }}
td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
tbody tr:hover {{ background: var(--surface-2); }}

figure {{ margin: 22px 0; }}
figcaption {{ color: var(--text-secondary); font-size: 13.5px; margin-top: 8px; }}
svg.vx {{ display: block; max-width: 100%; }}
.vx-grid {{ stroke: var(--border); stroke-width: 1; }}
.vx-axis {{ stroke: var(--text-muted); stroke-width: 1; }}
.vx-line {{ fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }}
.vx-dot {{ stroke: var(--surface-0); stroke-width: 2; }}
.vx-rule {{ stroke: var(--text-secondary); stroke-width: 1.5; stroke-dasharray: 4 3; }}
.vx-tick {{ fill: var(--text-muted); font-size: 11.5px; }}
.vx-label {{ fill: var(--text-secondary); font-size: 12.5px; }}
.vx-value {{ fill: var(--text-primary); font-size: 12.5px;
             font-variant-numeric: tabular-nums; }}
.vx-rule-label {{ fill: var(--text-secondary); font-size: 11.5px; }}
.vx-mark {{ cursor: default; }}
.vx-mark:hover rect, .vx-mark:hover circle {{ opacity: .78; }}

.themetoggle {{ position: fixed; top: 12px; right: 14px; z-index: 9;
  background: var(--surface-2); color: var(--text-secondary);
  border: 1px solid var(--border); border-radius: 999px; padding: 5px 13px;
  font-size: 12.5px; cursor: pointer; }}

@media (max-width: 900px) {{
  .wrap {{ grid-template-columns: 1fr; gap: 0; }}
  nav.toc {{ position: static; max-height: none; border-bottom: 1px solid var(--border); }}
}}

@media print {{
  /* Force the light palette: a dark ground is wrong on paper. */
  :root, :root[data-theme="dark"] {{ {_vars(LIGHT)} color-scheme: light; }}
  @page {{ size: Letter; margin: 0.6in 0.55in; }}
  body {{ font-size: 10.5pt; line-height: 1.5; background: #fff; }}
  .wrap {{ display: block; max-width: none; padding: 0; }}
  nav.toc, .themetoggle {{ display: none; }}
  main {{ padding: 0; }}
  h2 {{ break-before: page; border-top: none; }}
  h2:first-of-type {{ break-before: avoid; }}
  h3, figure, .implication, .warning, .method, tr {{ break-inside: avoid; }}
  thead {{ display: table-header-group; }}
  table {{ font-size: 8.6pt; width: 100%; }}
  th, td {{ padding: 3px 6px; white-space: normal; }}
  p, .lede, .implication, .method, .warning {{ max-width: none; }}
  .tablewrap {{ overflow: visible; }}
  a {{ color: inherit; text-decoration: none; }}
}}
"""

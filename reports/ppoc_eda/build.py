"""Build the report: compute findings once, then render every output from them.

Outputs are rewritten only when the findings change. That keeps the committed
HTML and PDF out of the history when a rebuild produces the same analysis, and
it makes the PDF's own byte-stability a convenience rather than a requirement.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from .context import OUT_DIR, open_context
from .document import build as build_document
from .findings import registered
from .render import html as render_html
from .render import markdown as render_markdown
from .render import pdf as render_pdf


def payload(doc, ctx) -> dict:
    return {
        "snapshot": {
            "package": ctx.package.get("name"),
            "version": ctx.package.get("version"),
            "snapshot": ctx.snapshot,
            "sha256": ctx.digest,
        },
        "parts": [
            {"number": p.number, "title": p.title,
             "findings": [f.to_json() for f in p.findings]}
            for p in doc.parts
        ],
    }


def canonical(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False,
                      default=str) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bundle", default=None, help="path to the DuckDB bundle")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--only", default=None, help="run probes whose name starts with this")
    ap.add_argument("--list-probes", action="store_true")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="rewrite outputs even when the findings are unchanged")
    args = ap.parse_args(argv)

    if args.list_probes:
        from .document import load_probes
        load_probes()
        for name, fn in sorted(registered().items()):
            print(f"{fn.probe_part:>5s}  {name}")
        return 0

    ctx = open_context(args.bundle) if args.bundle else open_context()
    try:
        doc = build_document(ctx, only=args.only)
        data = payload(doc, ctx)
        body = canonical(data)
        html_text = render_html.render(doc)
        md_text = render_markdown.render(doc)
    finally:
        ctx.con.close()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    findings_path = out / "findings.json"

    previous = None
    if findings_path.is_file():
        try:
            stored = json.loads(findings_path.read_text())
            stored.pop("generated_at", None)
            previous = canonical(stored)
        except json.JSONDecodeError:
            previous = None

    if previous == body and not args.force and not args.only:
        print("findings unchanged — outputs left untouched")
        return 0

    stamped = dict(data)
    stamped["generated_at"] = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    findings_path.write_text(canonical(stamped), encoding="utf-8")
    (out / "index.html").write_text(html_text, encoding="utf-8")
    (out / "ppoc-eda.md").write_text(md_text, encoding="utf-8")
    n = len(doc.all_findings())
    print(f"wrote findings.json, index.html, ppoc-eda.md ({n} findings, "
          f"{len(doc.parts)} parts)")

    if args.no_pdf:
        print("pdf: skipped by --no-pdf")
    else:
        print("pdf:", render_pdf.render(out / "index.html", out / "ppoc-eda.pdf"))
    return 0

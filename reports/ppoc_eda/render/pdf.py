"""Derive the PDF from the rendered HTML with headless Chrome.

Chrome is used because it renders exactly the CSS and inline SVG the HTML page
already uses, so the PDF cannot disagree with the HTML about anything. It is
optional: when no browser is found the other three outputs still build.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)
FIXED_DATE = b"D:20240101000000Z"


def find_browser() -> str | None:
    explicit = os.environ.get("PPOC_CHROME")
    if explicit and Path(explicit).exists():
        return explicit
    for name in ("google-chrome", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    return next((c for c in CANDIDATES if Path(c).exists()), None)


def _normalize(pdf: Path) -> None:
    """Strip the wall-clock stamps Chrome writes, then fix the trailer id.

    Determinism is a convenience here, not a guarantee: the build only rewrites
    outputs when the findings change, so an unchanged snapshot never reaches
    this function.
    """
    raw = pdf.read_bytes()
    raw = re.sub(rb"/(CreationDate|ModDate)\s*\(D:[^)]*\)",
                 lambda m: b"/" + m.group(1) + b" (" + FIXED_DATE + b")", raw)
    pdf.write_bytes(raw)
    qpdf = shutil.which("qpdf")
    if qpdf:
        tmp = pdf.with_suffix(".tmp.pdf")
        result = subprocess.run(
            [qpdf, "--deterministic-id", "--object-streams=generate",
             str(pdf), str(tmp)],
            capture_output=True, check=False,
        )
        # qpdf warns on files it can still repair; accept those.
        if tmp.exists() and result.returncode in (0, 3):
            tmp.replace(pdf)
        elif tmp.exists():
            tmp.unlink()


def render(html_path: Path, pdf_path: Path, wait: float = 120.0) -> str:
    """Print `html_path` to `pdf_path`.

    Chrome writes the PDF and then, on macOS, frequently declines to exit. So
    the file is the completion signal, not the process: poll until it exists
    and stops growing, then terminate the browser.
    """
    browser = find_browser()
    if not browser:
        return ("skipped: no Chrome or Chromium found. Set PPOC_CHROME to a "
                "browser binary to build the PDF.")
    if pdf_path.exists():
        pdf_path.unlink()
    profile = pdf_path.parent / ".chrome-profile"
    shutil.rmtree(profile, ignore_errors=True)
    proc = subprocess.Popen(
        [browser, "--headless=old", "--disable-gpu", "--no-sandbox",
         "--no-first-run", "--no-default-browser-check", "--disable-extensions",
         "--disable-background-networking", "--virtual-time-budget=20000",
         "--no-pdf-header-footer", f"--user-data-dir={profile}",
         f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri()],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline, size, stable = time.monotonic() + wait, -1, 0
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None and pdf_path.exists():
                break
            current = pdf_path.stat().st_size if pdf_path.exists() else -1
            if current > 0 and current == size:
                stable += 1
                if stable >= 3:          # unchanged across ~1.5s: fully written
                    break
            else:
                stable = 0
            size = current
            time.sleep(0.5)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        shutil.rmtree(profile, ignore_errors=True)

    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        return "failed: the browser produced no PDF"
    _normalize(pdf_path)
    return f"wrote {pdf_path.name} ({pdf_path.stat().st_size / 1024:.0f} KB)"

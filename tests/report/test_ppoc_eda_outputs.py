"""Audits over the built PPOC EDA outputs.

These check the artifacts, not the code that made them: a report that names a
downstream project, or that leaks a date or a free-text string from a source
document, is a defect regardless of which probe produced it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from .pdf_text import extract, squashed

OUT = Path(__file__).resolve().parents[2] / "reports" / "ppoc-eda"
TEXT_OUTPUTS = ("index.html", "ppoc-eda.md")

#: Terms that would make this report specific to one downstream project.
FORBIDDEN = [
    "growthchartliteracy", "growth-chart-literacy", "counterfactual",
    "stimulus", "stimuli", "serialization", "serialized",
    "this project", "the source project", "healthy arm", "referral endpoint",
]
EXPERIMENT_CODE = re.compile(r"\bE(?:3|5a|5|7|9)\b")

#: The report is allowed to name the cohort and extract anchors, and nothing else
#: date-shaped. A leaked source-document string would show up as a slash date.
SLASH_DATE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")
ALLOWED_DATES = {"31 Dec 2024", "03 Feb 2025"}
LONG_DATE = re.compile(r"\b\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}\b")

#: An absolute path outside the repository would break the neutrality rule.
FOREIGN_PATH = re.compile(r"/Users/[A-Za-z0-9_.-]+/(?!src/tries/ppoc-data-schema)")


def _pdf_text() -> str:
    """The PDF is the artifact GitHub renders, so it is audited like the rest."""
    pdf = OUT / "ppoc-eda.pdf"
    if not pdf.is_file():
        pytest.skip("no PDF built (needs Chrome)")
    text = extract(pdf)
    if len(text) < 2000:
        pytest.skip("PDF text could not be decoded")
    return text


def _outputs() -> list[Path]:
    present = [OUT / name for name in TEXT_OUTPUTS if (OUT / name).is_file()]
    if not present:
        pytest.skip("report has not been built; run reports/build_ppoc_eda.py")
    return present


@pytest.mark.parametrize("term", FORBIDDEN)
def test_no_project_specific_language(term: str) -> None:
    for path in _outputs():
        assert term not in path.read_text(encoding="utf-8").lower(), (
            f"{path.name} contains project-specific term {term!r}"
        )


def test_no_experiment_codes() -> None:
    for path in _outputs():
        hits = EXPERIMENT_CODE.findall(path.read_text(encoding="utf-8"))
        assert not hits, f"{path.name} references experiment codes {set(hits)}"


def test_no_leaked_dates() -> None:
    """No date-shaped string beyond the two cohort anchors."""
    for path in _outputs():
        text = path.read_text(encoding="utf-8")
        assert not SLASH_DATE.findall(text), f"{path.name} carries a slash date"
        stray = set(LONG_DATE.findall(text)) - ALLOWED_DATES
        assert not stray, f"{path.name} carries unexpected dates {stray}"


def test_no_foreign_absolute_paths() -> None:
    for path in _outputs():
        hits = FOREIGN_PATH.findall(path.read_text(encoding="utf-8"))
        assert not hits, f"{path.name} contains an absolute path outside the repo"


def test_findings_json_is_the_source_of_truth() -> None:
    path = OUT / "findings.json"
    if not path.is_file():
        pytest.skip("report has not been built")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["snapshot"]["sha256"], "findings.json records no bundle digest"
    findings = [f for p in data["parts"] for f in p["findings"]]
    assert findings, "findings.json carries no findings"
    ids = [f["id"] for f in findings]
    assert len(ids) == len(set(ids)), "duplicate finding ids"
    for f in findings:
        assert f["title"], f"{f['id']} has no title"


def test_every_html_figure_has_a_caption_and_label() -> None:
    path = OUT / "index.html"
    if not path.is_file():
        pytest.skip("report has not been built")
    html = path.read_text(encoding="utf-8")
    assert html.count("<figure") == html.count("<figcaption"), (
        "a figure is missing its caption"
    )
    for svg in re.findall(r"<svg[^>]*>", html):
        assert "aria-label=" in svg, "an SVG is missing its accessible label"


# --- the same audits, over the PDF -----------------------------------------

@pytest.mark.parametrize("term", FORBIDDEN)
def test_pdf_has_no_project_specific_language(term: str) -> None:
    _pdf_text()
    assert term.replace(" ", "") not in squashed(OUT / "ppoc-eda.pdf"), (
        f"the PDF contains project-specific term {term!r}"
    )


def test_pdf_has_no_experiment_codes() -> None:
    assert not EXPERIMENT_CODE.findall(_pdf_text()), "the PDF references experiment codes"


def test_pdf_has_no_leaked_dates() -> None:
    text = _pdf_text()
    assert not SLASH_DATE.findall(text), "the PDF carries a slash date"
    stray = set(LONG_DATE.findall(text)) - ALLOWED_DATES
    assert not stray, f"the PDF carries unexpected dates {stray}"


def test_pdf_has_no_foreign_paths_or_source_uri() -> None:
    """Chrome can write the source file:// URL into the document; it must not."""
    squash = squashed(OUT / "ppoc-eda.pdf")
    assert "file://" not in squash, "the PDF records its own source URI"
    assert not FOREIGN_PATH.findall(_pdf_text()), (
        "the PDF contains an absolute path outside the repo"
    )


def test_coverage_map_cites_only_sections_that_exist() -> None:
    """A checklist row pointing at a section nobody wrote destroys the map's value."""
    path = OUT / "findings.json"
    if not path.is_file():
        pytest.skip("report has not been built")
    data = json.loads(path.read_text(encoding="utf-8"))
    findings = [f for p in data["parts"] for f in p["findings"]]
    existing = {f["part"] for f in findings}

    coverage = next((f for f in findings if f["id"] == "coverage.map"), None)
    if coverage is None:
        pytest.skip("coverage map not built")
    cited = set()
    for table in coverage.get("tables", []):
        for row in table["rows"]:
            cited.update(re.findall(r"\b(\d+\.\d+)\b", row.get("note", "")))
    missing = sorted(cited - existing)
    assert not missing, f"coverage map cites sections that do not exist: {missing}"


def test_frequency_orderings_carry_a_tiebreak() -> None:
    """A frequency ordering without a tiebreak is not reproducible.

    DuckDB orders ties by whatever its parallel scan produced, so `ORDER BY n
    DESC` alone lets equal-count rows swap between runs. That rewrites the
    committed HTML and PDF on every rebuild and defeats the change-detection
    gate, which is how it was found.
    """
    probes = Path(__file__).resolve().parents[2] / "reports" / "ppoc_eda" / "probes"
    offenders = []
    for path in probes.glob("*.py"):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"ORDER BY .*\bDESC\b", line) and "DESC," not in line:
                offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert not offenders, "frequency ordering without a tiebreak:\n" + "\n".join(offenders)

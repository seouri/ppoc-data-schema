from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = (ROOT / "docs" / "synthetic-generator.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def _hypothyroidism_section() -> str:
    heading = "## Evaluator-only pediatric-hypothyroidism ancillary pathway"
    if heading not in GUIDE:
        return ""
    start = GUIDE.index(heading)
    end = GUIDE.find("\n## ", start + len(heading))
    return GUIDE[start:] if end == -1 else GUIDE[start:end]


def test_guide_names_the_public_hypothyroidism_ancillary_api_and_constants() -> None:
    section = _hypothyroidism_section()
    for symbol in (
        "PediatricHypothyroidismAncillaryPolicy",
        "PediatricHypothyroidismAncillaryProjection",
        "PediatricHypothyroidismAncillaryValidationStatus",
        "PediatricHypothyroidismAncillaryCheck",
        "PediatricHypothyroidismAncillaryValidationReport",
        "project_pediatric_hypothyroidism_ancillary_resources",
        "validate_pediatric_hypothyroidism_ancillary_resources",
    ):
        assert symbol in section, f"guide is missing public API symbol: {symbol}"

    for term in (
        "SYN-PEDIATRIC-HYPOTHYROIDISM",
        "SYN-HYPOTHYROIDISM-TSH",
        "SYN-HYPOTHYROIDISM-FREE-T4",
        'result_flag="Synthetic"',
        "Synthetic Pediatric Endocrinology",
        "Synthetic levothyroxine",
        'med_record_type="Internal"',
    ):
        assert term in section, f"guide is missing fictional contract term: {term}"


def test_guide_states_in_memory_schema_and_causal_treatment_contract() -> None:
    section = _hypothyroidism_section()
    for term in (
        "exact descriptor schema",
        "in-memory",
        "evaluator-only",
        "visible `recognition`",
        "one `referrals`",
        "visible `workup`",
        "two `labs`",
        "visible `diagnosis`",
        "one `problem_list`",
        "hidden `treatment_start`",
        "at or after",
        "one medication",
        "hidden treatment alone never creates a medication",
        "fictional",
        "not ICD",
        "LOINC",
        "RxNorm",
        "clinical claim",
    ):
        assert term in section, f"guide is missing semantic contract term: {term}"


def test_guide_preserves_deferred_boundaries_and_readme_links_the_slice() -> None:
    section = _hypothyroidism_section().lower()
    for term in (
        "runtime",
        "package",
        "prevalence",
        "demographic calibration",
        "privacy",
        "non-matchability",
        "clinical review",
        "release",
        "real",
        "held-out",
        "synthea",
    ):
        assert term in section, f"guide is missing deferred boundary: {term}"

    assert "[synthetic generator guide](docs/synthetic-generator.md)" in README
    assert (
        "docs/superpowers/plans/2026-09-02-pediatric-hypothyroidism-ancillary-pathway.md"
        in README
    )
    assert (
        "docs/superpowers/specs/2026-09-02-pediatric-hypothyroidism-ancillary-pathway-design.md"
        in README
    )
    assert sum(
        "pediatric-hypothyroidism" in line.lower() for line in README.splitlines()
    ) == 1

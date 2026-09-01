from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]
GUIDE = (ROOT / "docs" / "synthetic-generator.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def _ghd_section() -> str:
    start = GUIDE.index("## Evaluator-only GHD ancillary pathway")
    end = GUIDE.index("## Exact-schema observed-resource package export", start)
    return GUIDE[start:end]


def test_guide_documents_the_evaluator_only_ghd_ancillary_contract() -> None:
    guide = _ghd_section()
    required = (
        "GhdAncillaryPolicy",
        "AncillaryResourceProjection",
        "AncillaryValidationReport",
        "project_ghd_ancillary_resources",
        "validate_ghd_ancillary_resources",
        "labs",
        "medications",
        "problem_list",
        "referrals",
        "SYN-GHD",
        "SYN-GHD-IGF1",
        "SYN-GHD-STIM",
        "Synthetic Pediatric Endocrinology",
        "Synthetic growth hormone",
        'result_flag="Synthetic"',
        'med_record_type="Internal"',
        "hidden",
        "treatment_start",
        "visible diagnosis",
        "result_delay_days",
        "PASS",
        "FAIL",
        "UNEVALUABLE",
        "exact descriptor order",
        "empty string",
        "evaluator-only",
        "in-memory",
        "deterministic",
    )
    for term in required:
        assert term in guide, f"GHD section is missing required contract term: {term}"


def test_guide_preserves_all_deferred_boundaries() -> None:
    guide = _ghd_section()
    for term in (
        "ObservedResourceBundle",
        "complete package export",
        "augmented derivation",
        "other disorders",
        "prevalence",
        "held-out validation",
        "privacy",
        "non-matchability",
        "clinical review",
        "task utility",
        "release",
        "Synthea",
        "fail-closed",
    ):
        assert term in guide, f"GHD section is missing deferred boundary: {term}"


def test_guide_states_exact_ghd_timing_and_aggregate_contract() -> None:
    guide = _ghd_section()
    for phrase in (
        "first visible `recognition` event",
        "first `workup`",
        "first visible\n`diagnosis`",
        "hidden\n`treatment_start`",
        "only after visible diagnosis",
        "hidden treatment alone never creates a visible row",
        "delayed by `policy.result_delay_days`",
        "`shape.field_names(resource)` in exact descriptor order",
        'empty string (empty-string) convention (`""`)',
        "`FAIL` wins over `UNEVALUABLE`, which wins\nover `PASS`",
    ):
        assert phrase in guide, f"GHD section is missing exact semantic: {phrase}"


def test_readme_links_the_dedicated_synthetic_generator_guide() -> None:
    assert "[synthetic generator guide](docs/synthetic-generator.md)" in README

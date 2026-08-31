from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]
GUIDE = (ROOT / "docs" / "synthetic-generator.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_guide_documents_the_evaluator_only_ghd_ancillary_contract() -> None:
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
        assert term in GUIDE, f"guide is missing required contract term: {term}"


def test_guide_preserves_all_deferred_boundaries() -> None:
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
        assert term in GUIDE, f"guide is missing deferred boundary: {term}"


def test_readme_links_guide_without_overclaiming_ghd_pathway() -> None:
    assert "docs/synthetic-generator.md#evaluator-only-ghd-ancillary-pathway" in README
    assert "GHD ancillary" in README
    paragraph_start = README.index("GHD ancillary")
    paragraph = README[paragraph_start : paragraph_start + 2000]
    for term in (
        "evaluator-only",
        "package",
        "prevalence",
        "clinical",
        "privacy",
        "non-matchability",
        "derivation",
        "release",
        "Synthea",
    ):
        assert term.lower() in paragraph.lower(), f"README GHD roadmap must defer {term}"

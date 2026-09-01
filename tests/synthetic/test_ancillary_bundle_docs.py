from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]
GUIDE = (ROOT / "docs" / "synthetic-generator.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def _section() -> str:
    start = GUIDE.index("### In-memory GHD ancillary bundle integration")
    end = GUIDE.index("## Exact-schema observed-resource package export", start)
    return GUIDE[start:end]


def test_guide_documents_the_exact_in_memory_ancillary_bundle_api_and_preconditions() -> None:
    section = _section()
    for term in (
        "merge_ghd_ancillary_resources",
        "validate_ghd_ancillary_bundle",
        "AncillaryBundleValidationStatus",
        "AncillaryBundleValidationReport",
        "ObservedResourceBundle",
        "CohortMember",
        "AncillaryResourceProjection",
        "GhdAncillaryPolicy",
        "typed in-memory",
        "empty",
        "labs",
        "medications",
        "problem_list",
        "referrals",
        "fresh",
        "immutable",
        "six-resource",
        "bundle_identity",
        "base_resources",
        "ancillary_resources",
        "truth_boundary",
    ):
        assert term in section, f"bundle-integration section is missing {term}"


def test_guide_explains_validation_boundaries_and_deferred_claims() -> None:
    section = _section()
    for term in (
        "validate_observed_resources",
        "reject",
        "nonempty ancillary",
        "malformed",
        "UNEVALUABLE",
        "visible",
        "FAIL",
        "evaluator-only",
        "synthetic-only",
        "no file",
        "package/file export",
        "augmented derivation",
        "paired counterfactual worlds",
        "prevalence",
        "demographic",
        "held-out",
        "clinical",
        "task utility",
        "privacy",
        "non-matchability",
        "release approval",
        "other disorders",
        "Synthea",
    ):
        assert term in section, f"bundle-integration section is missing deferred boundary {term}"


def test_readme_links_the_dedicated_synthetic_generator_guide() -> None:
    assert "[synthetic generator guide](docs/synthetic-generator.md)" in README

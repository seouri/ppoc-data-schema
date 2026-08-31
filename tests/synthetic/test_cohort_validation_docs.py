from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "synthetic-generator.md"
README = ROOT / "README.md"


def test_profile_guide_documents_the_exact_api_and_status_contract() -> None:
    """Catches a profile report that is shipped without its callable contract."""
    guide = GUIDE.read_text(encoding="utf-8")

    for required in (
        "validate_native_cohort",
        "CohortValidationPolicy",
        "CohortValidationReport",
        "CohortValidationStatus",
        "required_age_windows",
        "growth_tolerances",
        "PASS",
        "FAIL",
        "UNEVALUABLE",
    ):
        assert required in guide


def test_profile_guide_documents_separate_layers_and_visible_category_projection() -> None:
    """Catches documentation collapsing latent, observable, and recorded evidence."""
    guide = GUIDE.read_text(encoding="utf-8")

    for required in (
        "latent module",
        "observable phenotype",
        "recorded recognition",
        "recorded workup",
        "recorded diagnosis",
        "blank/nonresponse",
        "`Unknown`",
        "growth summaries",
        "height_z_score",
        "bmi_z_score",
        "height_velocity_cm_per_year",
        "weight_velocity_kg_per_year",
        "evaluator-only",
        "aggregate-only",
    ):
        assert required in guide


def test_profile_documentation_names_every_deferred_claim_boundary() -> None:
    """Catches a profile report being presented as evidence it cannot establish."""
    guide = GUIDE.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")

    for document in (guide, readme):
        for deferred in (
            "prevalence",
            "held-out",
            "clinical",
            "privacy",
            "non-matchability",
            "package",
            "Synthea",
        ):
            assert deferred in document


def test_readme_links_the_native_cohort_profile_report_guide() -> None:
    """Catches a public roadmap that omits the new evaluator entry point."""
    readme = README.read_text(encoding="utf-8")

    assert "validate_native_cohort" in readme
    assert "docs/synthetic-generator.md#evaluator-only-native-cohort-fidelity-profile" in readme

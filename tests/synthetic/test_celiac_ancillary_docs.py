from __future__ import annotations

from pathlib import Path

from synthetic.native.celiac_ancillary import (
    CELIAC_ANCILLARY_RESOURCE_NAMES,
    CELIAC_DIAGNOSIS_CODE,
    CELIAC_LAB_RESULT_FLAG,
    CELIAC_MEDICATION_NAME,
    CELIAC_MEDICATION_RECORD_TYPE,
    CELIAC_REFERRAL_SPECIALTY,
    CELIAC_TOTAL_IGA_COMPONENT,
    CELIAC_TTG_IGA_COMPONENT,
)

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "synthetic-generator.md"
README = ROOT / "README.md"
SECTION_HEADING = "## Evaluator-only celiac ancillary pathway\n"


def _section() -> str:
    guide = GUIDE.read_text(encoding="utf-8")
    assert SECTION_HEADING in guide, "celiac ancillary guide section is missing"
    return guide.split(SECTION_HEADING, maxsplit=1)[1].split("\n## ", maxsplit=1)[0]


def test_guide_names_the_public_api_and_exact_fictional_contract() -> None:
    section = _section()

    for api_name in (
        "CeliacAncillaryPolicy",
        "CeliacAncillaryProjection",
        "CeliacAncillaryProjectionUnavailable",
        "CeliacAncillaryValidationStatus",
        "CeliacAncillaryCheck",
        "CeliacAncillaryValidationReport",
        "project_celiac_ancillary_resources",
        "validate_celiac_ancillary_resources",
    ):
        assert api_name in section
    for resource_name in CELIAC_ANCILLARY_RESOURCE_NAMES:
        assert f"`{resource_name}`" in section
    for constant_name in (
        "CELIAC_DIAGNOSIS_CODE",
        "CELIAC_TTG_IGA_COMPONENT",
        "CELIAC_TOTAL_IGA_COMPONENT",
        "CELIAC_LAB_RESULT_FLAG",
        "CELIAC_REFERRAL_SPECIALTY",
        "CELIAC_MEDICATION_NAME",
        "CELIAC_MEDICATION_RECORD_TYPE",
    ):
        assert constant_name in section
    for value in (
        CELIAC_DIAGNOSIS_CODE,
        CELIAC_TTG_IGA_COMPONENT,
        CELIAC_TOTAL_IGA_COMPONENT,
        CELIAC_REFERRAL_SPECIALTY,
        CELIAC_MEDICATION_NAME,
    ):
        assert f"`{value}`" in section
    assert f'`result_flag="{CELIAC_LAB_RESULT_FLAG}"`' in section
    assert f'`med_record_type="{CELIAC_MEDICATION_RECORD_TYPE}"`' in section


def test_guide_states_the_exact_schema_in_memory_and_causal_boundaries() -> None:
    section = _section()

    for boundary in (
        "accept only typed in-memory values",
        "exact-schema",
        "immutable",
        "evaluator-only",
        "recognition",
        "one `referrals`",
        "workup",
        "two serology",
        "diagnosis",
        "unresolved",
        "hidden `treatment_start`",
        "hidden treatment alone",
        "treatment before a censored diagnosis",
    ):
        assert boundary in section


def test_guide_separates_fictional_latent_state_and_non_target_output() -> None:
    section = _section().lower()

    for term in (
        "fictional/nonclinical",
        "make no icd",
        "loinc",
        "rxnorm",
        "latent state remains hidden",
        "healthy",
        "all other disorder kinds return empty tuples",
        "does not write or infer `obesity_flag`",
    ):
        assert term in section


def test_guide_keeps_deferred_evidence_and_release_boundaries_explicit() -> None:
    section = _section().lower()

    for deferred_topic in (
        "runtime/package integration",
        "prevalence/demographic calibration",
        "privacy/non-matchability",
        "clinical review",
        "release authorization",
        "real or held-out data",
        "synthea conformance",
    ):
        assert deferred_topic in section
    assert "remain deferred" in section
    assert "not ordinary-development prerequisites" in section


def test_readme_links_the_celiac_slice_without_copying_the_guide() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "[synthetic generator guide](docs/synthetic-generator.md)" in readme
    assert "excess-weight ancillary pathway is a separate roadmap slice" in readme
    assert (
        "docs/superpowers/plans/2026-09-02-celiac-ancillary-pathway.md"
        in readme
    )
    assert (
        "docs/superpowers/specs/2026-09-02-celiac-ancillary-pathway-design.md"
        in readme
    )
    assert "The evaluator-only celiac ancillary pathway is a separate roadmap slice" in readme
    assert "SYN-CELIAC-DISEASE" not in readme
    assert "Synthetic Pediatric Gastroenterology" not in readme

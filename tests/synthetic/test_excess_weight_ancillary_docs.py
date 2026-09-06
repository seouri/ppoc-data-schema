from __future__ import annotations

from pathlib import Path

from synthetic.native.excess_weight_ancillary import (
    EXCESS_WEIGHT_A1C_COMPONENT,
    EXCESS_WEIGHT_ANCILLARY_RESOURCE_NAMES,
    EXCESS_WEIGHT_DIAGNOSIS_CODE,
    EXCESS_WEIGHT_LAB_RESULT_FLAG,
    EXCESS_WEIGHT_LIPID_COMPONENT,
    EXCESS_WEIGHT_REFERRAL_SPECIALTY,
)

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "synthetic-generator.md"
README = ROOT / "README.md"
SECTION_HEADING = "## Evaluator-only excess-weight ancillary pathway\n"


def _section() -> str:
    guide = GUIDE.read_text(encoding="utf-8")
    assert SECTION_HEADING in guide, "excess-weight ancillary guide section is missing"
    return guide.split(SECTION_HEADING, maxsplit=1)[1].split("\n## ", maxsplit=1)[0]


def test_guide_names_the_evaluator_api_shape_and_exact_fictional_constants() -> None:
    section = _section()

    for api_name in (
        "ExcessWeightAncillaryPolicy",
        "ExcessWeightAncillaryProjection",
        "ExcessWeightAncillaryProjectionUnavailable",
        "ExcessWeightAncillaryCheck",
        "ExcessWeightAncillaryValidationStatus",
        "ExcessWeightAncillaryValidationReport",
        "project_excess_weight_ancillary_resources",
        "validate_excess_weight_ancillary_resources",
    ):
        assert api_name in section
    for resource_name in EXCESS_WEIGHT_ANCILLARY_RESOURCE_NAMES:
        assert f"`{resource_name}`" in section
    for constant_name in (
        "EXCESS_WEIGHT_DIAGNOSIS_CODE",
        "EXCESS_WEIGHT_LIPID_COMPONENT",
        "EXCESS_WEIGHT_A1C_COMPONENT",
        "EXCESS_WEIGHT_REFERRAL_SPECIALTY",
        "EXCESS_WEIGHT_LAB_RESULT_FLAG",
    ):
        assert constant_name in section
    for value in (
        EXCESS_WEIGHT_DIAGNOSIS_CODE,
        EXCESS_WEIGHT_LIPID_COMPONENT,
        EXCESS_WEIGHT_A1C_COMPONENT,
        EXCESS_WEIGHT_REFERRAL_SPECIALTY,
    ):
        assert f"`{value}`" in section
    assert f'`result_flag="{EXCESS_WEIGHT_LAB_RESULT_FLAG}"`' in section


def test_guide_preserves_the_exact_schema_and_in_memory_boundary() -> None:
    section = _section()

    for boundary in (
        "evaluator-only",
        "in-memory",
        "exact-schema",
        "CohortMember",
        "ResourceShape",
        "descriptor field order",
        "immutable",
        "descriptor path",
        "CSV",
        "package writer",
        "CLI",
        "governed input",
    ):
        assert boundary in section


def test_guide_documents_recorded_descendants_and_never_maps_treatment_to_medication() -> None:
    section = _section()

    assert "recognition" in section and "`referrals`" in section
    assert "workup" in section and "`labs`" in section
    assert "diagnosis" in section and "`problem_list`" in section
    assert "The `medications` tuple is always empty" in section
    assert "latent `treatment_start`" in section
    assert "no visible medication row" in section
    assert "Hidden or unrecorded events never create visible descendants" in section


def test_guide_separates_latent_excess_weight_from_observed_obesity_flag() -> None:
    section = _section()

    assert "`EXCESS_WEIGHT` is evaluator-only" in section
    assert "neither implies nor writes `obesity_flag`" in section
    assert "separately derived from observed BMI percentile" in section


def test_guide_keeps_optional_evidence_and_release_claims_deferred() -> None:
    section = _section()

    for deferred_topic in (
        "prevalence",
        "privacy/non-matchability",
        "clinical validity",
        "release authorization",
        "Synthea conformance",
    ):
        assert deferred_topic in section
    assert "remain deferred" in section


def test_readme_links_the_guide_and_marks_the_pathway_as_a_roadmap_slice() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "[synthetic generator guide](docs/synthetic-generator.md)" in readme
    assert SECTION_HEADING in GUIDE.read_text(encoding="utf-8")

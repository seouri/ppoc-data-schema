from __future__ import annotations

from pathlib import Path

from synthetic.native.undernutrition_ancillary import (
    UNDERNUTRITION_ANCILLARY_RESOURCE_NAMES,
    UNDERNUTRITION_DIAGNOSIS_CODE,
    UNDERNUTRITION_HEIGHT_COMPONENT,
    UNDERNUTRITION_LAB_RESULT_FLAG,
    UNDERNUTRITION_MEDICATION_NAME,
    UNDERNUTRITION_MEDICATION_RECORD_TYPE,
    UNDERNUTRITION_REFERRAL_SPECIALTY,
    UNDERNUTRITION_WEIGHT_COMPONENT,
)

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "synthetic-generator.md"
README = ROOT / "README.md"
SECTION_HEADING = "## Evaluator-only undernutrition ancillary pathway\n"


def _section() -> str:
    guide = GUIDE.read_text(encoding="utf-8")
    assert SECTION_HEADING in guide, "undernutrition ancillary guide section is missing"
    return guide.split(SECTION_HEADING, maxsplit=1)[1].split("\n## ", maxsplit=1)[0]


def test_guide_names_the_public_api_and_exact_fictional_contract() -> None:
    section = _section()

    for api_name in (
        "UndernutritionAncillaryPolicy",
        "UndernutritionAncillaryProjection",
        "UndernutritionAncillaryProjectionUnavailable",
        "UndernutritionAncillaryValidationStatus",
        "UndernutritionAncillaryCheck",
        "UndernutritionAncillaryValidationReport",
        "project_undernutrition_ancillary_resources",
        "validate_undernutrition_ancillary_resources",
    ):
        assert api_name in section, f"guide is missing public API symbol: {api_name}"

    for resource_name in UNDERNUTRITION_ANCILLARY_RESOURCE_NAMES:
        assert f"`{resource_name}`" in section

    for constant_name in (
        "UNDERNUTRITION_DIAGNOSIS_CODE",
        "UNDERNUTRITION_WEIGHT_COMPONENT",
        "UNDERNUTRITION_HEIGHT_COMPONENT",
        "UNDERNUTRITION_LAB_RESULT_FLAG",
        "UNDERNUTRITION_REFERRAL_SPECIALTY",
        "UNDERNUTRITION_MEDICATION_NAME",
        "UNDERNUTRITION_MEDICATION_RECORD_TYPE",
    ):
        assert constant_name in section

    for value in (
        UNDERNUTRITION_DIAGNOSIS_CODE,
        UNDERNUTRITION_WEIGHT_COMPONENT,
        UNDERNUTRITION_HEIGHT_COMPONENT,
        UNDERNUTRITION_REFERRAL_SPECIALTY,
        UNDERNUTRITION_MEDICATION_NAME,
        "undernutrition-ancillary-id-v1",
    ):
        assert f"`{value}`" in section
    assert f'`result_flag="{UNDERNUTRITION_LAB_RESULT_FLAG}"`' in section
    assert f'`med_record_type="{UNDERNUTRITION_MEDICATION_RECORD_TYPE}"`' in section


def test_guide_states_schema_source_and_link_boundaries() -> None:
    section = _section()

    for term in (
        "typed `CohortMember`",
        "`ResourceShape`",
        "exact-schema",
        "in-memory",
        "evaluator-only",
        "four named resource shapes",
        "descriptor field order",
        "empty-string missing-value conventions",
        "`UndernutritionModule`",
        "weight/BMI-first decline",
        "delayed height effect",
        "optional partial recovery",
        "hidden upstream state",
        "source-point visit link",
    ):
        assert term in section, f"guide is missing boundary term: {term}"


def test_guide_documents_descendants_treatment_gating_and_empty_non_targets() -> None:
    section = _section()

    for term in (
        "visible `recognition`",
        "one `referrals`",
        "visible `workup`",
        "two `labs` per workup",
        "visible `diagnosis`",
        "one unresolved `problem_list`",
        "private `treatment_start`",
        "one medication",
        "diagnosis is absent, censored, or later than treatment",
        "response/nonresponse creates no row",
        "fictional nutrition-supplement",
        "no `obesity_flag`",
        "every non-undernutrition member",
        "four empty tuples",
    ):
        assert term in section, f"guide is missing pathway term: {term}"


def test_guide_keeps_fictional_labels_and_deferred_work_explicit() -> None:
    section = _section().lower()

    for term in (
        "fictional rather than clinical terminology",
        "not icd",
        "loinc",
        "rxnorm",
        "runtime/package integration",
        "prevalence/demographic calibration",
        "privacy/non-matchability",
        "clinical/nutrition/release claims",
        "real or held-out data",
        "dedicated resource/terminology expansion",
        "optional synthea conformance",
    ):
        assert term in section, f"guide is missing deferred boundary: {term}"
    assert "remain deferred" in section
    assert "not ordinary-development prerequisites" in section


def test_readme_links_the_undernutrition_slice_without_copying_the_guide() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "[synthetic generator guide](docs/synthetic-generator.md)" in readme
    assert (
        "docs/superpowers/plans/2026-09-02-undernutrition-ancillary-pathway.md"
        in readme
    )
    assert (
        "docs/superpowers/specs/2026-09-02-undernutrition-ancillary-pathway-design.md"
        in readme
    )
    assert (
        "The evaluator-only undernutrition ancillary pathway is a separate roadmap "
        "slice"
    ) in readme
    assert "SYN-UNDERNUTRITION" not in readme
    assert "Synthetic Pediatric Nutrition" not in readme
    assert "UndernutritionAncillaryPolicy" not in readme

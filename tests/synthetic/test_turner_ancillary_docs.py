from __future__ import annotations

from pathlib import Path

from synthetic.native.turner_ancillary import (
    TURNER_ANCILLARY_RESOURCE_NAMES,
    TURNER_DIAGNOSIS_CODE,
    TURNER_ENDOCRINE_EVIDENCE_COMPONENT,
    TURNER_KARYOTYPE_COMPONENT,
    TURNER_LAB_RESULT_FLAG,
    TURNER_MEDICATION_NAME,
    TURNER_MEDICATION_RECORD_TYPE,
    TURNER_REFERRAL_SPECIALTY,
)

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "synthetic-generator.md"
README = ROOT / "README.md"
SECTION_HEADING = "## Evaluator-only Turner ancillary pathway\n"


def _section() -> str:
    guide = GUIDE.read_text(encoding="utf-8")
    assert SECTION_HEADING in guide, "Turner ancillary guide section is missing"
    return guide.split(SECTION_HEADING, maxsplit=1)[1].split("\n## ", maxsplit=1)[0]


def test_guide_names_the_public_api_and_exact_fictional_contract() -> None:
    section = _section()

    for api_name in (
        "TurnerAncillaryPolicy",
        "TurnerAncillaryProjection",
        "TurnerAncillaryProjectionUnavailable",
        "TurnerAncillaryValidationStatus",
        "TurnerAncillaryCheck",
        "TurnerAncillaryValidationReport",
        "project_turner_ancillary_resources",
        "validate_turner_ancillary_resources",
    ):
        assert api_name in section, f"guide is missing public API symbol: {api_name}"

    for resource_name in TURNER_ANCILLARY_RESOURCE_NAMES:
        assert f"`{resource_name}`" in section

    for constant_name in (
        "TURNER_DIAGNOSIS_CODE",
        "TURNER_KARYOTYPE_COMPONENT",
        "TURNER_ENDOCRINE_EVIDENCE_COMPONENT",
        "TURNER_LAB_RESULT_FLAG",
        "TURNER_REFERRAL_SPECIALTY",
        "TURNER_MEDICATION_NAME",
        "TURNER_MEDICATION_RECORD_TYPE",
    ):
        assert constant_name in section

    for value in (
        TURNER_DIAGNOSIS_CODE,
        TURNER_KARYOTYPE_COMPONENT,
        TURNER_ENDOCRINE_EVIDENCE_COMPONENT,
        TURNER_REFERRAL_SPECIALTY,
        TURNER_MEDICATION_NAME,
        "turner-ancillary-id-v1",
    ):
        assert f"`{value}`" in section
    assert f'`result_flag="{TURNER_LAB_RESULT_FLAG}"`' in section
    assert f'`med_record_type="{TURNER_MEDICATION_RECORD_TYPE}"`' in section


def test_guide_states_exact_schema_typed_in_memory_and_upstream_boundaries() -> None:
    section = _section()
    for term in (
        "typed `CohortMember`",
        "`ResourceShape`",
        "exact-schema",
        "in-memory",
        "evaluator-only",
        "four named resource shapes",
        "descriptor field order",
        "empty-string missing-value",
        'reference_sex="F"',
        "female-reference",
        "recorded sex is not used to infer reference eligibility",
        "no birth-state deficit",
        "source-point",
        "visit link",
    ):
        assert term in section, f"guide is missing boundary term: {term}"


def test_guide_documents_visible_descendants_hidden_treatment_and_empty_non_targets() -> None:
    section = _section()
    for term in (
        "visible `recognition`",
        "one `referrals`",
        "visible `workup`",
        "two `labs`",
        "visible `diagnosis`",
        "one unresolved `problem_list`",
        "private `treatment_start`",
        "one medication",
        "treatment suppression",
        "diagnosis is absent or censored",
        "response event",
        "no response event",
        "no `obesity_flag`",
        "four empty tuples",
        "every non-Turner member",
    ):
        assert term in section, f"guide is missing pathway term: {term}"


def test_guide_keeps_fictional_labels_and_deferred_work_explicit() -> None:
    section = _section().lower()

    for term in (
        "fictional",
        "not icd",
        "loinc",
        "rxnorm",
        "runtime/package integration",
        "prevalence/demographic calibration",
        "privacy/non-matchability",
        "clinical/release claims",
        "real or held-out data",
        "optional synthea conformance",
    ):
        assert term in section, f"guide is missing deferred boundary: {term}"
    assert "remain deferred" in section
    assert "not ordinary-development prerequisites" in section


def test_readme_links_the_turner_roadmap_slice_without_copying_the_guide() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "[synthetic generator guide](docs/synthetic-generator.md)" in readme
    assert (ROOT / "docs/superpowers/plans"
            / "2026-09-02-turner-ancillary-pathway.md").is_file()
    assert (ROOT / "docs/superpowers/specs"
            / "2026-09-02-turner-ancillary-pathway-design.md").is_file()
    assert "SYN-TURNER" not in readme
    assert "Synthetic Pediatric Endocrinology" not in readme
    assert "TurnerAncillaryPolicy" not in readme

from __future__ import annotations

from pathlib import Path

from synthetic.native.sga_ancillary import (
    SGA_ANCILLARY_RESOURCE_NAMES,
    SGA_BIRTH_SIZE_COMPONENT,
    SGA_DIAGNOSIS_CODE,
    SGA_GESTATIONAL_AGE_COMPONENT,
    SGA_LAB_RESULT_FLAG,
    SGA_REFERRAL_SPECIALTY,
)

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "synthetic-generator.md"
README = ROOT / "README.md"
SECTION_HEADING = "## Evaluator-only SGA ancillary pathway\n"


def _section() -> str:
    guide = GUIDE.read_text(encoding="utf-8")
    assert SECTION_HEADING in guide, "SGA ancillary guide section is missing"
    return guide.split(SECTION_HEADING, maxsplit=1)[1].split("\n## ", maxsplit=1)[0]


def test_guide_names_the_public_api_and_exact_fictional_contract() -> None:
    section = _section()

    for api_name in (
        "SgaAncillaryPolicy",
        "SgaAncillaryProjection",
        "SgaAncillaryProjectionUnavailable",
        "SgaAncillaryValidationStatus",
        "SgaAncillaryCheck",
        "SgaAncillaryValidationReport",
        "project_sga_ancillary_resources",
        "validate_sga_ancillary_resources",
    ):
        assert api_name in section
    for resource_name in SGA_ANCILLARY_RESOURCE_NAMES:
        assert f"`{resource_name}`" in section
    for constant_name in (
        "SGA_DIAGNOSIS_CODE",
        "SGA_GESTATIONAL_AGE_COMPONENT",
        "SGA_BIRTH_SIZE_COMPONENT",
        "SGA_LAB_RESULT_FLAG",
        "SGA_REFERRAL_SPECIALTY",
    ):
        assert constant_name in section
    for value in (
        SGA_DIAGNOSIS_CODE,
        SGA_GESTATIONAL_AGE_COMPONENT,
        SGA_BIRTH_SIZE_COMPONENT,
        SGA_REFERRAL_SPECIALTY,
        "sga-ancillary-id-v1",
    ):
        assert f"`{value}`" in section
    assert f'`result_flag="{SGA_LAB_RESULT_FLAG}"`' in section


def test_guide_states_in_memory_exact_schema_and_event_contract() -> None:
    section = _section()

    for term in (
        "typed in-memory",
        "exact-schema",
        "immutable",
        "evaluator-only",
        "descriptor field order",
        "recognition",
        "one `referrals`",
        "workup",
        "two `labs`",
        "diagnosis",
        "one unresolved `problem_list`",
        "no dedicated gestational-age resource",
        "empty values",
        "The `medications` tuple is always empty",
        "no visible medication row",
    ):
        assert term in section


def test_guide_keeps_hidden_state_and_nonclinical_boundaries_explicit() -> None:
    section = _section().lower()

    for term in (
        "birth-state",
        "catch-up",
        "persistent",
        "remains hidden",
        "fictional/nonclinical",
        "make no icd",
        "loinc",
        "rxnorm",
        "healthy",
        "all other disorder kinds return empty tuples",
        "does not write or derive `obesity_flag`",
    ):
        assert term in section


def test_guide_defers_runtime_evidence_and_release_boundaries() -> None:
    section = _section().lower()

    for deferred_topic in (
        "runtime/package integration",
        "prevalence/demographic calibration",
        "privacy/non-matchability",
        "clinical review",
        "release authorization",
        "real or held-out data",
        "gestational-age resource expansion",
        "synthea conformance",
    ):
        assert deferred_topic in section
    assert "remain deferred" in section
    assert "not ordinary-development prerequisites" in section


def test_readme_links_the_sga_roadmap_slice_without_copying_the_guide() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "[synthetic generator guide](docs/synthetic-generator.md)" in readme
    assert "excess-weight ancillary pathway is a separate roadmap slice" in readme
    assert (
        "docs/superpowers/plans/2026-09-02-sga-ancillary-pathway.md" in readme
    )
    assert (
        "docs/superpowers/specs/2026-09-02-sga-ancillary-pathway-design.md"
        in readme
    )
    assert "The evaluator-only SGA ancillary pathway is a separate roadmap slice" in readme
    assert "SYN-SGA" not in readme
    assert "Synthetic Neonatology Follow-up" not in readme

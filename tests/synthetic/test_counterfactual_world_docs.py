from pathlib import Path

ROOT = Path(__file__).parents[2]
GUIDE = (ROOT / "docs" / "synthetic-generator.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def _section() -> str:
    start = GUIDE.index("## In-memory paired counterfactual EHR worlds")
    end = GUIDE.index("## Exact-schema observed-resource package export", start)
    return GUIDE[start:end]


def test_guide_documents_the_typed_in_memory_paired_world_api_and_usage() -> None:
    section = _section()
    for term in (
        "CounterfactualEhrWorldPair",
        "CounterfactualWorldValidationStatus",
        "assemble_counterfactual_ehr_worlds",
        "validate_counterfactual_ehr_worlds",
        "CounterfactualPair",
        "SyntheticDemographics",
        "ObservationPolicy",
        "GhdAncillaryPolicy",
        "already-loaded descriptor mapping",
        "base-compatible",
        "length_availability_probability=0.0",
        "observed `LENGTH`",
        "cannot project",
        "NamedRandomStreams",
        "same seed and patient index",
        "deterministic",
        "in-memory",
    ):
        assert term in section, f"paired-world section is missing {term}"
    assert "baseline_context" not in section
    assert "intervention_context" not in section


def test_guide_documents_fixed_aggregate_validation_and_visible_change_matrix() -> None:
    section = _section()
    for term in (
        "pair_binding",
        "shared_demographics",
        "shared_observation",
        "observation_invariants",
        "resource_invariants",
        "permitted_changes",
        "truth_boundary",
        "PASS",
        "FAIL",
        "UNEVALUABLE",
        "FAIL > UNEVALUABLE > PASS",
        "PHYSIOLOGY_SEVERITY",
        "EARLIER_RECOGNITION",
        "TREATMENT_ADHERENCE",
        "growth measurement values",
        "visible event trace",
        "ancillary",
        "treatment_start",
        "redacted",
    ):
        assert term in section, f"paired-world validation contract is missing {term}"


def test_guide_preserves_truth_boundary_and_explicit_deferrals() -> None:
    section = _section().lower()
    for term in (
        "hidden truth",
        "latent",
        "no file",
        "package",
        "cli",
        "real",
        "governed",
        "calibration",
        "held-out",
        "privacy",
        "model",
        "synthea",
        "pair-aware exact-schema export",
        "next gate",
        "optional later adapter",
        "prevalence",
        "demographic",
        "clinical",
        "task utility",
        "non-matchability",
    ):
        assert term in section, f"paired-world section is missing boundary {term}"


def test_readme_links_the_dedicated_synthetic_generator_guide() -> None:
    assert "[synthetic generator guide](docs/synthetic-generator.md)" in README

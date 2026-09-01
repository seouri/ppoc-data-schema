from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from synthetic.calibrate import (
    DEFAULT_AGE_WINDOWS,
    CalibrationRunConfig,
    PartitionPolicy,
    calibrate,
    write_calibration_result,
)
from synthetic.calibration import CalibrationDisclosurePolicy
from synthetic.calibration_targets import (
    ETHNICITY_CATEGORY_SLUGS,
    RACE_CATEGORY_SLUGS,
    RECORDED_FLAGS,
    SEX_CATEGORY_SLUGS,
    TARGET_REGISTRY_VERSION,
)
from synthetic.heldout_validate import FidelityPolicy, HeldoutComparison, HeldoutRunConfig
from synthetic.manifest import RunManifest
from synthetic.prevalence_evidence import (
    PrevalenceEvidenceConfig,
    PrevalenceEvidenceReport,
    PrevalenceEvidenceUnavailable,
    PrevalenceRunResult,
    PrevalenceRunSpec,
    evaluate_prevalence_evidence,
    verify_package_identity,
)
from synthetic.schema_contract import schema_fingerprint
from synthetic.validate import validate_structure
from tests.synthetic.calibration_fixtures import write_mock_snapshot
from tests.synthetic.heldout_fixtures import descriptor_for
from tests.synthetic.prevalence_evidence_fixtures import write_prevalence_package

ROOT = Path(__file__).resolve().parents[2]
PARTITION_KEY = b"0123456789abcdef"


def _required_v1_keys() -> tuple[tuple[str, str, str, str, str, None], ...]:
    dimensions = "outcome_layer=observed"
    return tuple(
        sorted(
            (
                *(
                    (dimensions, f"sex_{slug}", "demographics", "proportion", "proportion", None)
                    for slug in SEX_CATEGORY_SLUGS.values()
                ),
                (dimensions, "race_multiselect", "demographics", "proportion", "proportion", None),
                *(
                    (dimensions, f"ethnicity_{slug}", "demographics", "proportion", "proportion", None)
                    for slug in ETHNICITY_CATEGORY_SLUGS.values()
                ),
                *(
                    (dimensions, f"race_{slug}", "demographics", "proportion", "proportion", None)
                    for slug in RACE_CATEGORY_SLUGS.values()
                ),
                *(
                    (dimensions, flag, "recorded_outcome", "proportion", "proportion", None)
                    for flag in RECORDED_FLAGS.values()
                ),
            )
        )
    )


def _passing_comparison(key: tuple[str, str, str, str, str, None]) -> HeldoutComparison:
    return HeldoutComparison(*key, "PASS", 0.5, 0.5, 0.0, 1.0)


def _controlled_heldout_result(
    template: HeldoutRunConfig,
    *,
    omit: tuple[str, str, str, str, str, None] | None = None,
    include_diagnostics: bool = False,
) -> SimpleNamespace:
    comparisons = tuple(key for key in _required_v1_keys() if key != omit)
    heldout_comparisons = tuple(_passing_comparison(key) for key in comparisons)
    if include_diagnostics:
        heldout_comparisons += (
            HeldoutComparison(
                "age_regime=infant",
                "weight_available",
                "observation",
                "proportion",
                "proportion",
                None,
                "FAIL",
                0.0,
                1.0,
                1.0,
                0.0,
            ),
            HeldoutComparison(
                "outcome_layer=observed",
                "diagnosis_age_years_mean",
                "recorded_outcome",
                "mean",
                "year",
                None,
                "FAIL",
                1.0,
                2.0,
                1.0,
                0.0,
            ),
            SimpleNamespace(
                stratum_id="outcome_layer=latent",
                target_name="synthetic_label",
                family="recorded_outcome",
                statistic="proportion",
                unit="proportion",
                quantile_level=None,
                status="FAIL",
            ),
        )
    report = SimpleNamespace(
        source_snapshot=template.source_snapshot,
        synthetic_artifact_id="synthetic-v1",
        schema_fingerprint="f" * 64,
        partition_policy=template.partition_policy.to_report_mapping(),
        disclosure_policy={
            "policy_id": template.disclosure_policy.policy_id,
            "policy_version": template.disclosure_policy.policy_version,
        },
        fidelity_policy=template.fidelity_policy,
        heldout_aggregate_sha256="a" * 64,
        synthetic_aggregate_sha256="b" * 64,
        comparisons=heldout_comparisons,
    )
    return SimpleNamespace(report=report)


def _partition_policy() -> PartitionPolicy:
    return PartitionPolicy("partition-v1", "1", "key-2026", 5_000, 2)


def _disclosure_policy() -> CalibrationDisclosurePolicy:
    return CalibrationDisclosurePolicy("disclosure-v1", "1", 1, 3)


def _fidelity_policy(**changes: object) -> FidelityPolicy:
    values: dict[str, object] = {
        "policy_id": "fidelity-v1",
        "policy_version": "1",
        "target_registry_version": TARGET_REGISTRY_VERSION,
        "minimum_evaluable_support": 1,
        "proportion_floor": 1.0,
        "proportion_z_score": 2.0,
        "continuous_tolerances": {
            "demographics": 100.0,
            "observation": 100.0,
            "physiology": 100.0,
            "utilization": 100.0,
            "recorded_outcome": 100.0,
        },
        "count_abs_tolerance": 10_000,
        "required_families": ["demographics", "recorded_outcome"],
        "max_unevaluable_targets": 0,
    }
    values.update(changes)
    return FidelityPolicy(**values)  # type: ignore[arg-type]


def _heldout_template(tmp_path: Path, *, policy: FidelityPolicy | None = None) -> HeldoutRunConfig:
    real_root = write_mock_snapshot(tmp_path / "real", id_prefix="REAL")
    disclosure_policy = _disclosure_policy()
    calibration = calibrate(
        CalibrationRunConfig(
            data_root=real_root,
            source_descriptor=ROOT / "datapackage.json",
            source_snapshot="snapshot-v1",
            artifact_id="synthetic-v1",
            created_at="2026-09-01T12:00:00Z",
            partition_policy=_partition_policy(),
            disclosure_policy=disclosure_policy,
            partition_key=PARTITION_KEY,
            age_windows=DEFAULT_AGE_WINDOWS,
        )
    )
    calibration_root = tmp_path / "calibration"
    write_calibration_result(calibration, calibration_root)
    return HeldoutRunConfig(
        real_root=real_root,
        real_descriptor=ROOT / "datapackage.json",
        source_snapshot="snapshot-v1",
        synthetic_root=tmp_path / "not-used-by-evidence",
        calibration_artifact=calibration_root / "calibration-artifact.json",
        calibration_report=calibration_root / "calibration-report.json",
        partition_policy=_partition_policy(),
        disclosure_policy=disclosure_policy,
        partition_key=PARTITION_KEY,
        fidelity_policy=policy or _fidelity_policy(),
        age_windows=DEFAULT_AGE_WINDOWS,
        output=tmp_path / "heldout-output-not-used",
    )


def _config(tmp_path: Path, *, policy: FidelityPolicy | None = None) -> PrevalenceEvidenceConfig:
    runs = tuple(
        PrevalenceRunSpec(write_prevalence_package(tmp_path / f"run-{seed}", seed=seed), seed)
        for seed in (101, 102, 103)
    )
    return PrevalenceEvidenceConfig(runs=runs, heldout_template=_heldout_template(tmp_path, policy=policy))


def _refresh_manifest(package: Path) -> None:
    """Rebind a wholly fictional package manifest after an intentional fixture mutation."""
    original = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    descriptor = dict(descriptor_for(package))
    structure = validate_structure(package, descriptor)
    assert not structure.errors
    hashes = {
        path.relative_to(package).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(package.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    manifest = RunManifest.generated(
        profile=original["profile"],
        seed=original["seed"],
        schema_fingerprint=schema_fingerprint(descriptor),
        reference_time=original["reference_time"],
        reference_id=original["reference_id"],
        reference_sha256=original["reference_sha256"],
        configuration_sha256=original["configuration_sha256"],
        software_revision=original["software_revision"],
        derivation_fingerprint=original["derivation_fingerprint"],
        test_only_derivation=False,
        row_counts=structure.row_counts,
        file_sha256=hashes,
    )
    (package / "manifest.json").write_bytes(manifest.to_json_bytes())


def _mutate_sex_to_female(package: Path) -> None:
    path = package / "patients.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = tuple(rows[0])
    for row in rows:
        row["sex"] = "F"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    _refresh_manifest(package)


def test_evidence_evaluates_only_observed_demographic_and_recorded_outcome_targets(
    tmp_path: Path,
) -> None:
    """Removing v1 filtering must make non-observed comparisons enter the public report."""
    report = evaluate_prevalence_evidence(_config(tmp_path))

    assert report.status == "UNEVALUABLE"
    assert tuple(run.identity.seed for run in report.runs) == (101, 102, 103)
    assert all(
        comparison.stratum_id == "outcome_layer=observed"
        and comparison.family in {"demographics", "recorded_outcome"}
        for comparison in report.comparisons
    )
    assert {comparison.family for comparison in report.comparisons} == {
        "demographics",
        "recorded_outcome",
    }
    assert tuple(comparison.canonical_key for comparison in report.comparisons) == tuple(
        sorted(comparison.canonical_key for comparison in report.comparisons)
    )
    public_report = report.to_mapping()
    assert str(tmp_path) not in str(public_report)
    assert [run["identity"]["package_sha256"] for run in public_report["runs"]] == [
        run.identity.package_sha256 for run in report.runs
    ]
    assert all(set(run) == {"identity", "status", "comparison_count"} for run in public_report["runs"])
    serialized_runs = json.dumps(public_report["runs"], sort_keys=True)
    for field in (
        "comparisons",
        "comparison_sha256",
        "heldout_value",
        "synthetic_value",
        "difference",
        "tolerance",
        "support",
        "denominator",
        "heldout_aggregate_sha256",
        "synthetic_aggregate_sha256",
    ):
        assert field not in serialized_runs


def test_public_run_mapping_cannot_commit_per_run_comparison_values(tmp_path: Path) -> None:
    """Adding a per-run comparison digest would create a hidden value commitment in public output."""
    report = evaluate_prevalence_evidence(_config(tmp_path))
    original_run = report.runs[0]
    original = next(item for item in original_run.comparisons if item.status == "PASS")
    replacement = HeldoutComparison(
        original.stratum_id,
        original.target_name,
        original.family,
        original.statistic,
        original.unit,
        original.quantile_level,
        "PASS",
        0.0,
        0.0,
        0.0,
        1.0,
    )
    altered = replace(
        original_run,
        comparisons=tuple(replacement if item == original else item for item in original_run.comparisons),
    )

    assert altered.to_mapping() == original_run.to_mapping()
    assert set(altered.to_mapping()) == {"identity", "status", "comparison_count"}


def test_evidence_uses_fail_over_unevaluable_over_pass_across_runs(tmp_path: Path) -> None:
    """Omitting a failed package from the aggregate would hide a prevalence failure."""
    config = _config(tmp_path, policy=_fidelity_policy(proportion_floor=0.0, proportion_z_score=0.000001))
    _mutate_sex_to_female(config.runs[-1].package_root)

    report = evaluate_prevalence_evidence(config)

    assert report.status == "FAIL"
    assert any(comparison.status == "FAIL" for comparison in report.comparisons)
    assert any(comparison.fail_count == 1 for comparison in report.comparisons)


def test_evidence_requires_each_v1_cell_to_be_evaluable(tmp_path: Path) -> None:
    """Dropping support below the frozen policy must make the evidence unevaluable."""
    report = evaluate_prevalence_evidence(
        _config(tmp_path, policy=_fidelity_policy(minimum_evaluable_support=1_000))
    )

    assert report.status == "UNEVALUABLE"
    assert all(comparison.status == "UNEVALUABLE" for comparison in report.comparisons)


def test_evidence_aggregation_is_independent_of_predeclared_run_order(tmp_path: Path) -> None:
    """Returning caller order instead of canonical seed order would change aggregate output bytes."""
    config = _config(tmp_path)

    forward = evaluate_prevalence_evidence(config)
    reverse = evaluate_prevalence_evidence(replace(config, runs=tuple(reversed(config.runs))))

    assert reverse.to_mapping() == forward.to_mapping()


def test_evidence_can_report_an_all_pass_complete_v1_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Treating an all-pass complete run set as unevaluable would break gate promotion."""
    config = _config(tmp_path)
    module = __import__("synthetic.prevalence_evidence", fromlist=["validate_heldout"])
    controlled = _controlled_heldout_result(config.heldout_template)
    monkeypatch.setattr(module, "validate_heldout", lambda _config: controlled)

    report = evaluate_prevalence_evidence(config)

    assert report.status == "PASS"
    assert len(report.comparisons) == len(_required_v1_keys())
    assert {comparison.status for comparison in report.comparisons} == {"PASS"}


def test_evidence_injects_a_globally_absent_required_v1_key_as_unevaluable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dropping a registered key from every run must not produce an all-pass report."""
    config = _config(tmp_path)
    module = __import__("synthetic.prevalence_evidence", fromlist=["validate_heldout"])
    omitted = _required_v1_keys()[0]
    controlled = _controlled_heldout_result(config.heldout_template, omit=omitted)
    monkeypatch.setattr(module, "validate_heldout", lambda _config: controlled)

    report = evaluate_prevalence_evidence(config)

    assert report.status == "UNEVALUABLE"
    comparison = next(item for item in report.comparisons if item.canonical_key == omitted)
    assert comparison.status == "UNEVALUABLE"
    assert comparison.evaluable_count == 0
    assert {run.status for run in report.runs} == {"UNEVALUABLE"}
    assert {run.to_mapping()["comparison_count"] for run in report.runs} == {
        len(_required_v1_keys())
    }


def test_evidence_publishes_the_worst_paired_tolerance_exceedance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Independently maximizing differences and tolerances can make a FAIL look within tolerance."""
    config = _config(tmp_path)
    module = __import__("synthetic.prevalence_evidence", fromlist=["validate_heldout"])
    target = _required_v1_keys()[0]
    variants = iter(
        (
            ("PASS", 0.46, 0.05),
            ("FAIL", 0.47, 0.02),
            ("PASS", 0.50, 0.01),
        )
    )

    def controlled(_config: HeldoutRunConfig) -> SimpleNamespace:
        status, synthetic_value, tolerance = next(variants)
        difference = abs(0.5 - synthetic_value)
        result = _controlled_heldout_result(config.heldout_template)
        replacement = HeldoutComparison(
            *target,
            status,
            0.5,
            synthetic_value,
            difference,
            tolerance,
        )
        result.report.comparisons = tuple(
            replacement
            if (
                item.stratum_id,
                item.target_name,
                item.family,
                item.statistic,
                item.unit,
                item.quantile_level,
            )
            == target
            else item
            for item in result.report.comparisons
        )
        return result

    monkeypatch.setattr(module, "validate_heldout", controlled)

    report = evaluate_prevalence_evidence(config)
    comparison = next(item for item in report.comparisons if item.canonical_key == target)

    assert comparison.status == "FAIL"
    assert comparison.maximum_absolute_difference == pytest.approx(0.04)
    assert comparison.maximum_tolerance_exceedance == pytest.approx(0.01)
    assert "tolerance" not in comparison.to_mapping()
    assert comparison.to_mapping()["maximum_tolerance_exceedance"] == pytest.approx(0.01)


def test_evidence_ignores_latent_and_observable_comparisons_from_a_controlled_heldout_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Letting non-observed diagnostics enter the report would make them gate prevalence."""
    config = _config(tmp_path)
    module = __import__("synthetic.prevalence_evidence", fromlist=["validate_heldout"])
    controlled = _controlled_heldout_result(config.heldout_template, include_diagnostics=True)
    monkeypatch.setattr(module, "validate_heldout", lambda _config: controlled)

    report = evaluate_prevalence_evidence(config)

    assert report.status == "PASS"
    assert all(item.family in {"demographics", "recorded_outcome"} for item in report.comparisons)
    assert all(not item.target_name.startswith("diagnosis_age_years_") for item in report.comparisons)


def test_report_rejects_aggregate_comparisons_that_do_not_match_run_evidence(tmp_path: Path) -> None:
    """Accepting supplied all-pass aggregates would hide a failing run-level comparison."""
    evaluated = evaluate_prevalence_evidence(_config(tmp_path))
    run = evaluated.runs[0]
    original = next(item for item in run.comparisons if item.status == "PASS")
    key = (
        original.stratum_id,
        original.target_name,
        original.family,
        original.statistic,
        original.unit,
        original.quantile_level,
    )
    assert original.heldout_value is not None
    synthetic_value = 0.0 if original.heldout_value else 1.0
    difference = abs(float(original.heldout_value) - synthetic_value)
    failing = HeldoutComparison(*key, "FAIL", original.heldout_value, synthetic_value, difference, 0.0)
    mismatched_run = replace(
        run,
        status="FAIL",
        comparisons=tuple(
            failing
            if (item.stratum_id, item.target_name, item.family, item.statistic, item.unit, item.quantile_level)
            == key
            else item
            for item in run.comparisons
        ),
    )

    with pytest.raises(ValueError, match="comparisons"):
        PrevalenceEvidenceReport(
            report_version=evaluated.report_version,
            status=evaluated.status,
            generation_identity=evaluated.generation_identity,
            heldout_identity=evaluated.heldout_identity,
            runs=(mismatched_run, *evaluated.runs[1:]),
            comparisons=evaluated.comparisons,
        )


def test_run_with_no_v1_comparisons_is_unevaluable(tmp_path: Path) -> None:
    """Treating an empty run comparison set as PASS would bypass the required-cell gate."""
    identity = evaluate_prevalence_evidence(_config(tmp_path)).runs[0].identity

    with pytest.raises(ValueError, match="status"):
        PrevalenceRunResult(identity=identity, status="PASS", comparisons=())


def test_public_mapping_excludes_heldout_truth_hashes(tmp_path: Path) -> None:
    """Serializing held-out aggregate hashes would disclose prohibited truth identifiers."""
    report = evaluate_prevalence_evidence(_config(tmp_path))
    mapping = report.to_mapping()
    serialized = json.dumps(mapping, sort_keys=True)
    representation = repr(report)

    assert "heldout_aggregate_sha256" not in serialized
    assert "synthetic_aggregate_sha256" not in serialized
    assert report.heldout_identity.heldout_aggregate_sha256 not in serialized
    assert report.heldout_identity.synthetic_aggregate_sha256 not in serialized
    assert "heldout_aggregate_sha256" not in representation
    assert "synthetic_aggregate_sha256" not in representation
    assert report.heldout_identity.heldout_aggregate_sha256 not in representation
    assert report.heldout_identity.synthetic_aggregate_sha256 not in representation


def test_default_report_and_run_reprs_exclude_internal_comparison_values(tmp_path: Path) -> None:
    """Leaving dataclass comparison fields repr-visible would disclose one-run values in logs."""
    report = evaluate_prevalence_evidence(_config(tmp_path))
    representations = (repr(report), repr(report.runs[0]))

    for representation in representations:
        for field in ("heldout_value", "synthetic_value", "difference", "tolerance"):
            assert field not in representation
        assert "0.5" not in representation


@pytest.mark.parametrize(
    "attribute",
    (
        "profile",
        "engine",
        "reference_time",
        "reference_id",
        "configuration_sha256",
        "reference_sha256",
        "software_revision",
        "prng_family",
        "seed_derivation_version",
        "derivation_fingerprint",
    ),
)
def test_evidence_rejects_cross_run_generation_identity_mismatches(
    tmp_path: Path, attribute: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ignoring any shared generation identity field would mix incomparable packages."""
    config = _config(tmp_path)
    manifest_path = config.runs[-1].package_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[attribute] = (
        "e" * 64
        if attribute
        in {"configuration_sha256", "reference_sha256", "derivation_fingerprint", "schema_fingerprint"}
        else "different-token"
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    identity = verify_package_identity(config.runs[-1])
    assert getattr(identity, attribute) == manifest[attribute]
    module = __import__("synthetic.prevalence_evidence", fromlist=["validate_heldout"])
    called = False

    def must_not_evaluate(_config: HeldoutRunConfig) -> object:
        nonlocal called
        called = True
        raise AssertionError("generation identity mismatch reached held-out evaluation")

    monkeypatch.setattr(module, "validate_heldout", must_not_evaluate)

    with pytest.raises(PrevalenceEvidenceUnavailable, match="unavailable"):
        evaluate_prevalence_evidence(config)
    assert not called


def test_evidence_rejects_a_source_package_replaced_during_heldout_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Removing post-evaluation package re-verification would admit a TOCTOU replacement."""
    config = _config(tmp_path)
    module = __import__("synthetic.prevalence_evidence", fromlist=["validate_heldout"])
    real_validate = module.validate_heldout
    replacement = config.runs[0].package_root / "validation-report.json"

    def replace_after_evaluation(heldout_config: HeldoutRunConfig) -> object:
        result = real_validate(heldout_config)
        replacement.write_bytes(b"{}\n")
        return result

    monkeypatch.setattr(module, "validate_heldout", replace_after_evaluation)

    with pytest.raises(PrevalenceEvidenceUnavailable, match="unavailable"):
        evaluate_prevalence_evidence(config)


def test_evidence_rejects_a_declared_package_root_replaced_after_configuration(
    tmp_path: Path,
) -> None:
    """Discarding configuration-time directory identity admits a substitute predeclared run."""
    config = _config(tmp_path)
    declared = config.runs[0].package_root
    declared.rename(tmp_path / "original-run-101")
    write_prevalence_package(declared, seed=config.runs[0].expected_seed)

    with pytest.raises(PrevalenceEvidenceUnavailable, match="unavailable"):
        evaluate_prevalence_evidence(config)

    assert "root_identities" not in repr(config)


def test_staged_package_rejects_mutation_and_restore_before_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Writable staged bytes would let an evaluator alter a package then restore it undetected."""
    config = _config(tmp_path)
    module = __import__("synthetic.prevalence_evidence", fromlist=["validate_heldout"])
    real_validate = module.validate_heldout

    def mutation_attempt(heldout_config: HeldoutRunConfig) -> object:
        staged_patient_file = heldout_config.synthetic_root / "patients.csv"
        original = staged_patient_file.read_bytes()
        try:
            staged_patient_file.write_bytes(original.replace(b",F,", b",M,"))
        except PermissionError:
            pass
        else:
            staged_patient_file.write_bytes(original)
            pytest.fail("staged package was writable during held-out evaluation")
        return real_validate(heldout_config)

    monkeypatch.setattr(module, "validate_heldout", mutation_attempt)

    report = evaluate_prevalence_evidence(config)

    assert report.status == "UNEVALUABLE"

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from synthetic.calibrate import (
    DEFAULT_AGE_WINDOWS,
    CalibrationRunConfig,
    PartitionPolicy,
    calibrate,
    write_calibration_result,
)
from synthetic.calibration import CalibrationDisclosurePolicy
from synthetic.calibration_targets import TARGET_REGISTRY_VERSION
from synthetic.heldout_validate import FidelityPolicy, HeldoutRunConfig
from synthetic.manifest import RunManifest
from synthetic.prevalence_evidence import (
    PrevalenceEvidenceConfig,
    PrevalenceEvidenceUnavailable,
    PrevalenceRunSpec,
    evaluate_prevalence_evidence,
)
from synthetic.schema_contract import schema_fingerprint
from synthetic.validate import validate_structure
from tests.synthetic.calibration_fixtures import write_mock_snapshot
from tests.synthetic.heldout_fixtures import descriptor_for
from tests.synthetic.prevalence_evidence_fixtures import write_prevalence_package

ROOT = Path(__file__).resolve().parents[2]
PARTITION_KEY = b"0123456789abcdef"


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


@pytest.mark.parametrize(
    "attribute",
    (
        "profile",
        "configuration_sha256",
        "reference_sha256",
        "software_revision",
        "prng_family",
        "seed_derivation_version",
        "derivation_fingerprint",
        "schema_fingerprint",
    ),
)
def test_evidence_rejects_cross_run_generation_identity_mismatches(
    tmp_path: Path, attribute: str
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

    with pytest.raises(PrevalenceEvidenceUnavailable, match="unavailable"):
        evaluate_prevalence_evidence(config)


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

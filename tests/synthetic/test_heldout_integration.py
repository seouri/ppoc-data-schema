from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from synthetic import heldout_validate as heldout_module
from synthetic.calibrate import (
    DEFAULT_AGE_WINDOWS,
    CalibrationRunConfig,
    PartitionPolicy,
    calibrate,
    load_calibration_report,
    write_calibration_result,
)
from synthetic.calibration import CalibrationDisclosurePolicy
from synthetic.calibration_targets import TARGET_REGISTRY_VERSION
from synthetic.heldout_validate import (
    FidelityPolicy,
    HeldoutRunConfig,
    validate_heldout,
    write_heldout_report,
)
from synthetic.schema_contract import load_descriptor, resource_spec
from tests.synthetic.calibration_fixtures import write_mock_snapshot
from tests.synthetic.heldout_fixtures import write_synthetic_package

ROOT = Path(__file__).resolve().parents[2]
PARTITION_KEY = b"0123456789abcdef"


def _partition_policy() -> PartitionPolicy:
    return PartitionPolicy("partition-v1", "1", "key-2026", 5_000, 2)


def _disclosure_policy(*, minimum: int = 1) -> CalibrationDisclosurePolicy:
    return CalibrationDisclosurePolicy("disclosure-v1", "1", minimum, 3)


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
        "required_families": [
            "demographics",
            "observation",
            "physiology",
            "utilization",
            "recorded_outcome",
        ],
        "max_unevaluable_targets": 1_000,
    }
    values.update(changes)
    return FidelityPolicy(**values)  # type: ignore[arg-type]


def _write_calibration(
    real_root: Path,
    destination: Path,
    disclosure_policy: CalibrationDisclosurePolicy,
) -> tuple[Path, Path]:
    calibration = calibrate(
        CalibrationRunConfig(
            data_root=real_root,
            source_descriptor=ROOT / "datapackage.json",
            source_snapshot="snapshot-v1",
            artifact_id="synthetic-v1",
            created_at="2026-08-31T12:00:00Z",
            partition_policy=_partition_policy(),
            disclosure_policy=disclosure_policy,
            partition_key=PARTITION_KEY,
            age_windows=DEFAULT_AGE_WINDOWS,
        )
    )
    write_calibration_result(calibration, destination)
    return destination / "calibration-artifact.json", destination / "calibration-report.json"


def _config(
    tmp_path: Path,
    *,
    disclosure_minimum: int = 1,
    fidelity_policy: FidelityPolicy | None = None,
) -> HeldoutRunConfig:
    real_root = write_mock_snapshot(tmp_path / "real", id_prefix="REAL")
    synthetic_root = write_synthetic_package(tmp_path / "synthetic", id_prefix="GEN")
    disclosure = _disclosure_policy(minimum=disclosure_minimum)
    artifact, report = _write_calibration(real_root, tmp_path / "calibration", disclosure)
    return HeldoutRunConfig(
        real_root=real_root,
        real_descriptor=ROOT / "datapackage.json",
        source_snapshot="snapshot-v1",
        synthetic_root=synthetic_root,
        calibration_artifact=artifact,
        calibration_report=report,
        partition_policy=_partition_policy(),
        disclosure_policy=disclosure,
        partition_key=PARTITION_KEY,
        fidelity_policy=fidelity_policy or _fidelity_policy(),
        age_windows=DEFAULT_AGE_WINDOWS,
        output=tmp_path / "heldout",
    )


def _shift_generated_physiology(package_root: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    resource = resource_spec(descriptor, "visits_augmented")
    path = package_root / resource["path"]
    with path.open(encoding=resource["encoding"], newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    for row in rows:
        if row["height_z_score"]:
            row["height_z_score"] = "100000"
    with path.open("w", encoding=resource["encoding"], newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _rewrite_json(path: Path, mutate: object) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert callable(mutate)
    mutate(value)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_config_is_immutable_and_validates_every_governed_field(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with pytest.raises(FrozenInstanceError):
        config.source_snapshot = "other"  # type: ignore[misc]
    with pytest.raises(ValueError, match="real_root"):
        replace(config, real_root="not-a-path")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="source_snapshot"):
        replace(config, source_snapshot="unsafe/path")
    with pytest.raises(ValueError, match="partition_key"):
        replace(config, partition_key=b"short")
    with pytest.raises(ValueError, match="age_windows"):
        replace(config, age_windows=())
    with pytest.raises(ValueError, match="output"):
        replace(config, output="not-a-path")  # type: ignore[arg-type]


def test_calibration_report_loader_rejects_oversized_input_before_parsing(
    tmp_path: Path,
) -> None:
    report = tmp_path / "calibration-report.json"
    report.write_bytes(b" " * (1024 * 1024 + 1))

    with pytest.raises(ValueError, match="maximum size"):
        load_calibration_report(report)


def test_validate_uses_separate_connections_and_fixed_partition_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    connections: list[object] = []
    calls: list[tuple[object, str]] = []
    real_connect = heldout_module.duckdb.connect
    real_compute = heldout_module.compute_raw_targets

    def tracked_connect(database: str) -> object:
        connection = real_connect(database)
        connections.append(connection)
        return connection

    def tracked_compute(connection: object, prepared: object, calibration_config: object, *, partition_label: str) -> object:
        calls.append((connection, partition_label))
        return real_compute(connection, prepared, calibration_config, partition_label=partition_label)

    monkeypatch.setattr(heldout_module.duckdb, "connect", tracked_connect)
    monkeypatch.setattr(heldout_module, "compute_raw_targets", tracked_compute)

    result = validate_heldout(config)

    assert result.report.status == "PASS"
    assert len(connections) == 2
    assert connections[0] is not connections[1]
    assert calls == [(connections[0], "held_out"), (connections[1], "calibration")]
    serialized = result.report.canonical_json()
    assert "REAL-P-" not in serialized
    assert "GEN-P-" not in serialized
    assert str(config.real_root) not in serialized
    assert PARTITION_KEY.hex() not in serialized
    assert not hasattr(result, "connection")


def test_shifted_generated_value_produces_promotable_fail(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _shift_generated_physiology(config.synthetic_root)

    result = validate_heldout(config)
    write_heldout_report(result, config.output)

    assert result.report.status == "FAIL"
    assert any(comparison.status == "FAIL" for comparison in result.report.comparisons)
    assert config.output.is_dir()


def test_high_disclosure_minimum_produces_promotable_unevaluable(tmp_path: Path) -> None:
    config = _config(tmp_path, disclosure_minimum=1_000)

    result = validate_heldout(config)
    write_heldout_report(result, config.output)

    assert result.report.status == "UNEVALUABLE"
    assert result.report.comparison_counts["UNEVALUABLE"] > 0
    assert config.output.is_dir()


@pytest.mark.parametrize(
    "mismatch",
    [
        "artifact_snapshot",
        "artifact_schema",
        "artifact_disclosure",
        "report_snapshot",
        "report_schema",
        "report_hash",
        "report_partition",
        "report_check",
        "synthetic_marker",
    ],
)
def test_compatibility_mismatches_fail_before_target_computation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mismatch: str,
) -> None:
    config = _config(tmp_path)
    if mismatch == "artifact_snapshot":
        _rewrite_json(config.calibration_artifact, lambda value: value.__setitem__("source_snapshot", "other"))
    elif mismatch == "artifact_schema":
        _rewrite_json(config.calibration_artifact, lambda value: value.__setitem__("schema_fingerprint", "0" * 64))
    elif mismatch == "artifact_disclosure":
        _rewrite_json(
            config.calibration_artifact,
            lambda value: value["disclosure_policy"].__setitem__("policy_version", "2"),
        )
    elif mismatch == "report_snapshot":
        _rewrite_json(config.calibration_report, lambda value: value.__setitem__("source_snapshot", "other"))
    elif mismatch == "report_schema":
        _rewrite_json(config.calibration_report, lambda value: value.__setitem__("schema_fingerprint", "0" * 64))
    elif mismatch == "report_hash":
        _rewrite_json(config.calibration_report, lambda value: value.__setitem__("source_aggregate_sha256", "0" * 64))
    elif mismatch == "report_partition":
        _rewrite_json(
            config.calibration_report,
            lambda value: value["partition_policy"].__setitem__("policy_version", "2"),
        )
    elif mismatch == "report_check":
        _rewrite_json(
            config.calibration_report,
            lambda value: value["checks"][0].__setitem__("passed", False),
        )
    else:
        descriptor = config.synthetic_root / "datapackage.json"
        _rewrite_json(descriptor, lambda value: value.pop("x-synthetic"))

    monkeypatch.setattr(
        heldout_module,
        "compute_raw_targets",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("targets reached")),
    )

    with pytest.raises(ValueError):
        validate_heldout(config)
    assert not config.output.exists()


def test_write_promotes_only_canonical_report_and_summary(tmp_path: Path) -> None:
    config = _config(tmp_path)
    result = validate_heldout(config)

    write_heldout_report(result, config.output)

    assert sorted(path.name for path in config.output.iterdir()) == [
        "heldout-validation-report.json",
        "heldout-validation-summary.txt",
    ]
    report_bytes = (config.output / "heldout-validation-report.json").read_bytes()
    summary_bytes = (config.output / "heldout-validation-summary.txt").read_bytes()
    assert report_bytes == result.report.to_json_bytes()
    assert summary_bytes == result.report.human_summary().encode("ascii")
    assert json.loads(report_bytes) == result.report.to_mapping()


@pytest.mark.parametrize("suffix", ["partial", "failed"])
def test_write_refuses_hashed_lifecycle_collision(tmp_path: Path, suffix: str) -> None:
    config = _config(tmp_path)
    result = validate_heldout(config)
    identity = (
        f"{result.report.synthetic_artifact_id}:"
        f"{result.report.fidelity_policy.policy_id}:"
        f"{result.report.fidelity_policy.policy_version}"
    )
    lifecycle_id = hashlib.sha256(identity.encode("ascii")).hexdigest()
    (config.output.parent / f".{config.output.name}.{lifecycle_id}.{suffix}").mkdir()

    with pytest.raises(FileExistsError, match="lifecycle"):
        write_heldout_report(result, config.output)
    assert not config.output.exists()


def test_write_refuses_existing_output_without_overwriting(tmp_path: Path) -> None:
    config = _config(tmp_path)
    result = validate_heldout(config)
    config.output.mkdir()
    sentinel = config.output / "keep.txt"
    sentinel.write_text("keep\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_heldout_report(result, config.output)
    assert sentinel.read_text(encoding="utf-8") == "keep\n"


def test_noncanonical_write_archives_only_fixed_aggregate_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    result = validate_heldout(config)
    real_write = heldout_module._write_exclusive_fsynced

    def corrupt_report(path: Path, payload: bytes) -> None:
        if path.name == "heldout-validation-report.json":
            payload = b" " + payload
        real_write(path, payload)

    monkeypatch.setattr(heldout_module, "_write_exclusive_fsynced", corrupt_report)

    with pytest.raises(ValueError, match="could not be promoted") as error:
        write_heldout_report(result, config.output)

    assert "canonical" not in str(error.value)
    assert not config.output.exists()
    identity = (
        f"{result.report.synthetic_artifact_id}:"
        f"{result.report.fidelity_policy.policy_id}:"
        f"{result.report.fidelity_policy.policy_version}"
    )
    lifecycle_id = hashlib.sha256(identity.encode("ascii")).hexdigest()
    failed = config.output.parent / f".{config.output.name}.{lifecycle_id}.failed"
    assert sorted(path.name for path in failed.iterdir()) == ["failure.json"]
    assert json.loads((failed / "failure.json").read_text(encoding="utf-8")) == {
        "status": "FAILED",
        "reason": "held-out output validation failed",
    }

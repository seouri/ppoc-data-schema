from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from synthetic.calibrate import (
    DEFAULT_AGE_WINDOWS,
    CalibrationAgeWindow,
    CalibrationCheck,
    CalibrationReport,
    CalibrationRunConfig,
    PartitionPolicy,
    calibrate,
    write_calibration_result,
)
from synthetic.calibration import CalibrationDisclosurePolicy
from tests.synthetic.calibration_fixtures import write_mock_snapshot


def valid_config(**changes: object) -> CalibrationRunConfig:
    values: dict[str, object] = {
        "data_root": Path("synthetic-snapshot"),
        "source_descriptor": Path("datapackage.json"),
        "source_snapshot": "snapshot-v1",
        "artifact_id": "calibration-v1",
        "created_at": "2026-08-31T12:00:00Z",
        "partition_policy": PartitionPolicy("partition-v1", "1", "key-2026", 8_000, 2),
        "disclosure_policy": CalibrationDisclosurePolicy("disclosure-v1", "1", 2, 3),
        "partition_key": b"0123456789abcdef",
        "age_windows": DEFAULT_AGE_WINDOWS,
    }
    values.update(changes)
    return CalibrationRunConfig(**values)  # type: ignore[arg-type]


def test_partition_policy_uses_explicit_basis_points() -> None:
    policy = PartitionPolicy("partition-v1", "1", "key-2026", 8_000, 2)
    assert policy.calibration_basis_points == 8_000
    assert policy.minimum_partition_patients == 2


def test_default_windows_are_ordered_observation_bins() -> None:
    assert [window.window_id for window in DEFAULT_AGE_WINDOWS] == [
        "infancy", "childhood", "puberty_window", "adolescence"
    ]
    assert DEFAULT_AGE_WINDOWS[0].lower_age_days == 0
    assert DEFAULT_AGE_WINDOWS[-1].upper_age_days == 7_306


@pytest.mark.parametrize(
    ("factory", "match"),
    [
        (lambda: PartitionPolicy("partition-v1", "1", "key-2026", True, 2), "integer"),
        (lambda: PartitionPolicy("partition-v1", "1", "key-2026", 0, 2), "basis"),
        (lambda: PartitionPolicy("partition-v1", "1", "key-2026", 10_000, 2), "basis"),
        (lambda: PartitionPolicy("partition-v1", "1", "key-2026", 8_000, 0), "minimum"),
        (lambda: PartitionPolicy("partition-v1", "1", "", 8_000, 2), "token"),
        (lambda: PartitionPolicy("partition/v1", "1", "key-2026", 8_000, 2), "token"),
    ],
)
def test_partition_policy_rejects_invalid_values(factory: object, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        factory()  # type: ignore[operator]


def test_run_config_is_frozen_and_preserves_explicit_paths() -> None:
    config = valid_config()
    assert config.data_root == Path("synthetic-snapshot")
    assert config.source_descriptor == Path("datapackage.json")
    with pytest.raises(FrozenInstanceError):
        config.source_snapshot = "other"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"data_root": "snapshot"}, "data_root"),
        ({"source_descriptor": "datapackage.json"}, "source_descriptor"),
        ({"partition_key": b""}, "partition_key"),
        ({"partition_key": b"too-short"}, "partition_key"),
        ({"partition_key": bytearray(b"0123456789abcdef")}, "partition_key"),
        ({"created_at": "2026-02-30T12:00:00Z"}, "created_at"),
        ({"created_at": "2026-08-31T12:00:00+00:00"}, "created_at"),
        ({"age_windows": ()}, "age_windows"),
        ({"age_windows": (CalibrationAgeWindow("late", 10, 20), CalibrationAgeWindow("early", 0, 11))}, "ordered"),
    ],
)
def test_run_config_rejects_invalid_governed_inputs(changes: dict[str, object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        valid_config(**changes)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: CalibrationAgeWindow("broken", True, 2),
        lambda: CalibrationAgeWindow("broken", -1, 2),
        lambda: CalibrationAgeWindow("broken", 2, 2),
        lambda: CalibrationAgeWindow("broken/window", 0, 2),
    ],
)
def test_age_window_rejects_invalid_bounds_and_identifiers(factory: object) -> None:
    with pytest.raises(ValueError):
        factory()  # type: ignore[operator]


def test_report_is_canonical_and_aggregate_only() -> None:
    report = CalibrationReport(
        report_version="calibration-report-v1",
        status="AGGREGATES_ONLY",
        source_snapshot="snapshot-v1",
        schema_fingerprint="a" * 64,
        partition_policy={"policy_id": "partition-v1", "policy_version": "1"},
        partition_counts={"calibration": 8, "held_out": 4},
        resource_row_counts={"patients": {"calibration": 8, "held_out": 4}},
        target_family_counts={"demographics": 3},
        suppression_counts={"demographics": 1},
        source_aggregate_sha256="b" * 64,
        checks=(CalibrationCheck("schema", True, "matched expected resource contract"),),
    )
    assert set(report.to_mapping()) == {
        "report_version", "status", "source_snapshot", "schema_fingerprint", "partition_policy",
        "partition_counts", "resource_row_counts", "target_family_counts", "suppression_counts",
        "source_aggregate_sha256", "checks",
    }
    assert report.canonical_json() == report.to_json_bytes().decode("ascii").removesuffix("\n")
    assert report.to_json_bytes().endswith(b"\n")
    with pytest.raises(TypeError):
        report.partition_counts["calibration"] = 0  # type: ignore[index]


@pytest.mark.parametrize(
    "changes",
    [
        {"partition_counts": {"patient_id": 1}},
        {"resource_row_counts": {"patients": {"visit_id": 1}}},
    ],
)
def test_report_rejects_record_or_key_material(changes: dict[str, object]) -> None:
    values = {
        "report_version": "calibration-report-v1", "status": "AGGREGATES_ONLY", "source_snapshot": "snapshot-v1",
        "schema_fingerprint": "a" * 64, "partition_policy": {"policy_id": "partition-v1", "policy_version": "1"},
        "partition_counts": {"calibration": 8, "held_out": 4}, "resource_row_counts": {"patients": {"calibration": 8, "held_out": 4}},
        "target_family_counts": {"demographics": 3}, "suppression_counts": {"demographics": 1},
        "source_aggregate_sha256": "b" * 64, "checks": (CalibrationCheck("schema", True, "matched contract"),),
    }
    values.update(changes)
    with pytest.raises(ValueError, match="aggregate|integer"):
        CalibrationReport(**values)  # type: ignore[arg-type]


def test_check_rejects_key_material_in_detail() -> None:
    with pytest.raises(ValueError, match="aggregate"):
        CalibrationCheck("schema", True, "key material accepted")


@pytest.mark.parametrize(
    "detail",
    [
        "unknown SYN-P-001",
        "unknown syn-p-001",
        "opened /restricted/patients.csv",
        "opened ../snapshot/patients.csv",
        "opened fixtures/patients.csv",
        "patientId matched",
        "partitionKey was provided",
    ],
)
def test_check_rejects_identifier_path_and_key_alias_details(detail: str) -> None:
    with pytest.raises(ValueError, match="aggregate"):
        CalibrationCheck("schema", True, detail)


@pytest.mark.parametrize(
    "changes",
    [
        {"partition_counts": {"calibration": "SYN-P-001", "held_out": 4}},
        {"partition_counts": {"calibration": "syn-p-001", "held_out": 4}},
        {"partition_counts": {"partitionKey": 8, "held_out": 4}},
        {"resource_row_counts": {"patients": {"sourcePath": 1}}},
        {"target_family_counts": {"patientCount": 1}},
        {"partition_policy": {"policy_id": "patientId", "policy_version": "1"}},
    ],
)
def test_report_rejects_identifier_values_and_field_aliases(changes: dict[str, object]) -> None:
    values = {
        "report_version": "calibration-report-v1", "status": "AGGREGATES_ONLY", "source_snapshot": "snapshot-v1",
        "schema_fingerprint": "a" * 64, "partition_policy": {"policy_id": "partition-v1", "policy_version": "1"},
        "partition_counts": {"calibration": 8, "held_out": 4}, "resource_row_counts": {"patients": {"calibration": 8, "held_out": 4}},
        "target_family_counts": {"demographics": 3}, "suppression_counts": {"demographics": 1},
        "source_aggregate_sha256": "b" * 64, "checks": (CalibrationCheck("schema", True, "matched contract"),),
    }
    values.update(changes)
    with pytest.raises(ValueError, match="aggregate|integer"):
        CalibrationReport(**values)  # type: ignore[arg-type]


def test_orchestration_requires_public_model_types() -> None:
    with pytest.raises(TypeError, match="config"):
        calibrate(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="result"):
        write_calibration_result(object(), Path("output"))  # type: ignore[arg-type]


def test_mock_snapshot_has_all_descriptor_resources_with_fictional_identifiers(tmp_path: Path) -> None:
    snapshot = write_mock_snapshot(tmp_path / "snapshot")
    assert (snapshot / "patients.csv").read_text(encoding="utf-8").splitlines()[1].startswith("SYN-P-001,")
    assert (snapshot / "visits.csv").read_text(encoding="utf-8").splitlines()[1].startswith(
        "SYN-P-001,SYN-V-001,"
    )
    assert len(list(snapshot.glob("*.csv"))) == 8

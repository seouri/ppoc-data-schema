from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import duckdb
import pytest

from synthetic.calibrate import DEFAULT_AGE_WINDOWS, CalibrationRunConfig, PartitionPolicy
from synthetic.calibration import CalibrationDisclosurePolicy
from synthetic.calibration_input import prepare_input, prepare_synthetic_input
from synthetic.calibration_targets import compute_raw_targets
from synthetic.schema_contract import resource_spec
from tests.synthetic.calibration_fixtures import write_mock_snapshot
from tests.synthetic.heldout_fixtures import descriptor_for, write_synthetic_package

ROOT = Path(__file__).resolve().parents[2]


def _test_config(root: Path) -> CalibrationRunConfig:
    return CalibrationRunConfig(
        data_root=root,
        source_descriptor=ROOT / "datapackage.json",
        source_snapshot="synthetic-v1",
        artifact_id="calibration-v1",
        created_at="2026-08-31T12:00:00Z",
        partition_policy=PartitionPolicy("partition-v1", "1", "key-2026", 5_000, 2),
        disclosure_policy=CalibrationDisclosurePolicy("disclosure-v1", "1", 2, 3),
        partition_key=b"0123456789abcdef",
        age_windows=DEFAULT_AGE_WINDOWS,
    )


def _find_target(targets: tuple[object, ...], name: str, stratum_id: str = "") -> object:
    matches = [
        target
        for target in targets
        if target.target_name == name and (not stratum_id or target.stratum_id == stratum_id)  # type: ignore[union-attr]
    ]
    assert len(matches) == 1
    return matches[0]


def _write_header_only(package_root: Path, resource_name: str) -> None:
    descriptor = descriptor_for(package_root)
    resource = resource_spec(descriptor, resource_name)
    path = package_root / resource["path"]
    dialect = resource.get("dialect", {})
    with path.open(newline="", encoding=resource.get("encoding", "utf-8")) as handle:
        header = next(
            csv.reader(
                handle,
                delimiter=dialect.get("delimiter", ","),
                quotechar=dialect.get("quoteChar", '"'),
                doublequote=dialect.get("doubleQuote", True),
            )
        )
    with path.open("w", newline="", encoding=resource.get("encoding", "utf-8")) as handle:
        csv.writer(
            handle,
            delimiter=dialect.get("delimiter", ","),
            quotechar=dialect.get("quoteChar", '"'),
            doublequote=dialect.get("doubleQuote", True),
        ).writerow(header)


def test_target_registry_can_select_held_out_without_mixing_partitions(tmp_path: Path) -> None:
    root = write_mock_snapshot(tmp_path / "snapshot", patient_count=12)
    config = _test_config(root)
    with duckdb.connect(":memory:") as connection:
        prepared = prepare_input(connection, config)
        held_out = compute_raw_targets(connection, prepared, config, partition_label="held_out")
        calibration = compute_raw_targets(connection, prepared, config)
        expected = {
            ("sex_f", "outcome_layer=observed"): (2 / 3, 2),
            ("healthy_flag", "outcome_layer=observed"): (1 / 3, 1),
            ("encounter_office", "visit_window=all"): (0.25, 3),
            ("weight_available", "age_regime=infancy"): (1.0, 3),
            ("height_z_mean", "age_regime=infancy|recorded_sex=F"): (0.1, 2),
        }
    assert held_out
    assert calibration
    assert held_out != calibration
    assert all("patient_id" not in target.stratum_id for target in held_out)
    assert {target.family for target in held_out} == {
        "demographics", "observation", "physiology", "recorded_outcome", "utilization",
    }
    for (name, stratum_id), (value, support) in expected.items():
        target = _find_target(held_out, name, stratum_id)
        assert (target.value, target.support_count) == (value, support)  # type: ignore[union-attr]


def test_target_registry_rejects_unknown_partition_before_querying(tmp_path: Path) -> None:
    root = write_mock_snapshot(tmp_path / "snapshot", patient_count=12)
    config = _test_config(root)
    with duckdb.connect(":memory:") as connection:
        prepared = prepare_input(connection, config)
        with pytest.raises(ValueError, match="partition_label"):
            compute_raw_targets(connection, prepared, config, partition_label="all")


def test_synthetic_input_stages_all_fictional_patients_as_calibration(tmp_path: Path) -> None:
    package_root = write_synthetic_package(tmp_path / "generated", patient_count=12)
    with duckdb.connect(":memory:") as connection:
        prepared = prepare_synthetic_input(connection, package_root, descriptor_for(package_root))
        labels = connection.execute(
            "SELECT partition_label, count(*) FROM patient_partitions GROUP BY partition_label"
        ).fetchall()
    assert labels == [("calibration", 12)]
    serialized = json.dumps(prepared.to_mapping())
    assert "GEN-P-001" not in serialized
    assert str(package_root) not in serialized
    assert prepared.descriptor == {}
    assert set(prepared.resource_names) == {
        "patients", "patients_augmented", "visits", "visits_augmented",
        "labs", "medications", "problem_list", "referrals",
    }


def test_synthetic_input_accepts_header_only_exact_schema_package(tmp_path: Path) -> None:
    package_root = write_synthetic_package(tmp_path / "generated", patient_count=3)
    for resource_name in descriptor_for(package_root)["resources"]:
        _write_header_only(package_root, resource_name["name"])
    with duckdb.connect(":memory:") as connection:
        prepared = prepare_synthetic_input(connection, package_root, descriptor_for(package_root))
        targets = compute_raw_targets(connection, prepared, _test_config(package_root))
    assert prepared.partition_summary.patient_counts == {"calibration": 0, "held_out": 0}
    assert targets == ()


def test_synthetic_input_omits_undefined_recorded_targets_for_missing_augmented_rows(
    tmp_path: Path,
) -> None:
    package_root = write_synthetic_package(tmp_path / "generated", patient_count=3)
    _write_header_only(package_root, "patients_augmented")
    with duckdb.connect(":memory:") as connection:
        prepared = prepare_synthetic_input(connection, package_root, descriptor_for(package_root))
        targets = compute_raw_targets(connection, prepared, _test_config(package_root))
    assert any(target.family == "demographics" for target in targets)
    assert not any(target.family == "recorded_outcome" for target in targets)


@pytest.mark.parametrize("mutation", ["missing_marker", "path_traversal", "duplicate_key", "unknown_patient"])
def test_synthetic_input_rejects_invalid_package_without_identifier_leakage(
    tmp_path: Path, mutation: str
) -> None:
    package_root = write_synthetic_package(tmp_path / "generated")
    descriptor_path = package_root / "datapackage.json"
    descriptor = descriptor_for(package_root)
    if mutation == "missing_marker":
        descriptor.pop("x-synthetic")
        descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
    elif mutation == "path_traversal":
        resource_spec(descriptor, "patients")["path"] = "../patients.csv"
        descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
    else:
        resource = resource_spec(descriptor, "patients" if mutation == "duplicate_key" else "labs")
        path = package_root / resource["path"]
        with path.open(newline="", encoding=resource.get("encoding", "utf-8")) as handle:
            rows = list(csv.reader(handle))
        if mutation == "duplicate_key":
            rows.append(rows[1])
        else:
            rows[1][rows[0].index("patient_id")] = "GEN-UNKNOWN"
        with path.open("w", newline="", encoding=resource.get("encoding", "utf-8")) as handle:
            csv.writer(handle).writerows(rows)
    with duckdb.connect(":memory:") as connection, pytest.raises(ValueError) as error:
        prepare_synthetic_input(connection, package_root, descriptor_for(package_root))
    assert "GEN-" not in str(error.value)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink support is required")
def test_synthetic_input_rejects_symlinked_descriptor_or_resource(tmp_path: Path) -> None:
    package_root = write_synthetic_package(tmp_path / "generated")
    descriptor_path = package_root / "datapackage.json"
    descriptor = descriptor_for(package_root)
    replacement = package_root / "descriptor-copy.json"
    descriptor_path.replace(replacement)
    descriptor_path.symlink_to(replacement.name)
    with pytest.raises(ValueError) as error:
        descriptor_for(package_root)
    assert "GEN-" not in str(error.value)
    with duckdb.connect(":memory:") as connection, pytest.raises(ValueError) as error:
        prepare_synthetic_input(connection, package_root, descriptor)
    assert "GEN-" not in str(error.value)

    package_root = write_synthetic_package(tmp_path / "generated-resource")
    descriptor = descriptor_for(package_root)
    resource_path = package_root / resource_spec(descriptor, "labs")["path"]
    replacement = resource_path.with_name("labs-copy.csv")
    resource_path.replace(replacement)
    resource_path.symlink_to(replacement.name)
    with duckdb.connect(":memory:") as connection, pytest.raises(ValueError) as error:
        prepare_synthetic_input(connection, package_root, descriptor)
    assert "GEN-" not in str(error.value)

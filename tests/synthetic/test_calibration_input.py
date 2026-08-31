import csv
import json
import os
import shutil
from dataclasses import replace
from pathlib import Path

import duckdb
import pytest

from synthetic import calibration_input
from synthetic.calibrate import DEFAULT_AGE_WINDOWS, CalibrationRunConfig, PartitionPolicy
from synthetic.calibration import CalibrationDisclosurePolicy
from synthetic.calibration_input import assign_partition, prepare_input
from synthetic.schema_contract import load_descriptor, resource_spec, schema_fingerprint
from tests.synthetic.calibration_fixtures import write_mock_snapshot

ROOT = Path(__file__).resolve().parents[2]


def config_for(root: Path, **changes: object) -> CalibrationRunConfig:
    values: dict[str, object] = {
        "data_root": root,
        "source_descriptor": ROOT / "datapackage.json",
        "source_snapshot": "synthetic-v1",
        "artifact_id": "calibration-v1",
        "created_at": "2026-08-31T12:00:00Z",
        "partition_policy": PartitionPolicy("partition-v1", "1", "key-2026", 5_000, 2),
        "disclosure_policy": CalibrationDisclosurePolicy("disclosure-v1", "1", 2, 3),
        "partition_key": b"0123456789abcdef",
        "age_windows": DEFAULT_AGE_WINDOWS,
    }
    values.update(changes)
    return CalibrationRunConfig(**values)  # type: ignore[arg-type]


def _rewrite_csv(path: Path, mutate: object) -> None:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    mutate(rows)  # type: ignore[operator]
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def _resource_path(root: Path, name: str) -> Path:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    return root / resource_spec(descriptor, name)["path"]


def _valid_snapshot(root: Path) -> Path:
    """Fill only required numeric fixture placeholders from the checked-in descriptor."""
    snapshot = write_mock_snapshot(root)
    descriptor = load_descriptor(ROOT / "datapackage.json")
    for resource in descriptor["resources"]:
        required_numeric = {
            field["name"]: "0" if field["type"] == "integer" else "0.5"
            for field in resource["schema"]["fields"]
            if field["type"] in {"integer", "number"}
            and (field.get("constraints") or {}).get("required")
        }
        if not required_numeric:
            continue
        path = snapshot / resource["path"]
        encoding = resource.get("encoding", "utf-8")
        with path.open(newline="", encoding=encoding) as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            headers = reader.fieldnames
        assert headers is not None
        for row in rows:
            for field, value in required_numeric.items():
                if not row[field]:
                    row[field] = value
        with path.open("w", newline="", encoding=encoding) as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
    return snapshot


def test_assign_partition_is_stable_keyed_and_digest_free() -> None:
    policy = PartitionPolicy("partition-v1", "1", "key-2026", 5_000, 1)
    first = assign_partition("SYN-P-001", policy, b"0123456789abcdef")
    assert first == assign_partition("SYN-P-001", policy, b"0123456789abcdef")
    assert first in {"calibration", "held_out"}
    labels = {
        assign_partition(f"SYN-P-{index:03d}", policy, b"0123456789abcdef")
        for index in range(1, 100)
    }
    assert labels == {"calibration", "held_out"}
    changed = [
        assign_partition(f"SYN-P-{index:03d}", policy, b"fedcba9876543210")
        for index in range(1, 100)
    ]
    assert changed != [assign_partition(f"SYN-P-{index:03d}", policy, b"0123456789abcdef") for index in range(1, 100)]
    assert not hasattr(first, "digest")


def test_prepare_input_proves_all_rows_use_one_patient_partition(tmp_path: Path) -> None:
    root = _valid_snapshot(tmp_path / "snapshot")
    config = config_for(root)
    with duckdb.connect(":memory:") as connection:
        prepared = prepare_input(connection, config)
    assert prepared.schema_fingerprint == schema_fingerprint(load_descriptor(ROOT / "datapackage.json"))
    assert set(prepared.partition_summary.patient_counts) == {"calibration", "held_out"}
    assert all(value >= 2 for value in prepared.partition_summary.patient_counts.values())
    assert set(prepared.partition_summary.resource_row_counts) == set(prepared.resource_names)
    assert "SYN-P-001" not in json.dumps(prepared.partition_summary.to_mapping())
    assert "SYN-P-001" not in json.dumps(prepared.to_mapping())


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda root: _resource_path(root, "labs").unlink(), "labs"),
        (lambda root: _resource_path(root, "labs").unlink() or _resource_path(root, "labs").symlink_to("patients.csv"), "labs"),
        (lambda root: _rewrite_csv(_resource_path(root, "patients"), lambda rows: rows.__setitem__(0, rows[0][:-1])), "patients"),
        (lambda root: _rewrite_csv(_resource_path(root, "patients"), lambda rows: rows.append(rows[1])), "patients"),
        (lambda root: _rewrite_csv(_resource_path(root, "labs"), lambda rows: rows.__setitem__(1, ["unknown", *rows[1][1:]])), "labs"),
        (lambda root: _rewrite_csv(_resource_path(root, "visits"), lambda rows: rows.__setitem__(1, [*rows[1][:2], "bad-age", *rows[1][3:]])), "visits.*age_in_days"),
    ],
)
def test_prepare_input_fails_closed_for_bad_snapshot_rows(tmp_path: Path, mutate: object, match: str) -> None:
    root = _valid_snapshot(tmp_path / "snapshot")
    mutate(root)  # type: ignore[operator]
    with duckdb.connect(":memory:") as connection, pytest.raises(ValueError, match=match):
        prepare_input(connection, config_for(root))


@pytest.mark.parametrize("unsafe_path", ["/tmp/patients.csv", "../patients.csv"])
def test_prepare_input_rejects_unsafe_descriptor_paths(tmp_path: Path, unsafe_path: str) -> None:
    root = _valid_snapshot(tmp_path / "snapshot")
    descriptor_path = tmp_path / "descriptor.json"
    descriptor = load_descriptor(ROOT / "datapackage.json")
    resource_spec(descriptor, "patients")["path"] = unsafe_path
    descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
    with duckdb.connect(":memory:") as connection, pytest.raises(ValueError, match="descriptor"):
        prepare_input(connection, config_for(root, source_descriptor=descriptor_path))


def test_prepare_input_rejects_schema_mismatch_and_small_partition(tmp_path: Path) -> None:
    root = _valid_snapshot(tmp_path / "snapshot")
    descriptor_path = tmp_path / "descriptor.json"
    shutil.copy(ROOT / "datapackage.json", descriptor_path)
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    descriptor["resources"].pop()
    descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
    with duckdb.connect(":memory:") as connection, pytest.raises(ValueError, match="descriptor"):
        prepare_input(connection, config_for(root, source_descriptor=descriptor_path))
    strict = replace(config_for(root), partition_policy=PartitionPolicy("partition-v1", "1", "key-2026", 5_000, 7))
    with duckdb.connect(":memory:") as connection, pytest.raises(ValueError, match="partition"):
        prepare_input(connection, strict)


def test_prepare_input_rejects_short_partition_key(tmp_path: Path) -> None:
    root = _valid_snapshot(tmp_path / "snapshot")
    with pytest.raises(ValueError, match="partition_key"):
        config_for(root, partition_key=b"short")


@pytest.mark.parametrize(
    ("resource", "field"),
    [
        ("patients_augmented", "healthy_flag"),
        ("patients_augmented", "visits_count"),
        ("visits_augmented", "age_in_days"),
        ("labs", "lab_order_date_age_in_days"),
        ("medications", "med_order_date_age_in_days"),
        ("referrals", "referral_date_age_in_days"),
    ],
)
def test_prepare_input_rejects_malformed_required_numeric_fields(
    tmp_path: Path, resource: str, field: str
) -> None:
    root = _valid_snapshot(tmp_path / "snapshot")

    def corrupt(rows: list[list[str]]) -> None:
        rows[1][rows[0].index(field)] = "not-a-number"

    _rewrite_csv(_resource_path(root, resource), corrupt)
    with duckdb.connect(":memory:") as connection, pytest.raises(ValueError, match=rf"{resource}.*{field}"):
        prepare_input(connection, config_for(root))


def test_prepare_input_stages_checked_file_descriptor_after_path_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _valid_snapshot(tmp_path / "snapshot")
    original = calibration_input._open_validated_source

    def replace_after_validation(data_root: Path, resource: dict[str, object]) -> object:
        source = original(data_root, resource)
        if resource["name"] == "labs":
            path = _resource_path(root, "labs")
            replacement = path.with_name("replacement.csv")
            replacement.write_text(
                path.read_text(encoding="iso-8859-1") + "unknown,,,,,,,,,,,\n", encoding="iso-8859-1"
            )
            os.replace(replacement, path)
        return source

    monkeypatch.setattr(calibration_input, "_open_validated_source", replace_after_validation)
    with duckdb.connect(":memory:") as connection:
        prepared = prepare_input(connection, config_for(root))
    assert sum(prepared.partition_summary.resource_row_counts["labs"].values()) == 12

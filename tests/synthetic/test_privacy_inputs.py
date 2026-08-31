from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from synthetic.privacy_audit import _load_private_package
from synthetic.schema_contract import load_descriptor, resource_spec
from tests.synthetic.privacy_fixtures import write_generated_package, write_real_package


def test_private_package_loader_enforces_marker_schema_and_private_profiles(tmp_path: Path) -> None:
    real = _load_private_package(write_real_package(tmp_path / "real"), synthetic=False, longitudinal_minimum=3)
    generated = _load_private_package(
        write_generated_package(tmp_path / "generated"), synthetic=True, longitudinal_minimum=3
    )

    assert real.patient_count == generated.patient_count == 12
    assert not hasattr(real, "connection")
    assert not hasattr(real, "rows")
    assert "REAL-P-001" not in repr(real)
    assert len(real._identifier_values) > 0
    assert len(real._trajectory_signatures) > 0
    assert len(real._profile_signatures) > 0
    assert real._profiles[0]._profile_signature != real._profiles[0]._trajectory_signature


@pytest.mark.parametrize("synthetic", [True, False])
def test_private_package_loader_rejects_wrong_marker_polarity(tmp_path: Path, synthetic: bool) -> None:
    root = write_real_package(tmp_path / "package") if synthetic else write_generated_package(tmp_path / "package")

    with pytest.raises(ValueError, match="marker"):
        _load_private_package(root, synthetic=synthetic, longitudinal_minimum=3)


def test_private_package_loader_rejects_path_traversal_without_leaking_row_data(tmp_path: Path) -> None:
    root = write_generated_package(tmp_path / "package")
    descriptor_path = root / "datapackage.json"
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    descriptor["resources"][0]["path"] = "../outside.csv"
    descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")

    with pytest.raises(ValueError) as error:
        _load_private_package(root, synthetic=True, longitudinal_minimum=3)

    assert "GEN-P-001" not in str(error.value)
    assert "outside.csv" not in str(error.value)


def test_private_package_loader_rejects_malformed_csv_and_duplicate_keys_without_identifier_echo(
    tmp_path: Path,
) -> None:
    root = write_generated_package(tmp_path / "package")
    descriptor = load_descriptor(root / "datapackage.json")
    visits_path = root / resource_spec(descriptor, "visits")["path"]
    with visits_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    rows[2][rows[0].index("visit_id")] = rows[1][rows[0].index("visit_id")]
    with visits_path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)

    with pytest.raises(ValueError) as error:
        _load_private_package(root, synthetic=True, longitudinal_minimum=3)

    assert "GEN-V-001" not in str(error.value)


def test_private_package_loader_rejects_declared_visit_foreign_key_orphans(tmp_path: Path) -> None:
    """Catches validating only patient links while accepting orphaned augmented visit rows."""
    root = write_generated_package(tmp_path / "package")
    descriptor = load_descriptor(root / "datapackage.json")
    path = root / resource_spec(descriptor, "visits_augmented")["path"]
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        fields = tuple(rows[0])
    rows[0]["visit_id"] = "ORPHAN-VISIT"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError) as error:
        _load_private_package(root, synthetic=True, longitudinal_minimum=3)

    assert "ORPHAN-VISIT" not in str(error.value)


def test_private_package_loader_rejects_symlinked_descriptor_and_resources(tmp_path: Path) -> None:
    root = write_generated_package(tmp_path / "package")
    descriptor = root / "datapackage.json"
    moved = root / "descriptor-real.json"
    descriptor.rename(moved)
    descriptor.symlink_to(moved.name)

    with pytest.raises(ValueError, match="descriptor"):
        _load_private_package(root, synthetic=True, longitudinal_minimum=3)


def test_private_package_loader_rejects_symlinked_resource_without_identifier_echo(tmp_path: Path) -> None:
    root = write_generated_package(tmp_path / "package")
    descriptor = load_descriptor(root / "datapackage.json")
    visits_path = root / resource_spec(descriptor, "visits")["path"]
    moved = root / "visits-real.csv"
    visits_path.rename(moved)
    visits_path.symlink_to(moved.name)

    with pytest.raises(ValueError) as error:
        _load_private_package(root, synthetic=True, longitudinal_minimum=3)

    assert "GEN-P-001" not in str(error.value)
    assert "GEN-V-001" not in str(error.value)


@pytest.mark.parametrize("malformed", ["not-an-age", '"unterminated'])
def test_private_package_loader_rejects_malformed_csv_or_values_without_identifier_echo(
    tmp_path: Path, malformed: str
) -> None:
    root = write_generated_package(tmp_path / "package")
    descriptor = load_descriptor(root / "datapackage.json")
    visits_path = root / resource_spec(descriptor, "visits")["path"]
    if malformed == "not-an-age":
        with visits_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        rows[1][rows[0].index("age_in_days")] = malformed
        with visits_path.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerows(rows)
    else:
        visits_path.write_text(malformed, encoding="utf-8")

    with pytest.raises(ValueError) as error:
        _load_private_package(root, synthetic=True, longitudinal_minimum=3)

    assert "GEN-P-001" not in str(error.value)
    assert "GEN-V-001" not in str(error.value)

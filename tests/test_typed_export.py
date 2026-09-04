from __future__ import annotations

import copy
import json
import math
import os
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from scripts.typed_export import (
    EXPECTED_RESOURCE_NAMES,
    DescriptorError,
    ExportConfig,
    load_package_contract,
)
from tests.analytical_export_fixtures import write_tiny_snapshot


def test_load_package_contract_preserves_order_and_types(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    contract = load_package_contract(fixture.descriptor)

    assert tuple(resource.name for resource in contract.resources) == EXPECTED_RESOURCE_NAMES
    visits = next(resource for resource in contract.resources if resource.name == "visits")
    assert [field.duckdb_type for field in visits.fields[:4]] == [
        "VARCHAR", "VARCHAR", "BIGINT", "VARCHAR"
    ]
    assert contract.snapshot == "2026-08-24"
    assert contract.descriptor_sha256
    assert visits.foreign_keys[0].reference_resource == "patients"
    assert next(resource for resource in contract.resources if resource.name == "labs").logical_foreign_keys[0].orphan_rows == 0


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda d: d["resources"].pop(), "exactly eight resources"),
        (lambda d: d["resources"].reverse(), "resource order"),
        (lambda d: d["resources"][0].update(path="../patients.csv"), "unsafe resource path"),
        (lambda d: d["resources"][0]["schema"]["fields"][0].update(type="date"), "unsupported field type"),
        (lambda d: d["resources"][0]["schema"]["fields"][0]["constraints"].update(pattern=".*"), "unsupported constraint"),
    ],
)
def test_load_package_contract_rejects_unsupported_descriptor(
    tmp_path: Path, mutation, message: str
) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    descriptor = json.loads(fixture.descriptor.read_text(encoding="utf-8"))
    mutation(descriptor)
    fixture.descriptor.write_text(json.dumps(descriptor), encoding="utf-8")

    with pytest.raises(DescriptorError, match=message):
        load_package_contract(fixture.descriptor)


def test_export_config_is_immutable(tmp_path: Path) -> None:
    config = ExportConfig(tmp_path / "d.json", tmp_path / "csv", tmp_path / "out")
    with pytest.raises(FrozenInstanceError):
        config.replace = True


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda d: d["resources"][1].update(name=d["resources"][0]["name"]), "duplicate resource name"),
        (lambda d: d["resources"][0]["schema"]["fields"].append(copy.deepcopy(d["resources"][0]["schema"]["fields"][0])), "duplicate field name"),
        (lambda d: d["resources"][0].update(path="nested/patients.csv"), "multi-component resource path"),
        (lambda d: d["resources"][0].update(format="json"), "resource format"),
        (lambda d: d["resources"][0].update(encoding="utf-16"), "unsupported encoding"),
        (lambda d: d["resources"][0]["dialect"].update(doubleQuote=False), "unsupported dialect"),
        (lambda d: d["resources"][0].pop("x-rowCount"), "x-rowCount"),
        (lambda d: d["resources"][0]["schema"].update(missingValues=["NA"]), "missingValues"),
        (lambda d: d["resources"][0]["schema"].update(primaryKey=["patient_id"]), "scalar primary key"),
        (lambda d: d["resources"][4]["x-logicalForeignKeys"][0].update(orphanRows=-1), "logical relationship count"),
        (lambda d: d["x-statisticsSource"].pop("snapshot"), "snapshot"),
    ],
)
def test_load_package_contract_rejects_malformed_contract(tmp_path: Path, mutation, message: str) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    descriptor = json.loads(fixture.descriptor.read_text(encoding="utf-8"))
    mutation(descriptor)
    fixture.descriptor.write_text(json.dumps(descriptor), encoding="utf-8")

    with pytest.raises(DescriptorError, match=message):
        load_package_contract(fixture.descriptor)


def test_load_package_contract_rejects_unknown_relationship_field(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    descriptor = json.loads(fixture.descriptor.read_text(encoding="utf-8"))
    descriptor["resources"][2]["schema"]["foreignKeys"][0]["reference"]["fields"] = "missing_id"
    fixture.descriptor.write_text(json.dumps(descriptor), encoding="utf-8")

    with pytest.raises(DescriptorError, match="relationship reference"):
        load_package_contract(fixture.descriptor)


@pytest.mark.parametrize("constraint", ["minimum", "maximum"])
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_load_package_contract_rejects_non_finite_numeric_constraints(
    tmp_path: Path, constraint: str, value: float
) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    descriptor = json.loads(fixture.descriptor.read_text(encoding="utf-8"))
    descriptor["resources"][2]["schema"]["fields"][2]["constraints"][constraint] = value
    fixture.descriptor.write_text(json.dumps(descriptor), encoding="utf-8")

    with pytest.raises(DescriptorError, match="finite"):
        load_package_contract(fixture.descriptor)


def test_load_package_contract_rejects_extra_dialect_semantics(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    descriptor = json.loads(fixture.descriptor.read_text(encoding="utf-8"))
    descriptor["resources"][0]["dialect"]["skipInitialSpace"] = True
    fixture.descriptor.write_text(json.dumps(descriptor), encoding="utf-8")

    with pytest.raises(DescriptorError, match="unsupported dialect"):
        load_package_contract(fixture.descriptor)


def test_load_package_contract_rejects_non_object_json(tmp_path: Path) -> None:
    descriptor = tmp_path / "datapackage.json"
    descriptor.write_text("[]", encoding="utf-8")
    with pytest.raises(DescriptorError, match="descriptor object"):
        load_package_contract(descriptor)


def test_load_package_contract_rejects_symlink_and_special_file(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path / "fixture")
    symlink = tmp_path / "link.json"
    symlink.symlink_to(fixture.descriptor)
    with pytest.raises(DescriptorError, match="regular descriptor file"):
        load_package_contract(symlink)

    fifo = tmp_path / "fifo.json"
    os.mkfifo(fifo)
    with pytest.raises(DescriptorError, match="regular descriptor file"):
        load_package_contract(fifo)


def test_descriptor_errors_do_not_echo_descriptor_contents(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    descriptor = json.loads(fixture.descriptor.read_text(encoding="utf-8"))
    descriptor["resources"][0]["path"] = "SECRET-PATH.txt"
    fixture.descriptor.write_text(json.dumps(descriptor), encoding="utf-8")

    with pytest.raises(DescriptorError) as error:
        load_package_contract(fixture.descriptor)
    assert "SECRET-PATH" not in str(error.value)


def test_tiny_snapshot_has_exact_keys_and_declared_labs_encoding(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    contract = load_package_contract(fixture.descriptor)

    assert {name: len(values) for name, values in fixture.rows.items()} == {
        "patients": 2,
        "patients_augmented": 2,
        "visits": 2,
        "visits_augmented": 2,
        "labs": 1,
        "medications": 1,
        "problem_list": 1,
        "referrals": 1,
    }
    assert fixture.rows["visits"][0]["patient_id"] == "SYN-P001"
    assert fixture.rows["visits"][0]["visit_id"] == "SYN-V001"
    assert fixture.rows["visits"][0]["age_in_days"] == 100
    labs = next(resource for resource in contract.resources if resource.name == "labs")
    assert labs.encoding == "iso-8859-1"
    assert fixture.data_root.joinpath("labs.csv").read_bytes().startswith(b"patient_id,")


def test_package_contract_descriptor_is_deeply_immutable(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    contract = load_package_contract(fixture.descriptor)

    with pytest.raises(TypeError):
        contract.descriptor["name"] = "changed"
    with pytest.raises(TypeError):
        contract.descriptor["resources"][0]["name"] = "changed"
    with pytest.raises(AttributeError):
        contract.descriptor["resources"].append({})

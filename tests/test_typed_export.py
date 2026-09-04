from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from dataclasses import FrozenInstanceError
from pathlib import Path

import duckdb
import pytest

from scripts.typed_export import (
    EXPECTED_RESOURCE_NAMES,
    DescriptorError,
    ExportConfig,
    ExportError,
    SourceFingerprint,
    fingerprint_sources,
    load_package_contract,
    preflight_sources,
    quote_identifier,
    quote_literal,
    typed_csv_query,
    verify_sources_unchanged,
)
from tests.analytical_export_fixtures import (
    replace_csv_cell,
    replace_labs_cell_bytes,
    write_tiny_snapshot,
)


def test_typed_csv_query_maps_values_without_inference(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    package = load_package_contract(fixture.descriptor)
    states = preflight_sources(package, fixture.data_root)
    visits = next(resource for resource in package.resources if resource.name == "visits")
    source = next(state for state in states if state.resource.name == "visits")

    rows = duckdb.connect().execute(typed_csv_query(visits, source.path)).fetchall()

    assert rows[0][0:3] == ("SYN-P001", "SYN-V001", 100)


@pytest.mark.parametrize("bad_value", ["1.0", "1e3", "9223372036854775808"])
def test_integer_conversion_fails_without_echoing_value(tmp_path: Path, bad_value: str) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    replace_csv_cell(fixture, "visits", "age_in_days", bad_value)
    package = load_package_contract(fixture.descriptor)
    source = preflight_sources(package, fixture.data_root)[2]

    with pytest.raises(Exception) as caught:
        duckdb.connect().execute(typed_csv_query(package.resources[2], source.path)).fetchall()

    assert "visits.age_in_days failed integer conversion" in str(caught.value)
    assert bad_value not in str(caught.value)


def test_labs_uses_literal_iso_8859_1_decoding(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    replace_labs_cell_bytes(fixture, "result_value", b"caf\xe9\x81")
    package = load_package_contract(fixture.descriptor)
    source = preflight_sources(package, fixture.data_root)[4]
    query = typed_csv_query(package.resources[4], source.path)

    value = duckdb.connect().execute(
        f'SELECT "result_value" FROM ({query}) AS typed_labs'
    ).fetchone()[0]

    assert value == "caf\u00e9\u0081"


def test_preflight_collects_all_eight_sources_before_hashing(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    package = load_package_contract(fixture.descriptor)

    states = preflight_sources(package, fixture.data_root)

    assert [state.resource.name for state in states] == list(EXPECTED_RESOURCE_NAMES)
    assert all(state.path.parent == fixture.data_root.resolve() for state in states)


@pytest.mark.parametrize("mutation", ["truncate", "append"])
def test_preflight_rejects_declared_row_count_mismatch(tmp_path: Path, mutation: str) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    path = fixture.data_root / "patients.csv"
    original_lines = path.read_bytes().splitlines(keepends=True)
    if mutation == "truncate":
        path.write_bytes(b"".join(original_lines[:2]))
    else:
        path.write_bytes(b"".join(original_lines + [original_lines[1]]))
    package = load_package_contract(fixture.descriptor)

    with pytest.raises(ExportError, match="patients"):
        preflight_sources(package, fixture.data_root)


def test_preflight_collects_multiple_failures_before_any_hash_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    patients_path = fixture.data_root / "patients.csv"
    visits_path = fixture.data_root / "visits.csv"
    patients_original = patients_path.read_bytes()
    visits_original = visits_path.read_bytes()
    patients_path.write_bytes(b"SECRET-HEADER\n" + patients_original.split(b"\n", 1)[1])
    visits_path.unlink()
    package = load_package_contract(fixture.descriptor)
    opened_modes: list[str] = []
    original_open = Path.open

    def tracking_open(path: Path, mode: str = "r", *args, **kwargs):
        opened_modes.append(mode)
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracking_open)

    with pytest.raises(ExportError) as error:
        preflight_sources(package, fixture.data_root)

    assert "patients" in str(error.value)
    assert "visits" in str(error.value)
    assert "rb" not in opened_modes

    patients_path.write_bytes(patients_original)
    visits_path.write_bytes(visits_original)
    states = preflight_sources(package, fixture.data_root)
    fingerprint_sources(states)
    assert "rb" in opened_modes


def test_preflight_rejects_header_order_mismatch_without_echoing_header(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    path = fixture.data_root / "patients.csv"
    lines = path.read_bytes().splitlines(keepends=True)
    lines[0] = b"SECRET-PATIENT-HEADER\n"
    path.write_bytes(b"".join(lines))
    package = load_package_contract(fixture.descriptor)

    with pytest.raises(ExportError, match="patients") as error:
        preflight_sources(package, fixture.data_root)

    assert "SECRET-PATIENT-HEADER" not in str(error.value)


@pytest.mark.parametrize("kind", ["missing", "symlink", "fifo"])
def test_preflight_rejects_missing_symlinked_and_nonregular_sources(tmp_path: Path, kind: str) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    path = fixture.data_root / "patients.csv"
    if kind == "missing":
        path.unlink()
    elif kind == "symlink":
        target = tmp_path / "elsewhere.csv"
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
    else:
        path.unlink()
        os.mkfifo(path)
    package = load_package_contract(fixture.descriptor)

    with pytest.raises(ExportError, match="patients"):
        preflight_sources(package, fixture.data_root)


def test_preflight_rejects_invalid_utf8_without_echoing_source_content(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    path = fixture.data_root / "patients.csv"
    path.write_bytes(path.read_bytes().replace(b"SYN-P001", b"SECRET-\xff"))
    package = load_package_contract(fixture.descriptor)

    with pytest.raises(ExportError, match="patients") as error:
        preflight_sources(package, fixture.data_root)

    assert "SECRET" not in str(error.value)


def test_typed_csv_query_maps_empty_strings_to_null_and_preserves_strings(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    replace_csv_cell(fixture, "visits", "enc_diag_1", "")
    package = load_package_contract(fixture.descriptor)
    source = preflight_sources(package, fixture.data_root)[2]

    rows = duckdb.connect().execute(typed_csv_query(package.resources[2], source.path)).fetchall()

    assert rows[0][3] == "Office Visit"
    assert rows[0][10] is None


@pytest.mark.parametrize("bad_value", ["NaN", "Inf", "1e309"])
def test_number_conversion_requires_finite_double(tmp_path: Path, bad_value: str) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    replace_csv_cell(fixture, "visits", "weight_oz", bad_value)
    package = load_package_contract(fixture.descriptor)
    source = preflight_sources(package, fixture.data_root)[2]

    with pytest.raises(Exception) as caught:
        duckdb.connect().execute(typed_csv_query(package.resources[2], source.path)).fetchall()

    assert "visits.weight_oz failed number conversion" in str(caught.value)
    assert bad_value not in str(caught.value)


def test_sql_quoting_escapes_identifiers_and_literals() -> None:
    assert quote_identifier('a"b') == '"a""b"'
    assert quote_literal("a'b") == "'a''b'"
    assert quote_literal(True) == "TRUE"
    assert quote_literal(3.5) == "3.5"


def test_fingerprint_captures_basename_hash_shape_and_stat_state(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    package = load_package_contract(fixture.descriptor)
    states = preflight_sources(package, fixture.data_root)

    fingerprints = fingerprint_sources(states)
    first = fingerprints[0]
    first_state = states[0]

    assert isinstance(first, SourceFingerprint)
    assert first.basename == "patients.csv"
    assert first.size == first_state.size
    assert first.sha256 == hashlib.sha256(first_state.path.read_bytes()).hexdigest()
    assert first.row_count == 2
    assert first.field_count == len(first_state.resource.fields)
    assert (first_state.device, first_state.inode, first_state.size, first_state.mtime_ns) == (
        first_state.path.stat().st_dev,
        first_state.path.stat().st_ino,
        first_state.path.stat().st_size,
        first_state.path.stat().st_mtime_ns,
    )


def test_verify_sources_unchanged_detects_mutation(tmp_path: Path) -> None:
    fixture = write_tiny_snapshot(tmp_path)
    package = load_package_contract(fixture.descriptor)
    states = preflight_sources(package, fixture.data_root)
    path = fixture.data_root / "patients.csv"
    path.write_bytes(path.read_bytes() + b"\n")

    with pytest.raises(ExportError, match="patients"):
        verify_sources_unchanged(states)


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

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import stat
import traceback
from dataclasses import FrozenInstanceError
from pathlib import Path

import duckdb
import pytest

from scripts.typed_export import (
    EXPECTED_RESOURCE_NAMES,
    BuildProvenance,
    BundleRun,
    DescriptorError,
    ExportConfig,
    ExportError,
    LifecycleError,
    OutputCollisionError,
    OutputFingerprint,
    PackageContract,
    SourceFingerprint,
    UnsafePathError,
    build_manifest,
    ensure_safe_output,
    fingerprint_sources,
    load_package_contract,
    preflight_sources,
    quote_identifier,
    quote_literal,
    sha256_file,
    typed_csv_query,
    verify_bundle_manifest,
    verify_sources_unchanged,
    write_manifest,
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


def test_final_review_labs_transcode_is_chunked_and_staged_privately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches whole-file labs decoding or transcoding outside private staging."""
    import scripts.typed_export as exporter

    fixture = write_tiny_snapshot(tmp_path / "input")
    replace_labs_cell_bytes(fixture, "result_value", b"caf\xe9\x81")
    package = load_package_contract(fixture.descriptor)
    source = preflight_sources(package, fixture.data_root)[4]
    staging = tmp_path / "private-staging"
    staging.mkdir(mode=0o700)
    original_open = Path.open
    read_sizes: list[int] = []

    class BoundedReader:
        def __init__(self, handle) -> None:
            self.handle = handle

        def __enter__(self):
            self.handle.__enter__()
            return self

        def __exit__(self, *args: object) -> object:
            return self.handle.__exit__(*args)

        def read(self, size: int = -1) -> bytes:
            read_sizes.append(size)
            assert 0 < size <= 1024 * 1024
            return self.handle.read(size)

    def bounded_open(path: Path, mode: str = "r", *args, **kwargs):
        handle = original_open(path, mode, *args, **kwargs)
        if path == source.path and mode == "rb":
            return BoundedReader(handle)
        return handle

    monkeypatch.setattr(Path, "open", bounded_open)
    try:
        query = typed_csv_query(
            package.resources[4], source.path, temporary_directory=staging
        )
        transcoded = list(staging.iterdir())
        assert len(transcoded) == 1
        assert stat.S_IMODE(transcoded[0].stat().st_mode) == 0o600
        value = duckdb.connect().execute(
            f'SELECT "result_value" FROM ({query}) AS typed_labs'
        ).fetchone()[0]
        assert value == "caf\u00e9\u0081"
        assert read_sizes
    finally:
        exporter._remove_transcoded_sources()
    assert list(staging.iterdir()) == []


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


def test_final_review_fingerprint_reuses_exact_preflight_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches a second full CSV parse after exact preflight already counted rows."""
    import scripts.typed_export as exporter

    fixture = write_tiny_snapshot(tmp_path)
    package = load_package_contract(fixture.descriptor)
    states = preflight_sources(package, fixture.data_root)

    def reject_duplicate_parse(*args: object, **kwargs: object) -> object:
        raise AssertionError("fingerprinting reparsed CSV text")

    monkeypatch.setattr(exporter.csv, "reader", reject_duplicate_parse)
    fingerprints = fingerprint_sources(states)

    assert [item.row_count for item in fingerprints] == [
        state.resource.row_count for state in states
    ]
    assert [item.field_count for item in fingerprints] == [
        len(state.resource.fields) for state in states
    ]


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
        (lambda d: d["resources"][1].update(path=d["resources"][0]["path"]), "duplicate resource path"),
        (lambda d: d["resources"][0]["schema"]["fields"].append(copy.deepcopy(d["resources"][0]["schema"]["fields"][0])), "duplicate field name"),
        (lambda d: d["resources"][0].update(path="nested/patients.csv"), "multi-component resource path"),
        (lambda d: d["resources"][0].update(format="json"), "resource format"),
        (lambda d: d["resources"][0].update(encoding="utf-16"), "unsupported encoding"),
        (lambda d: d["resources"][0]["dialect"].update(doubleQuote=False), "unsupported dialect"),
        (lambda d: d["resources"][0].pop("x-rowCount"), "x-rowCount"),
        (lambda d: d["resources"][0]["schema"].pop("missingValues"), "missingValues"),
        (lambda d: d["resources"][0]["schema"].update(missingValues=["NA"]), "missingValues"),
        (lambda d: d["resources"][0]["schema"].update(primaryKey=["patient_id"]), "scalar primary key"),
        (lambda d: d["resources"][4]["x-logicalForeignKeys"][0].update(orphanRows=-1), "logical relationship count"),
        (lambda d: d["resources"][4]["x-logicalForeignKeys"][0].pop("orphanRows"), "logical relationship count"),
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


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "/private/patients.csv",
        "C:\\private\\patients.csv",
        "\\\\server\\share\\patients.csv",
        "..\\patients.csv",
    ],
)
def test_final_review_descriptor_rejects_cross_platform_unsafe_resource_paths(
    tmp_path: Path, unsafe_path: str
) -> None:
    """Catches POSIX or Windows absolute/traversal resource paths on any host."""
    fixture = write_tiny_snapshot(tmp_path)
    descriptor = json.loads(fixture.descriptor.read_text(encoding="utf-8"))
    descriptor["resources"][0]["path"] = unsafe_path
    fixture.descriptor.write_text(json.dumps(descriptor), encoding="utf-8")

    with pytest.raises(DescriptorError, match="unsafe resource path") as caught:
        load_package_contract(fixture.descriptor)

    assert unsafe_path not in str(caught.value)


def test_final_review_descriptor_rejects_duplicate_json_object_keys(
    tmp_path: Path,
) -> None:
    """Catches ambiguous descriptors whose duplicate JSON keys would otherwise win."""
    fixture = write_tiny_snapshot(tmp_path)
    payload = fixture.descriptor.read_text(encoding="utf-8").replace(
        '"name": "ppoc-pediatric-ehr"',
        '"name": "SECRET-DUPLICATE",\n  "name": "ppoc-pediatric-ehr"',
        1,
    )
    fixture.descriptor.write_text(payload, encoding="utf-8")

    with pytest.raises(DescriptorError) as caught:
        load_package_contract(fixture.descriptor)

    assert "SECRET-DUPLICATE" not in str(caught.value)


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


def _load_tiny_tables(fixture) -> tuple[PackageContract, duckdb.DuckDBPyConnection]:
    package = load_package_contract(fixture.descriptor)
    sources = preflight_sources(package, fixture.data_root)
    connection = duckdb.connect()
    for source in sources:
        table = quote_identifier(source.resource.name)
        connection.execute(
            f"CREATE TABLE main.{table} AS {typed_csv_query(source.resource, source.path)}"
        )
    return package, connection


def test_validate_artifact_passes_complete_tiny_snapshot(tmp_path: Path) -> None:
    from scripts.typed_export import validate_artifact

    fixture = write_tiny_snapshot(tmp_path)
    package, connection = _load_tiny_tables(fixture)

    records = validate_artifact(connection, package, lambda resource: f'main."{resource.name}"')

    assert records
    assert {record.status for record in records} == {"PASS"}
    assert all(record.observed is not None for record in records)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            'UPDATE main."patients" SET "patient_id" = \'SYN-P001\' WHERE "patient_id" = \'SYN-P002\'',
            "patients primary key was not unique",
        ),
        (
            'DELETE FROM main."patients" WHERE "patient_id" = \'SYN-P002\'',
            "patients row count did not match",
        ),
        (
            'UPDATE main."patients" SET "patient_id" = NULL WHERE "patient_id" = \'SYN-P001\'',
            "patients.patient_id required count did not match",
        ),
        (
            'UPDATE main."patients" SET "sex" = \'X\' WHERE "patient_id" = \'SYN-P001\'',
            "patients.sex enum count did not match",
        ),
        (
            'UPDATE main."visits" SET "bmi_percentile" = -1 WHERE "visit_id" = \'SYN-V001\'',
            "visits.bmi_percentile minimum count did not match",
        ),
        (
            'UPDATE main."visits" SET "bmi_percentile" = 101 WHERE "visit_id" = \'SYN-V001\'',
            "visits.bmi_percentile maximum count did not match",
        ),
        (
            'UPDATE main."labs" SET "patient_id" = \'SYN-ORPHAN\'',
            "labs.patient_id foreign key count did not match",
        ),
        (
            'UPDATE main."labs" SET "visit_id" = \'SYN-ORPHAN\'',
            "labs.visit_id logical orphan count did not match",
        ),
        (
            'UPDATE main."labs" SET "visit_id" = NULL',
            "labs.visit_id logical null count did not match",
        ),
    ],
)
def test_validate_artifact_rejects_aggregate_rule_violations(
    tmp_path: Path, mutation: str, message: str
) -> None:
    from scripts.typed_export import ValidationError, validate_artifact

    fixture = write_tiny_snapshot(tmp_path)
    package, connection = _load_tiny_tables(fixture)
    connection.execute(mutation)

    with pytest.raises(ValidationError, match=message) as caught:
        validate_artifact(connection, package, lambda resource: f'main."{resource.name}"')

    assert "SYN-P001" not in str(caught.value)
    assert "SYN-ORPHAN" not in str(caught.value)


def test_validate_artifact_rejects_output_column_name_order_and_type(tmp_path: Path) -> None:
    from scripts.typed_export import ValidationError, validate_artifact

    fixture = write_tiny_snapshot(tmp_path)
    package, connection = _load_tiny_tables(fixture)

    for relation, message in (
        ('(SELECT "patient_id" AS "wrong_name", * EXCLUDE ("patient_id") FROM main."patients")', "patients schema did not match"),
        ('(SELECT "sex", "patient_id", * EXCLUDE ("sex", "patient_id") FROM main."patients")', "patients schema did not match"),
        ('(SELECT cast("patient_id" AS BIGINT) AS "patient_id", * EXCLUDE ("patient_id") FROM main."patients")', "patients schema did not match"),
    ):
        with pytest.raises(ValidationError, match=message):
            validate_artifact(
                connection,
                package,
                lambda resource, relation=relation: relation if resource.name == "patients" else f'main."{resource.name}"',
            )


def test_validate_artifact_rejects_missing_primary_key_value(tmp_path: Path) -> None:
    from scripts.typed_export import ValidationError, validate_artifact

    fixture = write_tiny_snapshot(tmp_path)
    descriptor = json.loads(fixture.descriptor.read_text(encoding="utf-8"))
    descriptor["resources"][0]["schema"]["fields"][0]["constraints"]["required"] = False
    fixture.descriptor.write_text(json.dumps(descriptor), encoding="utf-8")
    package, connection = _load_tiny_tables(fixture)
    connection.execute('UPDATE main."patients" SET "patient_id" = NULL WHERE "patient_id" = \'SYN-P001\'')

    with pytest.raises(ValidationError, match="patients primary key was not complete"):
        validate_artifact(connection, package, lambda resource: f'main."{resource.name}"')


def test_validate_artifact_compares_logical_orphans_without_strict_fk_failure(tmp_path: Path) -> None:
    from scripts.typed_export import validate_artifact

    fixture = write_tiny_snapshot(tmp_path)
    descriptor = json.loads(fixture.descriptor.read_text(encoding="utf-8"))
    descriptor["resources"][4]["x-logicalForeignKeys"][0]["orphanRows"] = 1
    fixture.descriptor.write_text(json.dumps(descriptor), encoding="utf-8")
    package, connection = _load_tiny_tables(fixture)
    connection.execute('UPDATE main."labs" SET "visit_id" = \'SYN-ORPHAN\'')

    records = validate_artifact(connection, package, lambda resource: f'main."{resource.name}"')

    logical = [record for record in records if record.resource == "labs" and record.rule == "logical orphan count"]
    assert [(record.expected, record.observed) for record in logical] == [(1, 1)]


def _provenance() -> BuildProvenance:
    return BuildProvenance("2026-09-04T00:00:00Z", "3.13", "1", "1", None, None, "a" * 64)


def test_manifest_is_canonical_private_and_contains_no_absolute_paths(tmp_path: Path) -> None:
    """Catches noncanonical or world-readable manifest publication."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    manifest = build_manifest("parquet-bundle", load_package_contract(fixture.descriptor), _provenance(), (), (), ())
    destination = tmp_path / "manifest.json"
    write_manifest(destination, manifest)
    payload = destination.read_text(encoding="utf-8")
    assert payload == json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    assert set(json.loads(payload)) == {"manifestVersion", "status", "artifactType", "package", "build", "descriptor", "sources", "outputs", "validation"}
    assert str(fixture.data_root) not in payload
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    manifest["build"] = {"unsafe": str(fixture.data_root)}
    with pytest.raises(LifecycleError):
        write_manifest(tmp_path / "unsafe-manifest.json", manifest)


def test_safe_output_rejects_checkout_inputs_symlinks_and_special_files(tmp_path: Path) -> None:
    """Catches output paths that could overwrite inputs or escape through links."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    package = load_package_contract(fixture.descriptor)
    sources = preflight_sources(package, fixture.data_root)
    repo = tmp_path / "repo"
    repo.mkdir()
    for candidate in (repo, repo / "below", fixture.descriptor, fixture.data_root, fixture.data_root / "patients.csv"):
        with pytest.raises(UnsafePathError):
            ensure_safe_output(repo, package, sources, candidate)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = outside / "link"
    link.symlink_to(fixture.data_root, target_is_directory=True)
    with pytest.raises(UnsafePathError):
        ensure_safe_output(repo, package, sources, link)
    fifo = outside / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(UnsafePathError):
        ensure_safe_output(repo, package, sources, fifo)


def test_bundle_start_permissions_collision_and_stale_recovery(tmp_path: Path) -> None:
    """Catches unsafe staging permissions and accidental stale-artifact cleanup."""
    output = tmp_path / "published"
    run = BundleRun.start(output, "parquet-bundle", False)
    assert stat.S_IMODE(run.staging.stat().st_mode) == 0o700
    (run.staging / "data").write_text("tiny", encoding="utf-8")
    os.chmod(run.staging / "data", 0o600)
    run.promote(lambda bundle: None)
    with pytest.raises(OutputCollisionError, match="rerun with --replace"):
        BundleRun.start(output, "parquet-bundle", False)
    assert (output / "data").read_text(encoding="utf-8") == "tiny"
    (tmp_path / ".new.parquet-bundle.partial-deadbeefdeadbeef").mkdir()
    with pytest.raises(LifecycleError, match="new"):
        BundleRun.start(tmp_path / "new", "parquet-bundle", False)


def test_final_review_bundle_start_prevalidates_replace_target_before_staging(
    tmp_path: Path,
) -> None:
    """Catches restricted staging created before an invalid replace target is rejected."""
    output = tmp_path / "published"
    output.mkdir(mode=0o700)
    unexpected = output / "unexpected"
    unexpected.write_text("not an exporter bundle", encoding="utf-8")
    os.chmod(unexpected, 0o600)

    with pytest.raises(LifecycleError):
        BundleRun.start(output, "parquet-bundle", True)

    assert not list(tmp_path.glob(".published.parquet-bundle.partial-*"))


@pytest.mark.parametrize(
    ("export_name", "fallback"),
    (("parquet", "parquet export failed"), ("duckdb", "duckdb export failed")),
)
@pytest.mark.parametrize("failure_point", ["fingerprint", "staging"])
def test_final_review_export_setup_failures_are_redacted_for_library_callers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    export_name: str,
    fallback: str,
    failure_point: str,
) -> None:
    """Catches raw fingerprinting or staging exceptions escaping the library boundary."""
    import scripts.typed_export as exporter

    fixture = write_tiny_snapshot(tmp_path / "input")
    output = tmp_path / export_name
    secret = "SECRET-SETUP-PATH-OR-VALUE"
    if failure_point == "fingerprint":
        monkeypatch.setattr(
            exporter,
            "fingerprint_sources",
            lambda states: (_ for _ in ()).throw(OSError(secret)),
        )
    else:
        original_mkdir = Path.mkdir

        def fail_staging(path: Path, *args: object, **kwargs: object) -> None:
            if ".partial-" in path.name:
                raise OSError(secret)
            original_mkdir(path, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", fail_staging)
    export_bundle = (
        exporter.export_parquet_bundle
        if export_name == "parquet"
        else exporter.export_duckdb_bundle
    )

    with pytest.raises(ExportError) as caught:
        export_bundle(ExportConfig(fixture.descriptor, fixture.data_root, output))

    assert str(caught.value) in {fallback, "bundle staging failed"}
    assert secret not in "".join(traceback.format_exception(caught.value))
    assert not output.exists()


@pytest.mark.parametrize("export_name", ["parquet", "duckdb"])
def test_final_review_export_closes_duckdb_before_discarding_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    export_name: str,
) -> None:
    """Catches failure cleanup that removes database/spill files before DuckDB closes."""
    import scripts.typed_export as exporter

    fixture = write_tiny_snapshot(tmp_path / "input")
    real_connect = exporter.duckdb.connect
    connections: list[duckdb.DuckDBPyConnection] = []

    def tracking_connect(*args: object, **kwargs: object) -> duckdb.DuckDBPyConnection:
        connection = real_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(exporter.duckdb, "connect", tracking_connect)
    execution_started = False

    def invalid_query(*args: object, **kwargs: object) -> str:
        nonlocal execution_started
        execution_started = True
        return "SELECT * FROM missing_private_source"

    monkeypatch.setattr(exporter, "typed_csv_query", invalid_query)
    original_remove_transcodes = exporter._remove_transcoded_sources
    observed_transcode_cleanup_after_close = False

    def assert_closed_then_remove_transcodes() -> None:
        nonlocal observed_transcode_cleanup_after_close
        assert execution_started
        assert connections
        with pytest.raises(duckdb.ConnectionException):
            connections[-1].execute("SELECT 1")
        observed_transcode_cleanup_after_close = True
        original_remove_transcodes()

    monkeypatch.setattr(
        exporter,
        "_remove_transcoded_sources",
        assert_closed_then_remove_transcodes,
    )
    original_discard = exporter.BundleRun.discard_staging
    observed_closed = False

    def assert_closed_then_discard(run: BundleRun) -> None:
        nonlocal observed_closed
        assert connections
        with pytest.raises(duckdb.ConnectionException):
            connections[-1].execute("SELECT 1")
        observed_closed = True
        original_discard(run)

    monkeypatch.setattr(exporter.BundleRun, "discard_staging", assert_closed_then_discard)
    export_bundle = (
        exporter.export_parquet_bundle
        if export_name == "parquet"
        else exporter.export_duckdb_bundle
    )

    with pytest.raises(ExportError):
        export_bundle(
            ExportConfig(fixture.descriptor, fixture.data_root, tmp_path / export_name)
        )

    assert observed_closed
    assert observed_transcode_cleanup_after_close


def test_bundle_replacement_restores_verified_old_bundle_after_post_backup_failure(tmp_path: Path) -> None:
    """Catches replacement that discards a verified target after final verification fails."""
    output, _ = _complete_manifest_bundle(tmp_path)
    original = (output / "ppoc.duckdb").read_bytes()
    os.chmod(output / "ppoc.duckdb", 0o644)
    with pytest.raises(LifecycleError):
        verify_bundle_manifest(output, "duckdb-bundle", frozenset({"manifest.json", "ppoc.duckdb"}))
    os.chmod(output / "ppoc.duckdb", 0o600)
    run = BundleRun.start(output, "duckdb-bundle", True)
    (run.staging / "data").write_text("new", encoding="utf-8")
    os.chmod(run.staging / "data", 0o600)
    def fail_only_after_backup(path: Path) -> None:
        if path == output:
            raise RuntimeError("post promote")

    with pytest.raises(LifecycleError, match="bundle verification failed"):
        run.promote(fail_only_after_backup)
    assert (output / "ppoc.duckdb").read_bytes() == original
    assert not run.staging.exists()


def test_verify_bundle_manifest_rejects_wrong_kind_and_unknown_inventory(tmp_path: Path) -> None:
    """Catches replacement acceptance of a bundle the lifecycle does not own."""
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    manifest = {"manifestVersion": 1, "status": "PASS", "artifactType": "duckdb-bundle", "package": {}, "build": {}, "descriptor": {}, "sources": [], "outputs": [], "validation": {"status": "PASS", "checkCount": 0, "failedChecks": 0}}
    write_manifest(bundle / "manifest.json", manifest)
    (bundle / "unexpected").write_text("x", encoding="utf-8")
    with pytest.raises(LifecycleError):
        verify_bundle_manifest(bundle, "parquet-bundle", frozenset({"manifest.json"}))


def _complete_manifest_bundle(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    fixture = write_tiny_snapshot(tmp_path / "input")
    bundle = tmp_path / "bundle"
    bundle.mkdir(mode=0o700)
    artifact = bundle / "ppoc.duckdb"
    artifact.write_bytes(b"tiny synthetic artifact")
    os.chmod(artifact, 0o600)
    package = load_package_contract(fixture.descriptor)
    manifest = build_manifest(
        "duckdb-bundle", package, _provenance(),
        fingerprint_sources(preflight_sources(package, fixture.data_root)),
        (OutputFingerprint("ppoc.duckdb", artifact.stat().st_size, sha256_file(artifact)),), (),
    )
    write_manifest(bundle / "manifest.json", manifest)
    return bundle, manifest


@pytest.mark.parametrize("mutation", ["missing-size", "missing-hash", "modified-output", "noncanonical"])
def test_verify_bundle_manifest_rejects_incomplete_modified_and_noncanonical_contracts(tmp_path: Path, mutation: str) -> None:
    """Catches acceptance of a manifest that cannot bind the complete bundle bytes."""
    bundle, manifest = _complete_manifest_bundle(tmp_path)
    if mutation == "missing-size":
        del manifest["outputs"][0]["size"]
    elif mutation == "missing-hash":
        del manifest["outputs"][0]["sha256"]
    elif mutation == "modified-output":
        (bundle / "ppoc.duckdb").write_bytes(b"modified")
        os.chmod(bundle / "ppoc.duckdb", 0o600)
    else:
        (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        os.chmod(bundle / "manifest.json", 0o600)
    if mutation in {"missing-size", "missing-hash"}:
        write_manifest(bundle / "manifest.json", manifest)
    with pytest.raises(LifecycleError):
        verify_bundle_manifest(bundle, "duckdb-bundle", frozenset({"manifest.json", "ppoc.duckdb"}))


def test_bundle_promotion_rejects_relaxed_staged_file_modes_with_noop_verifier(tmp_path: Path) -> None:
    """Catches lifecycle promotion of world-readable artifacts when a callback is lax."""
    output = tmp_path / "published"
    run = BundleRun.start(output, "parquet-bundle", False)
    (run.staging / "artifact").write_text("tiny", encoding="utf-8")
    with pytest.raises(LifecycleError):
        run.promote(lambda _: None)
    assert not output.exists()


def test_bundle_promotion_redacts_untrusted_verifier_exceptions(tmp_path: Path) -> None:
    """Catches source/value text leaking through an arbitrary verifier exception."""
    run = BundleRun.start(tmp_path / "published", "parquet-bundle", False)
    (run.staging / "artifact").write_text("tiny", encoding="utf-8")
    os.chmod(run.staging / "artifact", 0o600)
    secret = "SECRET-SOURCE-VALUE"

    def unsafe_verifier(_: Path) -> None:
        raise RuntimeError(secret)

    with pytest.raises(LifecycleError) as caught:
        run.promote(unsafe_verifier)
    assert "SECRET-SOURCE-VALUE" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert "SECRET-SOURCE-VALUE" not in "".join(traceback.format_exception(caught.value))


def test_bundle_promotion_rechecks_modes_after_verifier_callback(tmp_path: Path) -> None:
    """Catches a callback relaxing an artifact permission after the first lifecycle check."""
    output = tmp_path / "published"
    run = BundleRun.start(output, "parquet-bundle", False)
    artifact = run.staging / "artifact"
    artifact.write_text("tiny", encoding="utf-8")
    os.chmod(artifact, 0o600)

    calls = 0

    def relax_permission(_: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            os.chmod(artifact, 0o644)

    with pytest.raises(LifecycleError):
        run.promote(relax_permission)
    assert not output.exists()


@pytest.mark.parametrize("unsafe_path", ["C:\\private\\clinical.csv", "\\\\server\\share\\clinical.csv"])
def test_manifest_rejects_windows_absolute_paths_on_every_host(tmp_path: Path, unsafe_path: str) -> None:
    """Catches host-dependent parsing that would serialize Windows source paths on POSIX."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    manifest = build_manifest("parquet-bundle", load_package_contract(fixture.descriptor), _provenance(), (), (), ())
    manifest["build"] = {"unsafe": unsafe_path}
    with pytest.raises(LifecycleError):
        write_manifest(tmp_path / "manifest.json", manifest)

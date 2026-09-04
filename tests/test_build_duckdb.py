from __future__ import annotations

import json
import stat
from pathlib import Path

import duckdb
import pytest

from scripts.typed_export import (
    ExportConfig,
    ExportError,
    LifecycleError,
    OutputCollisionError,
    export_duckdb_bundle,
    load_package_contract,
    sha256_file,
    verify_duckdb_bundle,
)
from tests.analytical_export_fixtures import (
    replace_csv_cell,
    replace_labs_cell_bytes,
    write_tiny_snapshot,
)

RESOURCE_NAMES = (
    "patients", "patients_augmented", "visits", "visits_augmented",
    "labs", "medications", "problem_list", "referrals",
)
META_NAMES = ("build", "resources", "descriptor", "validations")


def test_export_duckdb_bundle_materializes_resources_metadata_and_constraints(tmp_path: Path) -> None:
    """Catches an export that omits typed tables, metadata, or persisted constraints."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    output = tmp_path / "duckdb"

    result = export_duckdb_bundle(ExportConfig(fixture.descriptor, fixture.data_root, output))

    package = load_package_contract(fixture.descriptor)
    assert result == output
    assert {path.name for path in output.iterdir()} == {"ppoc.duckdb", "manifest.json"}
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert stat.S_IMODE((output / "ppoc.duckdb").stat().st_mode) == 0o600
    connection = duckdb.connect(str(output / "ppoc.duckdb"), read_only=True)
    try:
        tables = set(connection.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema IN ('main', 'ppoc_meta')"
        ).fetchall())
        assert tables == {*(('main', name) for name in RESOURCE_NAMES), *(('ppoc_meta', name) for name in META_NAMES)}
        assert connection.execute('SELECT count(*) FROM main."visits"').fetchone() == (2,)
        assert connection.execute('SELECT "age_in_days" FROM main."visits" ORDER BY "visit_id"').fetchall() == [(100,), (200,)]
        for resource in package.resources:
            columns = connection.execute(f"DESCRIBE main.\"{resource.name}\"").fetchall()
            assert [(item[0], item[1]) for item in columns] == [
                (field.name, field.duckdb_type) for field in resource.fields
            ]
            assert [item[2] for item in columns] == ["NO" if field.required else "YES" for field in resource.fields]
        constraints = connection.execute(
            "SELECT constraint_type, constraint_text FROM duckdb_constraints() "
            "WHERE schema_name = 'main'"
        ).fetchall()
        assert any(kind == "NOT NULL" for kind, _ in constraints)
        assert any(kind == "CHECK" for kind, _ in constraints)
        assert not any(kind in {"PRIMARY KEY", "FOREIGN KEY"} for kind, _ in constraints)
        assert connection.execute("SELECT * FROM duckdb_indexes()").fetchall() == []
        assert connection.execute("SELECT * FROM duckdb_views() WHERE schema_name IN ('main', 'ppoc_meta') AND NOT internal").fetchall() == []
        assert connection.execute("SELECT * FROM duckdb_sequences() WHERE schema_name IN ('main', 'ppoc_meta')").fetchall() == []
        assert connection.execute("SELECT * FROM duckdb_functions() WHERE schema_name IN ('main', 'ppoc_meta') AND function_type = 'macro' AND NOT internal").fetchall() == []
        assert connection.execute("SELECT count(*) FROM ppoc_meta.build").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM ppoc_meta.resources").fetchone() == (8,)
        assert connection.execute("SELECT count(*) FROM ppoc_meta.descriptor").fetchone() == (1,)
        assert connection.execute("SELECT count(*) FROM ppoc_meta.validations").fetchone()[0] > 0
    finally:
        connection.close()


def test_export_duckdb_bundle_preserves_nulls_latin_1_metadata_and_manifest_binding(tmp_path: Path) -> None:
    """Catches changed nullable/literal lab values or an unbound DuckDB manifest."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    replace_csv_cell(fixture, "visits", "weight_oz", "")
    replace_labs_cell_bytes(fixture, "result_value", b"caf\xe9\x81")
    output = export_duckdb_bundle(ExportConfig(fixture.descriptor, fixture.data_root, tmp_path / "duckdb"))

    connection = duckdb.connect(str(output / "ppoc.duckdb"), read_only=True)
    try:
        assert connection.execute('SELECT "weight_oz" FROM main."visits" ORDER BY "visit_id"').fetchone() == (None,)
        assert connection.execute('SELECT "result_value" FROM main."labs"').fetchone() == ("café\x81",)
        descriptor_json = connection.execute("SELECT descriptor_json FROM ppoc_meta.descriptor").fetchone()[0]
        assert json.loads(descriptor_json)["name"] == "ppoc-pediatric-ehr"
    finally:
        connection.close()
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    db_output = next(item for item in manifest["outputs"] if item["basename"] == "ppoc.duckdb")
    assert db_output["sha256"] == sha256_file(output / "ppoc.duckdb")
    assert db_output["tables"] == [[name, 2 if name in {"patients", "patients_augmented", "visits", "visits_augmented"} else 1, len(next(resource.fields for resource in load_package_contract(fixture.descriptor).resources if resource.name == name))] for name in RESOURCE_NAMES]
    verify_duckdb_bundle(output, load_package_contract(fixture.descriptor))


def test_export_duckdb_bundle_is_logically_stable_across_fresh_outputs(tmp_path: Path) -> None:
    """Catches typed database contents that drift between fresh runs despite source equality."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    first = export_duckdb_bundle(ExportConfig(fixture.descriptor, fixture.data_root, tmp_path / "first"))
    second = export_duckdb_bundle(ExportConfig(fixture.descriptor, fixture.data_root, tmp_path / "second"))
    for name in RESOURCE_NAMES:
        connections = [duckdb.connect(str(bundle / "ppoc.duckdb"), read_only=True) for bundle in (first, second)]
        try:
            assert connections[0].execute(f'SELECT * FROM main."{name}"').fetchall() == connections[1].execute(f'SELECT * FROM main."{name}"').fetchall()
        finally:
            for connection in connections:
                connection.close()


def test_export_duckdb_bundle_rejects_source_mutation_without_promotion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Catches a database promoted after an input changes during export."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    output = tmp_path / "duckdb"
    import scripts.typed_export as exporter

    original = exporter.validate_artifact

    def mutate_after_validation(*args: object, **kwargs: object) -> object:
        result = original(*args, **kwargs)
        replace_csv_cell(fixture, "visits", "age_in_days", "999")
        return result

    monkeypatch.setattr(exporter, "validate_artifact", mutate_after_validation)
    with pytest.raises(ExportError):
        export_duckdb_bundle(ExportConfig(fixture.descriptor, fixture.data_root, output))
    assert not output.exists()


def test_export_duckdb_bundle_rolls_back_conversion_validation_collision_and_replacement(tmp_path: Path) -> None:
    """Catches unsafe promotion after conversion/validation failures and unsafe replacement handling."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    output = tmp_path / "duckdb"
    replace_csv_cell(fixture, "visits", "age_in_days", "not-an-integer")
    with pytest.raises(ExportError, match="visits.age_in_days failed integer conversion"):
        export_duckdb_bundle(ExportConfig(fixture.descriptor, fixture.data_root, output))
    assert not output.exists()

    replace_csv_cell(fixture, "visits", "age_in_days", "100")
    replace_csv_cell(fixture, "visits", "encounter_type", "unsupported")
    with pytest.raises(ExportError):
        export_duckdb_bundle(ExportConfig(fixture.descriptor, fixture.data_root, output))
    assert not output.exists()

    replace_csv_cell(fixture, "visits", "encounter_type", "Office Visit")
    export_duckdb_bundle(ExportConfig(fixture.descriptor, fixture.data_root, output))
    with pytest.raises(OutputCollisionError):
        export_duckdb_bundle(ExportConfig(fixture.descriptor, fixture.data_root, output))
    assert export_duckdb_bundle(ExportConfig(fixture.descriptor, fixture.data_root, output, replace=True)) == output


def test_export_duckdb_bundle_restores_verified_bundle_after_final_verification_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Catches replacement that loses the prior verified database after promotion failure."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    output = export_duckdb_bundle(ExportConfig(fixture.descriptor, fixture.data_root, tmp_path / "duckdb"))
    original_manifest = (output / "manifest.json").read_bytes()
    import scripts.typed_export as exporter

    original_verify = exporter.verify_duckdb_bundle

    def reject_only_promoted(path: Path, package: object) -> None:
        if path == output:
            raise LifecycleError("forced promoted verification failure")
        original_verify(path, package)

    monkeypatch.setattr(exporter, "verify_duckdb_bundle", reject_only_promoted)
    with pytest.raises(ExportError):
        export_duckdb_bundle(ExportConfig(fixture.descriptor, fixture.data_root, output, replace=True))
    assert (output / "manifest.json").read_bytes() == original_manifest
    original_verify(output, load_package_contract(fixture.descriptor))

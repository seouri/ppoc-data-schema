from __future__ import annotations

import json
import stat
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.typed_export import (
    ExportConfig,
    ExportError,
    LifecycleError,
    OutputCollisionError,
    export_duckdb_bundle,
    export_parquet_bundle,
    load_package_contract,
    sha256_file,
    verify_parquet_bundle,
    write_manifest,
)
from tests.analytical_export_fixtures import (
    replace_csv_cell,
    replace_labs_cell_bytes,
    write_tiny_snapshot,
)

EXPECTED_FILES = {
    "patients.parquet", "patients_augmented.parquet", "visits.parquet",
    "visits_augmented.parquet", "labs.parquet", "medications.parquet",
    "problem_list.parquet", "referrals.parquet", "source-datapackage.json",
    "manifest.json",
}


def _expected_schema(resource: object) -> pa.Schema:
    return pa.schema([
        pa.field(field.name, {"string": pa.string(), "integer": pa.int64(), "number": pa.float64()}[field.frictionless_type])
        for field in resource.fields
    ])


def test_export_parquet_bundle_writes_all_typed_resources(tmp_path: Path) -> None:
    """Catches an exporter that omits resources or lets Parquet infer CSV types."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    output = tmp_path / "parquet"

    result = export_parquet_bundle(ExportConfig(fixture.descriptor, fixture.data_root, output))

    package = load_package_contract(fixture.descriptor)
    assert result == output
    assert {path.name for path in output.iterdir()} == EXPECTED_FILES
    assert (output / "source-datapackage.json").read_bytes() == fixture.descriptor.read_bytes()
    for resource in package.resources:
        parquet = pq.ParquetFile(output / f"{resource.name}.parquet")
        assert parquet.schema_arrow == _expected_schema(resource)
        assert parquet.metadata is not None
        assert parquet.metadata.num_rows == resource.row_count
        for row_group in range(parquet.metadata.num_row_groups):
            for column in range(parquet.metadata.row_group(row_group).num_columns):
                assert parquet.metadata.row_group(row_group).column(column).compression == "ZSTD"
    visits = pq.read_table(output / "visits.parquet")
    assert visits.schema.names[:3] == ["patient_id", "visit_id", "age_in_days"]
    assert visits.schema.field("age_in_days").type == pa.int64()
    assert visits.column("age_in_days").to_pylist() == [100, 200]
    assert stat.S_IMODE((output / "visits.parquet").stat().st_mode) == 0o600


def test_export_parquet_bundle_preserves_nulls_latin_1_and_manifest_hashes(tmp_path: Path) -> None:
    """Catches a bundle that changes nulls/ISO-8859-1 values or misbinds its inventory."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    replace_csv_cell(fixture, "visits", "weight_oz", "")
    replace_labs_cell_bytes(fixture, "result_value", b"caf\xe9\x81")
    output = export_parquet_bundle(ExportConfig(fixture.descriptor, fixture.data_root, tmp_path / "parquet"))

    assert pq.read_table(output / "visits.parquet").column("weight_oz").to_pylist()[0] is None
    assert pq.read_table(output / "labs.parquet").column("result_value").to_pylist() == ["caf\u00e9\u0081"]
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PASS"
    assert manifest["descriptor"] == {
        "basename": "datapackage.json",
        "size": fixture.descriptor.stat().st_size,
        "sha256": sha256_file(fixture.descriptor),
    }
    for item in manifest["outputs"]:
        path = output / item["basename"]
        assert item["size"] == path.stat().st_size
        assert item["sha256"] == sha256_file(path)


def test_verify_parquet_bundle_rejects_reordered_manifest_outputs(tmp_path: Path) -> None:
    """Catches a manifest verifier that ignores descriptor output order."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    output = export_parquet_bundle(
        ExportConfig(fixture.descriptor, fixture.data_root, tmp_path / "parquet")
    )
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["outputs"] = list(reversed(manifest["outputs"]))
    write_manifest(manifest_path, manifest)

    with pytest.raises(LifecycleError):
        verify_parquet_bundle(output, load_package_contract(fixture.descriptor))


@pytest.mark.parametrize(
    ("export_bundle", "bundle_name"),
    ((export_parquet_bundle, "parquet"), (export_duckdb_bundle, "duckdb")),
)
def test_export_bundle_leaves_no_transcoded_source_in_system_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, export_bundle, bundle_name: str
) -> None:
    """Catches a persistent ISO-8859-1 source copy outside the bundle lifecycle."""
    import scripts.typed_export as exporter

    system_temp = tmp_path / "system-temp"
    system_temp.mkdir()
    monkeypatch.setattr(exporter.tempfile, "tempdir", str(system_temp))
    fixture = write_tiny_snapshot(tmp_path / "input")

    export_bundle(
        ExportConfig(fixture.descriptor, fixture.data_root, tmp_path / bundle_name)
    )

    assert list(system_temp.iterdir()) == []


def test_export_parquet_bundle_is_schema_and_row_stable_across_fresh_outputs(tmp_path: Path) -> None:
    """Catches a fresh export whose logical typed contents drift from the same snapshot."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    first = export_parquet_bundle(ExportConfig(fixture.descriptor, fixture.data_root, tmp_path / "first"))
    second = export_parquet_bundle(ExportConfig(fixture.descriptor, fixture.data_root, tmp_path / "second"))

    for name in ("patients", "patients_augmented", "visits", "visits_augmented", "labs", "medications", "problem_list", "referrals"):
        first_table = pq.read_table(first / f"{name}.parquet")
        second_table = pq.read_table(second / f"{name}.parquet")
        assert first_table.schema == second_table.schema
        assert first_table.to_pylist() == second_table.to_pylist()


def test_export_parquet_bundle_rejects_source_change_without_promotion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Catches promotion after a source changes between preflight and manifest creation."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    output = tmp_path / "parquet"
    import scripts.typed_export as exporter

    original = exporter._verify_parquet_with_pyarrow

    def mutate_after_write(*args: object, **kwargs: object) -> None:
        replace_csv_cell(fixture, "visits", "age_in_days", "999")
        original(*args, **kwargs)

    monkeypatch.setattr(exporter, "_verify_parquet_with_pyarrow", mutate_after_write)
    with pytest.raises(ExportError):
        export_parquet_bundle(ExportConfig(fixture.descriptor, fixture.data_root, output))
    assert not output.exists()


def test_export_parquet_bundle_rolls_back_conversion_failure_and_replaces_verified_bundle(tmp_path: Path) -> None:
    """Catches leaked partial output and unsafe collision/replacement behavior."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    output = tmp_path / "parquet"
    replace_csv_cell(fixture, "visits", "age_in_days", "not-an-integer")
    with pytest.raises(ExportError, match="visits.age_in_days failed integer conversion"):
        export_parquet_bundle(ExportConfig(fixture.descriptor, fixture.data_root, output))
    assert not output.exists()

    replace_csv_cell(fixture, "visits", "age_in_days", "100")
    export_parquet_bundle(ExportConfig(fixture.descriptor, fixture.data_root, output))
    with pytest.raises(OutputCollisionError):
        export_parquet_bundle(ExportConfig(fixture.descriptor, fixture.data_root, output))
    result = export_parquet_bundle(ExportConfig(fixture.descriptor, fixture.data_root, output, replace=True))
    assert result == output
    verify_parquet_bundle(output, load_package_contract(fixture.descriptor))


def test_export_parquet_bundle_rejects_validation_failure_without_promotion(tmp_path: Path) -> None:
    """Catches a Parquet bundle promoted despite a typed aggregate-rule violation."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    output = tmp_path / "parquet"
    replace_csv_cell(fixture, "visits", "encounter_type", "unsupported")

    with pytest.raises(ExportError):
        export_parquet_bundle(ExportConfig(fixture.descriptor, fixture.data_root, output))

    assert not output.exists()


def test_export_parquet_bundle_restores_previous_bundle_when_promoted_verification_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches replacement that loses a verified prior bundle when final verification fails."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    output = export_parquet_bundle(ExportConfig(fixture.descriptor, fixture.data_root, tmp_path / "parquet"))
    original_manifest = (output / "manifest.json").read_bytes()
    import scripts.typed_export as exporter

    original_verify = exporter.verify_parquet_bundle

    def reject_promoted(path: Path, package: object) -> None:
        if path == output:
            raise LifecycleError("forced promoted verification failure")
        original_verify(path, package)

    monkeypatch.setattr(exporter, "verify_parquet_bundle", reject_promoted)
    with pytest.raises(ExportError):
        export_parquet_bundle(ExportConfig(fixture.descriptor, fixture.data_root, output, replace=True))

    assert (output / "manifest.json").read_bytes() == original_manifest
    original_verify(output, load_package_contract(fixture.descriptor))

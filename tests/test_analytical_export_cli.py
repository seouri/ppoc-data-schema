from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pyarrow.parquet as pq
import pytest

from scripts.typed_export import (
    DEFAULT_DESCRIPTOR,
    load_package_contract,
    parse_args,
    quote_literal,
    sha256_file,
    validate_artifact,
    verify_duckdb_bundle,
    verify_parquet_bundle,
)
from tests.analytical_export_fixtures import replace_csv_cell, write_tiny_snapshot

ROOT = Path(__file__).resolve().parents[1]
RESOURCE_NAMES = (
    "patients", "patients_augmented", "visits", "visits_augmented", "labs",
    "medications", "problem_list", "referrals",
)


def _run_cli(
    script: str, fixture: object, output: Path, *extra: str, data_root: Path | None = None,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable, str(ROOT / "scripts" / script), "--descriptor",
        str(fixture.descriptor), "--output", str(output), *extra,
    ]
    if data_root is not None:
        command.extend(["--data-root", str(data_root)])
    return subprocess.run(
        command,
        cwd=ROOT,
        env={**os.environ, "PPOC_DATA_ROOT": "", **(environment or {})},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("script", ["export_parquet.py", "build_duckdb.py"])
def test_cli_help_is_available(script: str) -> None:
    """Catches a wrapper that cannot expose the shared operator interface."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), "--help"],
        cwd=ROOT,
        env={**os.environ, "PPOC_DATA_ROOT": ""},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--descriptor" in result.stdout
    assert "--data-root" in result.stdout
    assert "--output" in result.stdout
    assert "--replace" in result.stdout
    assert result.stderr == ""


def test_parse_args_uses_repository_descriptor_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Catches a default that silently changes the checked-in descriptor contract."""
    monkeypatch.setenv("PPOC_DATA_ROOT", str(tmp_path / "csv"))

    config = parse_args("parquet", ["--output", str(tmp_path / "output")])

    assert config.descriptor == DEFAULT_DESCRIPTOR
    assert config.data_root == tmp_path / "csv"
    assert config.output == tmp_path / "output"
    assert not config.replace


def test_parse_args_rejects_unknown_artifact_before_parsing() -> None:
    """Catches an internal dispatch typo selecting the wrong exporter behavior."""
    with pytest.raises(ValueError, match="unsupported CLI artifact type"):
        parse_args("other", [])


def test_parquet_cli_uses_explicit_paths(tmp_path: Path) -> None:
    """Catches a Parquet command that fails to dispatch a verified bundle export."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    output = tmp_path / "parquet"
    result = _run_cli("export_parquet.py", fixture, output, data_root=fixture.data_root)

    assert result.returncode == 0, result.stderr
    assert f"artifact=parquet-bundle output={output}" in result.stdout
    assert "resources=8" in result.stdout
    assert "rows=12" in result.stdout
    assert "status=PASS" in result.stdout
    assert result.stderr == ""


def test_duckdb_cli_uses_environment_data_root(tmp_path: Path) -> None:
    """Catches a DuckDB command that ignores the documented environment fallback."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    output = tmp_path / "duckdb"
    result = _run_cli(
        "build_duckdb.py", fixture, output, environment={"PPOC_DATA_ROOT": str(fixture.data_root)}
    )

    assert result.returncode == 0, result.stderr
    assert f"artifact=duckdb-bundle output={output}" in result.stdout
    assert "resources=8" in result.stdout
    assert "rows=12" in result.stdout
    assert "status=PASS" in result.stdout
    assert result.stderr == ""


def test_explicit_data_root_overrides_environment(tmp_path: Path) -> None:
    """Catches explicit operator input losing precedence to PPOC_DATA_ROOT."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    result = _run_cli(
        "export_parquet.py", fixture, tmp_path / "parquet", data_root=fixture.data_root,
        environment={"PPOC_DATA_ROOT": str(tmp_path / "missing")},
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


@pytest.mark.parametrize("script", ["export_parquet.py", "build_duckdb.py"])
def test_cli_requires_data_root_and_output(script: str, tmp_path: Path) -> None:
    """Catches commands accepting an ambiguous source root or destination."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    missing_root = _run_cli(script, fixture, tmp_path / "output")
    missing_output = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), "--descriptor", str(fixture.descriptor),
         "--data-root", str(fixture.data_root)],
        cwd=ROOT,
        env={**os.environ, "PPOC_DATA_ROOT": ""}, capture_output=True, text=True, check=False,
    )

    assert missing_root.returncode == 2
    assert "--data-root is required when PPOC_DATA_ROOT is unset" in missing_root.stderr
    assert missing_output.returncode == 2
    assert "--output" in missing_output.stderr


def test_cli_rejects_output_inside_repository_without_path_leakage(tmp_path: Path) -> None:
    """Catches a command that permits restricted derived artifacts in the checkout."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    result = _run_cli("export_parquet.py", fixture, ROOT / "forbidden", data_root=fixture.data_root)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "output path is unsafe\n"
    assert str(ROOT) not in result.stderr


def test_cli_requires_replace_for_collision_and_can_replace(tmp_path: Path) -> None:
    """Catches accidental overwrite or a nonfunctional explicit replacement path."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    output = tmp_path / "parquet"
    first = _run_cli("export_parquet.py", fixture, output, data_root=fixture.data_root)
    collision = _run_cli("export_parquet.py", fixture, output, data_root=fixture.data_root)
    replacement = _run_cli("export_parquet.py", fixture, output, "--replace", data_root=fixture.data_root)

    assert first.returncode == 0, first.stderr
    assert collision.returncode == 1
    assert collision.stderr == "output already exists; rerun with --replace\n"
    assert replacement.returncode == 0, replacement.stderr


def test_cli_error_redacts_source_path_and_value(tmp_path: Path) -> None:
    """Catches a conversion error that exposes restricted input location or cell content."""
    fixture = write_tiny_snapshot(tmp_path / "private-secret-input")
    replace_csv_cell(fixture, "visits", "age_in_days", "SECRET-VALUE")
    result = _run_cli("export_parquet.py", fixture, tmp_path / "out", data_root=fixture.data_root)

    assert result.returncode == 1
    assert "visits.age_in_days failed integer conversion" in result.stderr
    assert "private-secret-input" not in result.stderr
    assert "SECRET-VALUE" not in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_argument_errors_do_not_traceback_or_export(tmp_path: Path) -> None:
    """Catches malformed invocations escaping argparse's status-two boundary."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    result = _run_cli("build_duckdb.py", fixture, tmp_path / "out", "--unknown", data_root=fixture.data_root)

    assert result.returncode == 2
    assert "unrecognized arguments: --unknown" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "out").exists()


def _parquet_shape(bundle: Path) -> dict[str, tuple[object, int, list[dict[str, object]]]]:
    return {
        name: (pq.read_table(bundle / f"{name}.parquet").schema,
               pq.read_table(bundle / f"{name}.parquet").num_rows,
               pq.read_table(bundle / f"{name}.parquet").to_pylist())
        for name in RESOURCE_NAMES
    }


def _duckdb_shape(bundle: Path) -> dict[str, tuple[list[tuple[str, str]], int, list[tuple[object, ...]]]]:
    with duckdb.connect(str(bundle / "ppoc.duckdb"), read_only=True) as connection:
        return {
            name: (
                [(item[0], item[1]) for item in connection.execute(f'DESCRIBE main."{name}"').fetchall()],
                connection.execute(f'SELECT count(*) FROM main."{name}"').fetchone()[0],
                connection.execute(f'SELECT * FROM main."{name}"').fetchall(),
            )
            for name in RESOURCE_NAMES
        }


def _validation_shape(bundle: Path, script: str, package: object) -> tuple[object, ...]:
    if script == "export_parquet.py":
        connection = duckdb.connect()
        relation_for = lambda resource: (
            f"read_parquet({quote_literal(str(bundle / (resource.name + '.parquet')))})"
        )
    else:
        connection = duckdb.connect(str(bundle / "ppoc.duckdb"), read_only=True)
        relation_for = lambda resource: f'main."{resource.name}"'
    try:
        return validate_artifact(connection, package, relation_for)
    finally:
        connection.close()


def _duckdb_constraint_shape(bundle: Path) -> list[tuple[str, str, str, str]]:
    with duckdb.connect(str(bundle / "ppoc.duckdb"), read_only=True) as connection:
        return connection.execute(
            "SELECT schema_name, table_name, constraint_type, constraint_text "
            "FROM duckdb_constraints() WHERE schema_name IN ('main', 'ppoc_meta') "
            "ORDER BY schema_name, table_name, constraint_type, constraint_text"
        ).fetchall()


def test_two_destination_cli_smoke(tmp_path: Path) -> None:
    """Catches CLI output that changes typed logical artifacts across fresh destinations."""
    fixture = write_tiny_snapshot(tmp_path / "input")
    destinations = {
        "export_parquet.py": (tmp_path / "parquet-a", tmp_path / "parquet-b"),
        "build_duckdb.py": (tmp_path / "duckdb-a", tmp_path / "duckdb-b"),
    }
    package = load_package_contract(fixture.descriptor)
    for script, (first, second) in destinations.items():
        results = [_run_cli(script, fixture, output, data_root=fixture.data_root) for output in (first, second)]
        assert all(result.returncode == 0 for result in results), [result.stderr for result in results]
        manifests = [json.loads((output / "manifest.json").read_text(encoding="utf-8")) for output in (first, second)]
        for output, manifest in zip((first, second), manifests, strict=True):
            if script == "export_parquet.py":
                verify_parquet_bundle(output, package)
            else:
                verify_duckdb_bundle(output, package)
            assert all(
                item["size"] == (output / item["basename"]).stat().st_size
                and item["sha256"] == sha256_file(output / item["basename"])
                for item in manifest["outputs"]
            )
        assert manifests[0]["status"] == manifests[1]["status"] == "PASS"
        assert manifests[0]["validation"] == manifests[1]["validation"]
        assert manifests[0]["sources"] == manifests[1]["sources"]
        validations = [_validation_shape(output, script, package) for output in (first, second)]
        assert validations[0] == validations[1]
        assert all(record.status == "PASS" for record in validations[0])
        relationship_records = tuple(
            record
            for record in validations[0]
            if record.rule in {
                "foreign key count",
                "logical null count",
                "logical orphan count",
            }
        )
        assert relationship_records
        if script == "export_parquet.py":
            assert _parquet_shape(first) == _parquet_shape(second)
        else:
            assert _duckdb_shape(first) == _duckdb_shape(second)
            assert _duckdb_constraint_shape(first) == _duckdb_constraint_shape(second)
        assert all(item["sha256"] == sha256_file(fixture.data_root / item["basename"]) for item in manifests[0]["sources"])

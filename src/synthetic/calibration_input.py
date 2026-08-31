"""Governed snapshot loading and aggregate-only calibration input preparation."""

from __future__ import annotations

import csv
import hashlib
import hmac
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

import duckdb

from synthetic.schema_contract import (
    field_names,
    load_descriptor,
    resource_spec,
    schema_fingerprint,
)

if TYPE_CHECKING:
    from synthetic.calibrate import CalibrationRunConfig, PartitionPolicy

PartitionLabel = Literal["calibration", "held_out"]
_PARTITIONS = ("calibration", "held_out")
_RESOURCE_NAMES = (
    "patients",
    "patients_augmented",
    "visits",
    "visits_augmented",
    "labs",
    "medications",
    "problem_list",
    "referrals",
)
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_DUCKDB_ENCODINGS = {
    "utf-8": "utf-8",
    "iso-8859-1": "latin-1",
}


@dataclass(frozen=True)
class _OpenedSource:
    name: str
    fd: int


def _freeze_counts(value: Mapping[str, Mapping[str, int]]) -> Mapping[str, Mapping[str, int]]:
    return MappingProxyType({key: MappingProxyType(dict(item)) for key, item in value.items()})


@dataclass(frozen=True)
class PartitionSummary:
    """Aggregate-only partition counts, with no source identifiers or paths."""

    patient_counts: Mapping[str, int]
    resource_row_counts: Mapping[str, Mapping[str, int]]

    def __post_init__(self) -> None:
        if set(self.patient_counts) != set(_PARTITIONS):
            raise ValueError("partition summary must contain both partitions")
        if any(not isinstance(value, int) or value < 0 for value in self.patient_counts.values()):
            raise ValueError("partition summary counts must be nonnegative integers")
        if set(self.resource_row_counts) != set(_RESOURCE_NAMES):
            raise ValueError("partition summary must contain required resources")
        for counts in self.resource_row_counts.values():
            if set(counts) != set(_PARTITIONS) or any(
                not isinstance(value, int) or value < 0 for value in counts.values()
            ):
                raise ValueError("partition summary resource counts must be aggregate-only")
        object.__setattr__(self, "patient_counts", MappingProxyType(dict(self.patient_counts)))
        object.__setattr__(self, "resource_row_counts", _freeze_counts(self.resource_row_counts))

    def to_mapping(self) -> dict[str, object]:
        return {
            "patient_counts": dict(self.patient_counts),
            "resource_row_counts": {name: dict(counts) for name, counts in self.resource_row_counts.items()},
        }


@dataclass(frozen=True)
class CalibrationInput:
    """Public calibration input metadata; relations remain connection-local."""

    descriptor: Mapping[str, Any]
    schema_fingerprint: str
    partition_summary: PartitionSummary
    resource_names: tuple[str, ...]

    def __post_init__(self) -> None:
        if set(self.resource_names) != set(_RESOURCE_NAMES):
            raise ValueError("calibration input must name required resources")
        object.__setattr__(self, "descriptor", MappingProxyType(dict(self.descriptor)))

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema_fingerprint": self.schema_fingerprint,
            "partition_summary": self.partition_summary.to_mapping(),
            "resource_names": list(self.resource_names),
        }


def assign_partition(patient_id: str, policy: PartitionPolicy, key: bytes) -> PartitionLabel:
    """Deterministically assign a patient using a keyed digest without disclosing it."""
    if not isinstance(patient_id, str) or not patient_id:
        raise ValueError("patients.patient_id must be nonempty")
    if not isinstance(key, bytes) or len(key) < 16:
        raise ValueError("partition_key must contain at least 16 bytes")
    digest = hmac.new(key, patient_id.encode("utf-8"), hashlib.sha256).digest()
    basis_point = int.from_bytes(digest, byteorder="big") % 10_000
    return "calibration" if basis_point < policy.calibration_basis_points else "held_out"


def _repository_fingerprint() -> str:
    return schema_fingerprint(load_descriptor(_REPOSITORY_ROOT / "datapackage.json"))


def _validate_descriptor(config: CalibrationRunConfig) -> dict[str, Any]:
    try:
        descriptor = load_descriptor(config.source_descriptor)
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError("descriptor is invalid") from exc
    names = [resource.get("name") for resource in descriptor["resources"]]
    if set(names) != set(_RESOURCE_NAMES) or len(names) != len(_RESOURCE_NAMES):
        raise ValueError("descriptor must declare required resources")
    if schema_fingerprint(descriptor) != _repository_fingerprint():
        raise ValueError("descriptor schema fingerprint does not match repository")
    return descriptor


def _open_validated_source(data_root: Path, resource: Mapping[str, Any]) -> _OpenedSource:
    name = resource.get("name")
    raw_path = resource.get("path")
    if not isinstance(name, str) or not isinstance(raw_path, str) or not raw_path:
        raise ValueError("resource descriptor is invalid")
    if os.path.isabs(raw_path) or ".." in Path(raw_path).parts:
        raise ValueError(f"{name} resource path is invalid")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        directory_fd = os.open(data_root, directory_flags)
    except OSError as exc:
        raise ValueError(f"{name} resource is unavailable") from exc
    try:
        parts = Path(raw_path).parts
        for component in parts[:-1]:
            next_directory_fd = os.open(component, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_directory_fd
        entry = os.stat(parts[-1], dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(entry.st_mode):
            raise ValueError(f"{name} resource is unavailable")
        source_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    except (OSError, ValueError) as exc:
        raise ValueError(f"{name} resource is unavailable") from exc
    finally:
        os.close(directory_fd)
    try:
        if not stat.S_ISREG(os.fstat(source_fd).st_mode):
            raise ValueError(f"{name} resource is unavailable")
    except (OSError, ValueError) as exc:
        os.close(source_fd)
        raise ValueError(f"{name} resource is unavailable") from exc
    return _OpenedSource(name, source_fd)


def _validate_csv_header(source: _OpenedSource, descriptor: dict[str, Any]) -> None:
    name = source.name
    resource = resource_spec(descriptor, name)
    dialect = resource.get("dialect", {})
    try:
        with os.fdopen(os.dup(source.fd), "r", encoding=resource.get("encoding", "utf-8"), newline="") as handle:
            reader = csv.reader(
                handle,
                delimiter=dialect.get("delimiter", ","),
                quotechar=dialect.get("quoteChar", '"'),
                doublequote=dialect.get("doubleQuote", True),
                strict=True,
            )
            header = next(reader, None)
            # Force strict parsing of the whole stream before DuckDB sees it.
            for _ in reader:
                pass
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ValueError(f"{name} resource cannot be read") from exc
    if header != list(field_names(descriptor, name)):
        raise ValueError(f"{name} resource header does not match descriptor")
    os.lseek(source.fd, 0, os.SEEK_SET)


def _stage_relation(
    connection: duckdb.DuckDBPyConnection, source: _OpenedSource, resource: Mapping[str, Any]
) -> str:
    name = source.name
    relation = f"calibration_stage_{name}"
    dialect = resource.get("dialect", {})
    quote = dialect.get("quoteChar", '"')
    if not isinstance(quote, str) or len(quote) != 1:
        raise ValueError(f"{name} resource dialect is invalid")
    declared_encoding = resource.get("encoding", "utf-8")
    if not isinstance(declared_encoding, str) or declared_encoding not in _DUCKDB_ENCODINGS:
        raise ValueError(f"{name} resource encoding is unsupported")
    duckdb_encoding = _DUCKDB_ENCODINGS[declared_encoding]
    try:
        connection.execute(
            f'CREATE OR REPLACE TEMP TABLE "{relation}" AS '
            "SELECT * FROM read_csv(?, header = true, all_varchar = true, delim = ?, quote = ?, "
            "escape = ?, nullstr = ?, encoding = ?, strict_mode = true)",
            [
                f"/dev/fd/{source.fd}",
                dialect.get("delimiter", ","),
                quote,
                quote,
                "\0",
                duckdb_encoding,
            ],
        )
    except duckdb.Error as exc:
        raise ValueError(f"{name} resource cannot be staged") from exc
    return relation


def _has_rows(
    connection: duckdb.DuckDBPyConnection,
    query: str,
    parameters: tuple[object, ...] = (),
) -> bool:
    return connection.execute(query, parameters).fetchone()[0] > 0


def _validate_relation(
    connection: duckdb.DuckDBPyConnection, name: str, descriptor: dict[str, Any], relation: str
) -> None:
    resource = resource_spec(descriptor, name)
    fields = resource["schema"]["fields"]
    primary_key = resource["schema"].get("primaryKey")
    if _has_rows(connection, f'SELECT count(*) FROM "{relation}" WHERE patient_id IS NULL OR patient_id = \'\''):
        raise ValueError(f"{name}.patient_id must be nonempty")
    if primary_key:
        primary_fields = (primary_key,) if isinstance(primary_key, str) else tuple(primary_key)
        if not primary_fields or not all(isinstance(field, str) for field in primary_fields):
            raise ValueError(f"{name} primary key is invalid")
        for field_name in primary_fields:
            if _has_rows(
                connection,
                f'SELECT count(*) FROM "{relation}" '
                f'WHERE "{field_name}" IS NULL OR "{field_name}" = \'\'',
            ):
                raise ValueError(f"{name}.{field_name} must be nonempty")
        selected_fields = ", ".join(f'"{field_name}"' for field_name in primary_fields)
        if _has_rows(
            connection,
            f'SELECT count(*) FROM (SELECT {selected_fields} FROM "{relation}" '
            f'GROUP BY {selected_fields} HAVING count(*) > 1)',
        ):
            raise ValueError(f"{name} primary key must be unique")
    for field in fields:
        constraints = field.get("constraints") or {}
        field_name = field.get("name")
        field_type = field.get("type")
        if not isinstance(field_name, str) or not isinstance(constraints, Mapping):
            continue
        quoted = f'"{field_name}"'
        present = f"coalesce({quoted}, '') <> ''"
        if constraints.get("required") and _has_rows(
            connection,
            f'SELECT count(*) FROM "{relation}" WHERE {quoted} IS NULL OR {quoted} = \'\'',
        ):
            raise ValueError(f"{name}.{field_name} must be nonempty")
        cast_type: str | None = None
        if field_type == "integer":
            cast_type = "BIGINT"
            if _has_rows(
                connection,
                f'SELECT count(*) FROM "{relation}" WHERE {present} AND '
                f'(NOT regexp_full_match({quoted}, \'[+-]?[0-9]+\') '
                f'OR try_cast({quoted} AS BIGINT) IS NULL)',
            ):
                raise ValueError(f"{name}.{field_name} must be a valid integer")
        elif field_type == "number":
            cast_type = "DOUBLE"
            if _has_rows(
                connection,
                f'SELECT count(*) FROM "{relation}" WHERE {present} AND '
                f'(try_cast({quoted} AS DOUBLE) IS NULL '
                f'OR NOT isfinite(try_cast({quoted} AS DOUBLE)))',
            ):
                raise ValueError(f"{name}.{field_name} must be a valid finite number")
        if "enum" in constraints:
            enum_values = tuple(str(value) for value in constraints["enum"])
            placeholders = ", ".join("?" for _ in enum_values)
            if not enum_values or _has_rows(
                connection,
                f'SELECT count(*) FROM "{relation}" WHERE {present} '
                f"AND {quoted} NOT IN ({placeholders})",
                enum_values,
            ):
                raise ValueError(f"{name}.{field_name} must satisfy enum")
        for constraint_name, operator in (("minimum", "<"), ("maximum", ">")):
            if constraint_name not in constraints or cast_type is None:
                continue
            if _has_rows(
                connection,
                f'SELECT count(*) FROM "{relation}" WHERE {present} '
                f'AND try_cast({quoted} AS {cast_type}) {operator} ?',
                (constraints[constraint_name],),
            ):
                raise ValueError(f"{name}.{field_name} must satisfy {constraint_name}")


def _partition_counts(connection: duckdb.DuckDBPyConnection, relation: str) -> dict[str, int]:
    rows = connection.execute(
        f'SELECT partition_label, count(*) FROM "{relation}" GROUP BY partition_label'
    ).fetchall()
    counts = {label: 0 for label in _PARTITIONS}
    counts.update({label: count for label, count in rows})
    return counts


def prepare_input(connection: duckdb.DuckDBPyConnection, config: CalibrationRunConfig) -> CalibrationInput:
    """Validate and stage a governed snapshot, returning aggregate metadata only."""
    if not isinstance(connection, duckdb.DuckDBPyConnection):
        raise TypeError("connection must be a DuckDB connection")
    descriptor = _validate_descriptor(config)
    staged: dict[str, str] = {}
    for name in _RESOURCE_NAMES:
        resource = resource_spec(descriptor, name)
        source = _open_validated_source(config.data_root, resource)
        try:
            _validate_csv_header(source, descriptor)
            staged[name] = _stage_relation(connection, source, resource)
            _validate_relation(connection, name, descriptor, staged[name])
        finally:
            os.close(source.fd)

    patient_rows = connection.execute('SELECT patient_id FROM "calibration_stage_patients"').fetchall()
    partitions = [(patient_id, assign_partition(patient_id, config.partition_policy, config.partition_key)) for patient_id, in patient_rows]
    connection.execute("CREATE OR REPLACE TEMP TABLE patient_partitions(patient_id VARCHAR, partition_label VARCHAR)")
    connection.executemany("INSERT INTO patient_partitions VALUES (?, ?)", partitions)
    patient_counts = _partition_counts(connection, "patient_partitions")
    if any(count < config.partition_policy.minimum_partition_patients for count in patient_counts.values()):
        raise ValueError("partition policy minimum_partition_patients is not met")

    resource_counts: dict[str, dict[str, int]] = {}
    for name, relation in staged.items():
        if _has_rows(
            connection,
            f'SELECT count(*) FROM "{relation}" AS resource LEFT JOIN patient_partitions AS partitions '
            "ON resource.patient_id = partitions.patient_id WHERE partitions.patient_id IS NULL",
        ):
            raise ValueError(f"{name}.patient_id must join patients")
        rows = connection.execute(
            f'SELECT partitions.partition_label, count(*) FROM "{relation}" AS resource '
            "JOIN patient_partitions AS partitions ON resource.patient_id = partitions.patient_id "
            "GROUP BY partitions.partition_label"
        ).fetchall()
        counts = {label: 0 for label in _PARTITIONS}
        counts.update({label: count for label, count in rows})
        resource_counts[name] = counts
    return CalibrationInput(
        descriptor=descriptor,
        schema_fingerprint=schema_fingerprint(descriptor),
        partition_summary=PartitionSummary(patient_counts, resource_counts),
        resource_names=_RESOURCE_NAMES,
    )

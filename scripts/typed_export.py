from __future__ import annotations

import json
import stat
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DESCRIPTOR = ROOT / "datapackage.json"
EXPECTED_RESOURCE_NAMES = (
    "patients",
    "patients_augmented",
    "visits",
    "visits_augmented",
    "labs",
    "medications",
    "problem_list",
    "referrals",
)
TYPE_MAP = {"string": "VARCHAR", "integer": "BIGINT", "number": "DOUBLE"}
SUPPORTED_CONSTRAINTS = frozenset({"required", "enum", "minimum", "maximum"})
ENCODING_MAP = {"utf-8": "utf-8", "iso-8859-1": "latin-1"}


class ExportError(RuntimeError):
    """A redacted analytical-export failure safe for CLI display."""


class DescriptorError(ExportError):
    pass


@dataclass(frozen=True)
class ExportConfig:
    descriptor: Path
    data_root: Path
    output: Path
    replace: bool = False


@dataclass(frozen=True)
class FieldContract:
    name: str
    frictionless_type: str
    duckdb_type: str
    required: bool
    enum: tuple[str | int | float, ...] | None
    minimum: int | float | None
    maximum: int | float | None


@dataclass(frozen=True)
class RelationshipContract:
    field: str
    reference_resource: str
    reference_field: str
    orphan_rows: int | None = None
    null_rows: int | None = None


@dataclass(frozen=True)
class ResourceContract:
    name: str
    csv_path: str
    encoding: str
    delimiter: str
    quote_char: str
    double_quote: bool
    missing_values: tuple[str, ...]
    row_count: int
    fields: tuple[FieldContract, ...]
    primary_key: str | None
    foreign_keys: tuple[RelationshipContract, ...]
    logical_foreign_keys: tuple[RelationshipContract, ...]


@dataclass(frozen=True)
class PackageContract:
    name: str
    version: str
    snapshot: str
    descriptor_path: Path
    descriptor_bytes: bytes
    descriptor_sha256: str
    descriptor: dict[str, Any]
    resources: tuple[ResourceContract, ...]


def load_package_contract(path: Path) -> PackageContract:
    """Load and validate the checked-in analytical-export descriptor contract."""
    descriptor_path = Path(path)
    try:
        mode = descriptor_path.lstat().st_mode
    except (OSError, ValueError) as exc:
        raise DescriptorError("descriptor is not a regular descriptor file") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise DescriptorError("descriptor is not a regular descriptor file")
    try:
        descriptor_bytes = descriptor_path.read_bytes()
        descriptor = json.loads(descriptor_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DescriptorError("descriptor is not valid UTF-8 JSON") from exc
    if not isinstance(descriptor, dict):
        raise DescriptorError("descriptor object is invalid")

    name = _scalar_string(descriptor, "name", "descriptor name")
    version = _scalar_string(descriptor, "version", "descriptor version")
    statistics = _object(descriptor, "x-statisticsSource", "statistics source")
    snapshot = _scalar_string(statistics, "snapshot", "descriptor snapshot")
    resources = _resources(descriptor)
    descriptor_copy = json.loads(json.dumps(descriptor))
    return PackageContract(
        name=name,
        version=version,
        snapshot=snapshot,
        descriptor_path=descriptor_path,
        descriptor_bytes=descriptor_bytes,
        descriptor_sha256=sha256(descriptor_bytes).hexdigest(),
        descriptor=descriptor_copy,
        resources=resources,
    )


def _resources(descriptor: dict[str, Any]) -> tuple[ResourceContract, ...]:
    raw_resources = descriptor.get("resources")
    if not isinstance(raw_resources, list) or len(raw_resources) != len(EXPECTED_RESOURCE_NAMES):
        raise DescriptorError("descriptor must contain exactly eight resources")
    names = tuple(_scalar_string(resource, "name", "resource name") for resource in raw_resources if isinstance(resource, dict))
    if names != EXPECTED_RESOURCE_NAMES:
        if len(set(names)) != len(names):
            raise DescriptorError("descriptor has duplicate resource name")
        raise DescriptorError("descriptor resource order is not supported")
    if len(set(names)) != len(names):
        raise DescriptorError("descriptor has duplicate resource name")
    resource_names = set(EXPECTED_RESOURCE_NAMES)
    contracts = tuple(_resource(resource, resource_names) for resource in raw_resources)
    field_names = {
        resource["name"]: {field["name"] for field in resource["schema"]["fields"]}
        for resource in raw_resources
    }
    for resource in contracts:
        for relationship in (*resource.foreign_keys, *resource.logical_foreign_keys):
            if relationship.reference_field not in field_names[relationship.reference_resource]:
                raise DescriptorError("relationship reference is invalid")
    return contracts


def _resource(resource: dict[str, Any], resource_names: set[str]) -> ResourceContract:
    path = _scalar_string(resource, "path", "resource path")
    path_parts = PurePosixPath(path).parts
    if ".." in path_parts or PurePosixPath(path).is_absolute():
        raise DescriptorError("unsafe resource path")
    if len(path_parts) > 1:
        raise DescriptorError("multi-component resource path")
    if (
        not path
        or path_parts[0] != path
        or path_parts[0] in {".", ".."}
        or not path.endswith(".csv")
    ):
        raise DescriptorError("unsafe resource path")
    if resource.get("format") != "csv":
        raise DescriptorError("unsupported resource format")
    encoding = _scalar_string(resource, "encoding", "resource encoding")
    if encoding not in ENCODING_MAP:
        raise DescriptorError("unsupported encoding")
    dialect = _object(resource, "dialect", "resource dialect")
    if dialect.get("header") is not True or dialect.get("delimiter") != "," or dialect.get("quoteChar") != '"' or dialect.get("doubleQuote") is not True:
        raise DescriptorError("unsupported dialect")
    schema = _object(resource, "schema", "resource schema")
    missing_values = schema.get("missingValues", [""])
    if missing_values != [""]:
        raise DescriptorError("unsupported missingValues")
    row_count = _nonnegative_int(resource.get("x-rowCount"), "x-rowCount")
    fields = _fields(schema)
    primary_key = _primary_key(schema, fields)
    foreign_keys = _relationships(schema.get("foreignKeys", []), resource_names, fields, "foreign")
    logical_foreign_keys = _relationships(resource.get("x-logicalForeignKeys", []), resource_names, fields, "logical")
    return ResourceContract(
        name=resource["name"],
        csv_path=path,
        encoding=encoding,
        delimiter=dialect["delimiter"],
        quote_char=dialect["quoteChar"],
        double_quote=dialect["doubleQuote"],
        missing_values=("",),
        row_count=row_count,
        fields=fields,
        primary_key=primary_key,
        foreign_keys=foreign_keys,
        logical_foreign_keys=logical_foreign_keys,
    )


def _fields(schema: dict[str, Any]) -> tuple[FieldContract, ...]:
    raw_fields = schema.get("fields")
    if not isinstance(raw_fields, list) or not raw_fields:
        raise DescriptorError("resource schema fields are invalid")
    result: list[FieldContract] = []
    names: set[str] = set()
    for raw_field in raw_fields:
        if not isinstance(raw_field, dict):
            raise DescriptorError("resource field is invalid")
        name = _scalar_string(raw_field, "name", "field name")
        if name in names:
            raise DescriptorError("descriptor has duplicate field name")
        names.add(name)
        frictionless_type = _scalar_string(raw_field, "type", "field type")
        if frictionless_type not in TYPE_MAP:
            raise DescriptorError("descriptor has unsupported field type")
        constraints = raw_field.get("constraints", {})
        if not isinstance(constraints, dict):
            raise DescriptorError("field constraints are invalid")
        if set(constraints) - SUPPORTED_CONSTRAINTS:
            raise DescriptorError("descriptor has unsupported constraint")
        required = constraints.get("required", False)
        if not isinstance(required, bool):
            raise DescriptorError("field required constraint is invalid")
        enum = _enum(constraints.get("enum"))
        minimum = _number(constraints.get("minimum"), "field minimum")
        maximum = _number(constraints.get("maximum"), "field maximum")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise DescriptorError("field constraint range is invalid")
        result.append(FieldContract(name, frictionless_type, TYPE_MAP[frictionless_type], required, enum, minimum, maximum))
    return tuple(result)


def _relationships(
    raw_relationships: Any,
    resource_names: set[str],
    fields: tuple[FieldContract, ...],
    kind: str,
) -> tuple[RelationshipContract, ...]:
    if not isinstance(raw_relationships, list):
        raise DescriptorError(f"{kind} relationships are invalid")
    field_names = {field.name for field in fields}
    result = []
    for relationship in raw_relationships:
        if not isinstance(relationship, dict):
            raise DescriptorError(f"{kind} relationship is invalid")
        field = relationship.get("fields")
        reference = relationship.get("reference")
        if not isinstance(field, str) or not field or not isinstance(reference, dict):
            raise DescriptorError("relationship keys must be scalar")
        reference_resource = reference.get("resource")
        reference_field = reference.get("fields")
        if not isinstance(reference_resource, str) or not isinstance(reference_field, str):
            raise DescriptorError("relationship keys must be scalar")
        if field not in field_names or reference_resource not in resource_names or not reference_field:
            raise DescriptorError("relationship reference is invalid")
        orphan_rows = _optional_nonnegative_int(relationship.get("orphanRows"), "logical relationship count")
        null_rows = _optional_nonnegative_int(relationship.get("nullRows"), "logical relationship count")
        result.append(RelationshipContract(field, reference_resource, reference_field, orphan_rows, null_rows))
    return tuple(result)


def _primary_key(schema: dict[str, Any], fields: tuple[FieldContract, ...]) -> str | None:
    value = schema.get("primaryKey")
    if value is None:
        return None
    if not isinstance(value, str) or not value or value not in {field.name for field in fields}:
        raise DescriptorError("scalar primary key is invalid")
    return value


def _enum(value: Any) -> tuple[str | int | float, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not value or any(isinstance(item, (bool, dict, list)) or not isinstance(item, (str, int, float)) for item in value):
        raise DescriptorError("field enum constraint is invalid")
    return tuple(value)


def _number(value: Any, label: str) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DescriptorError(f"{label} is invalid")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DescriptorError(f"{label} is invalid")
    return value


def _optional_nonnegative_int(value: Any, label: str) -> int | None:
    if value is None:
        return None
    return _nonnegative_int(value, label)


def _object(parent: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise DescriptorError(f"{label} is invalid")
    return value


def _scalar_string(parent: dict[str, Any], key: str, label: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value:
        raise DescriptorError(f"{label} must be scalar")
    return value

from __future__ import annotations

import argparse
import atexit
import csv
import json
import math
import os
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

import duckdb

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
_TRANSCODED_SOURCES: list[Path] = []


class ExportError(RuntimeError):
    """A redacted analytical-export failure safe for CLI display."""


class DescriptorError(ExportError):
    pass


class ValidationError(ExportError):
    pass


class UnsafePathError(ExportError):
    pass


class OutputCollisionError(ExportError):
    pass


class LifecycleError(ExportError):
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


@dataclass(frozen=True)
class SourceState:
    resource: ResourceContract
    path: Path
    device: int
    inode: int
    size: int
    mtime_ns: int


@dataclass(frozen=True)
class SourceFingerprint:
    resource_name: str
    basename: str
    size: int
    sha256: str
    row_count: int
    field_count: int


@dataclass(frozen=True)
class OutputFingerprint:
    basename: str
    size: int
    sha256: str
    row_count: int | None = None
    field_count: int | None = None
    columns: tuple[tuple[str, str], ...] = ()
    tables: tuple[tuple[str, int, int], ...] = ()


@dataclass(frozen=True)
class BuildProvenance:
    created_at_utc: str
    python_version: str
    duckdb_version: str
    pyarrow_version: str
    exporter_git_revision: str | None
    exporter_git_dirty: bool | None
    exporter_module_sha256: str


@dataclass(frozen=True)
class ValidationRecord:
    resource: str
    field: str | None
    rule: str
    expected: int | float | str | list[object]
    observed: int | float | str | list[object]
    status: str = "PASS"


_MANIFEST_KEYS = frozenset({
    "manifestVersion", "status", "artifactType", "package", "build", "descriptor",
    "sources", "outputs", "validation",
})
_ARTIFACT_TYPES = frozenset({"parquet-bundle", "duckdb-bundle"})
_BUNDLE_INVENTORIES = {
    "parquet-bundle": frozenset({"manifest.json", "source-datapackage.json", *(f"{name}.parquet" for name in EXPECTED_RESOURCE_NAMES)}),
    "duckdb-bundle": frozenset({"manifest.json", "ppoc.duckdb"}),
}


def sha256_file(path: Path) -> str:
    """Hash a regular file without loading its contents into memory."""
    digest = sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def build_provenance() -> BuildProvenance:
    """Capture attributable exporter provenance without making Git mandatory."""
    revision: str | None = None
    dirty: bool | None = None
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, check=True, capture_output=True,
            text=True,
        ).stdout)
    except (OSError, subprocess.SubprocessError):
        revision = None
        dirty = None
    try:
        import pyarrow
        pyarrow_version = pyarrow.__version__
    except ImportError:
        pyarrow_version = "unavailable"
    return BuildProvenance(
        datetime.now(UTC).isoformat().replace("+00:00", "Z"), sys.version.split()[0],
        duckdb.__version__, pyarrow_version, revision, dirty, sha256_file(Path(__file__)),
    )


def _safe_basename(value: str) -> bool:
    return bool(value) and Path(value).name == value and value not in {".", ".."}


def _valid_digest(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _valid_git_revision(value: object) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(character in "0123456789abcdef" for character in value)


def _manifest_payload_is_safe(payload: Mapping[str, object]) -> bool:
    return set(payload) == _MANIFEST_KEYS and payload.get("manifestVersion") == 1 and payload.get("status") == "PASS" and payload.get("artifactType") in _ARTIFACT_TYPES


def _contains_absolute_path(value: object) -> bool:
    if isinstance(value, str):
        return Path(value).is_absolute() or (len(value) >= 3 and value[0].isalpha() and value[1:3] in {":\\", ":/"}) or value.startswith("\\\\")
    if isinstance(value, Mapping):
        return any(_contains_absolute_path(key) or _contains_absolute_path(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_absolute_path(item) for item in value)
    return False


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _strict_manifest(payload: object, artifact_type: str, expected_names: frozenset[str]) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or _contains_absolute_path(payload) or not _manifest_payload_is_safe(payload) or payload["artifactType"] != artifact_type or expected_names != _BUNDLE_INVENTORIES[artifact_type]:
        return None
    package = payload["package"]
    build = payload["build"]
    descriptor = payload["descriptor"]
    sources = payload["sources"]
    outputs = payload["outputs"]
    validation = payload["validation"]
    if not all(isinstance(item, dict) for item in (package, build, descriptor, validation)) or not isinstance(sources, list) or not isinstance(outputs, list):
        return None
    if set(package) != {"name", "version", "snapshot"} or not all(isinstance(value, str) and value for value in package.values()):
        return None
    if set(build) != {"createdAtUtc", "pythonVersion", "duckdbVersion", "pyarrowVersion", "exporterGitRevision", "exporterGitDirty", "exporterModuleSha256"} or not all(isinstance(build[key], str) and build[key] for key in ("createdAtUtc", "pythonVersion", "duckdbVersion", "pyarrowVersion")) or not (build["exporterGitRevision"] is None or _valid_git_revision(build["exporterGitRevision"])) or not (build["exporterGitDirty"] is None or isinstance(build["exporterGitDirty"], bool)) or not _valid_digest(build["exporterModuleSha256"]):
        return None
    if set(descriptor) != {"basename", "size", "sha256"} or not _safe_basename(descriptor["basename"]) or not _is_int(descriptor["size"]) or descriptor["size"] < 0 or not _valid_digest(descriptor["sha256"]):
        return None
    source_keys = {"resource", "basename", "size", "sha256", "rowCount", "fieldCount"}
    if len(sources) != len(EXPECTED_RESOURCE_NAMES) or tuple(item.get("resource") if isinstance(item, dict) else None for item in sources) != EXPECTED_RESOURCE_NAMES or any(not isinstance(item, dict) or set(item) != source_keys or not isinstance(item["resource"], str) or not _safe_basename(item["basename"]) or not all(_is_int(item[key]) and item[key] >= 0 for key in ("size", "rowCount", "fieldCount")) or not _valid_digest(item["sha256"]) for item in sources):
        return None
    output_keys = {"basename", "size", "sha256", "rowCount", "fieldCount", "columns", "tables"}
    expected_output_order = (
        tuple(f"{name}.parquet" for name in EXPECTED_RESOURCE_NAMES)
        + ("source-datapackage.json",)
        if artifact_type == "parquet-bundle"
        else ("ppoc.duckdb",)
    )
    output_names = tuple(
        item.get("basename") if isinstance(item, dict) else None for item in outputs
    )
    if output_names != expected_output_order or set(output_names) != expected_names - {"manifest.json"} or any(not isinstance(item, dict) or set(item) != output_keys or not _safe_basename(item["basename"]) or not _is_int(item["size"]) or item["size"] < 0 or not _valid_digest(item["sha256"]) or not (item["rowCount"] is None or _is_int(item["rowCount"]) and item["rowCount"] >= 0) or not (item["fieldCount"] is None or _is_int(item["fieldCount"]) and item["fieldCount"] >= 0) or not isinstance(item["columns"], list) or any(not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(value, str) and value for value in pair) for pair in item["columns"]) or not isinstance(item["tables"], list) or any(not isinstance(table, list) or len(table) != 3 or not isinstance(table[0], str) or not table[0] or not all(_is_int(value) and value >= 0 for value in table[1:]) for table in item["tables"]) for item in outputs):
        return None
    if set(validation) != {"status", "checkCount", "failedChecks"} or validation["status"] != "PASS" or not _is_int(validation["checkCount"]) or validation["checkCount"] < 0 or validation["failedChecks"] != 0:
        return None
    return payload


def build_manifest(
    artifact_type: str, package: PackageContract, provenance: BuildProvenance,
    sources: tuple[SourceFingerprint, ...], outputs: tuple[OutputFingerprint, ...],
    validations: tuple[ValidationRecord, ...],
) -> dict[str, object]:
    if artifact_type not in _ARTIFACT_TYPES:
        raise LifecycleError("unsupported bundle artifact type")
    if not _valid_digest(package.descriptor_sha256) or not _valid_digest(provenance.exporter_module_sha256):
        raise LifecycleError("manifest fingerprint is invalid")
    if any(not _safe_basename(item.basename) or not _valid_digest(item.sha256) for item in (*sources, *outputs)):
        raise LifecycleError("manifest fingerprint is invalid")
    if any(item.size < 0 or item.row_count is not None and item.row_count < 0 or item.field_count is not None and item.field_count < 0 for item in outputs):
        raise LifecycleError("manifest fingerprint is invalid")
    failures = sum(record.status != "PASS" for record in validations)
    return {
        "manifestVersion": 1, "status": "PASS" if not failures else "FAIL", "artifactType": artifact_type,
        "package": {"name": package.name, "version": package.version, "snapshot": package.snapshot},
        "build": {"createdAtUtc": provenance.created_at_utc, "pythonVersion": provenance.python_version, "duckdbVersion": provenance.duckdb_version, "pyarrowVersion": provenance.pyarrow_version, "exporterGitRevision": provenance.exporter_git_revision, "exporterGitDirty": provenance.exporter_git_dirty, "exporterModuleSha256": provenance.exporter_module_sha256},
        "descriptor": {"basename": package.descriptor_path.name, "size": len(package.descriptor_bytes), "sha256": package.descriptor_sha256},
        "sources": [{"resource": item.resource_name, "basename": item.basename, "size": item.size, "sha256": item.sha256, "rowCount": item.row_count, "fieldCount": item.field_count} for item in sources],
        "outputs": [{"basename": item.basename, "size": item.size, "sha256": item.sha256, "rowCount": item.row_count, "fieldCount": item.field_count, "columns": [list(pair) for pair in item.columns], "tables": [list(table) for table in item.tables]} for item in outputs],
        "validation": {"status": "PASS" if not failures else "FAIL", "checkCount": len(validations), "failedChecks": failures},
    }


def write_manifest(path: Path, payload: Mapping[str, object]) -> None:
    if not _manifest_payload_is_safe(payload) or _contains_absolute_path(payload):
        raise LifecycleError("manifest contract is invalid")
    destination = Path(path)
    if not _safe_basename(destination.name) or not destination.parent.is_dir():
        raise LifecycleError("manifest destination is invalid")
    encoded = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    temporary = destination.with_name(f".{destination.name}.tmp-{secrets.token_hex(8)}")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
    except OSError as exc:
        raise LifecycleError("manifest write failed") from exc


def verify_bundle_manifest(bundle: Path, artifact_type: str, expected_names: frozenset[str]) -> dict[str, Any]:
    root = Path(bundle)
    try:
        root_mode = root.lstat().st_mode
        manifest_path = root / "manifest.json"
        manifest_mode = manifest_path.lstat().st_mode
        if (
            not stat.S_ISDIR(root_mode)
            or stat.S_ISLNK(root_mode)
            or stat.S_IMODE(root_mode) != 0o700
            or not stat.S_ISREG(manifest_mode)
            or stat.S_ISLNK(manifest_mode)
            or stat.S_IMODE(manifest_mode) != 0o600
        ):
            raise OSError
        actual = {item.name for item in root.iterdir()}
        if actual != set(expected_names) or any(
            stat.S_ISLNK(item.lstat().st_mode)
            or not stat.S_ISREG(item.lstat().st_mode)
            or stat.S_IMODE(item.lstat().st_mode) != 0o600
            for item in root.iterdir()
        ):
            raise OSError
        raw = manifest_path.read_bytes()
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=lambda pairs: _no_duplicate_json_keys(pairs))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LifecycleError("existing bundle is not a verified bundle") from exc
    if raw != (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"):
        raise LifecycleError("existing bundle is not a verified bundle")
    verified = _strict_manifest(payload, artifact_type, expected_names)
    if verified is None:
        raise LifecycleError("existing bundle is not a verified bundle")
    for output in verified["outputs"]:
        path = root / output["basename"]
        if path.stat().st_size != output["size"] or sha256_file(path) != output["sha256"]:
            raise LifecycleError("existing bundle is not a verified bundle")
    return verified


def _no_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _equal_or_below(candidate: Path, boundary: Path) -> bool:
    try:
        candidate.relative_to(boundary)
        return True
    except ValueError:
        return False


def ensure_safe_output(repo_root: Path, package: PackageContract, sources: tuple[SourceState, ...], output: Path) -> Path:
    target = Path(output)
    try:
        if target.exists() or target.is_symlink():
            mode = target.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise UnsafePathError("output path is unsafe")
        parent = target.parent.resolve(strict=True)
        if not parent.is_dir():
            raise UnsafePathError("output parent is unsafe")
        resolved = (parent / target.name).resolve(strict=False)
    except (OSError, ValueError) as exc:
        raise UnsafePathError("output path is unsafe") from exc
    boundaries = [Path(repo_root).resolve(), package.descriptor_path.resolve(), *(state.path.resolve() for state in sources)]
    if any(_equal_or_below(resolved, boundary) or _equal_or_below(boundary, resolved) for boundary in boundaries):
        raise UnsafePathError("output path is unsafe")
    return resolved


@dataclass
class BundleRun:
    output: Path
    artifact_type: str
    replace: bool
    staging: Path
    backup: Path | None = None

    @classmethod
    def start(cls, output: Path, artifact_type: str, replace: bool) -> BundleRun:
        target = Path(output)
        if artifact_type not in _ARTIFACT_TYPES:
            raise LifecycleError("unsupported bundle artifact type")
        try:
            parent = target.parent.resolve(strict=True)
            if not parent.is_dir():
                raise OSError
        except OSError as exc:
            raise UnsafePathError("output parent is unsafe") from exc
        target = parent / target.name
        pattern = f".{target.name}.{artifact_type}."
        if any(item.name.startswith(pattern) and (".partial-" in item.name or ".backup-" in item.name) for item in parent.iterdir()):
            raise LifecycleError(f"recovery required for {target.name}")
        if target.exists() or target.is_symlink():
            mode = target.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise UnsafePathError("output path is unsafe")
            if not replace:
                raise OutputCollisionError("output already exists; rerun with --replace")
        token = secrets.token_hex(8)
        staging = parent / f".{target.name}.{artifact_type}.partial-{token}"
        staging.mkdir(mode=0o700)
        os.chmod(staging, 0o700)
        return cls(target, artifact_type, replace, staging)

    def discard_staging(self) -> None:
        if not self.staging.exists() and not self.staging.is_symlink():
            return
        if self.staging.is_symlink() or not self.staging.is_dir():
            raise LifecycleError("staging cleanup failed")
        for item in self.staging.iterdir():
            if item.is_dir() and not item.is_symlink():
                for nested in item.rglob("*"):
                    if nested.is_symlink():
                        raise LifecycleError("staging cleanup failed")
        import shutil
        shutil.rmtree(self.staging)

    def _verify_staging_invariant(self, root: Path | None = None) -> None:
        checked_root = self.staging if root is None else root
        try:
            if checked_root.is_symlink() or not checked_root.is_dir() or stat.S_IMODE(checked_root.lstat().st_mode) != 0o700:
                raise OSError
            for item in checked_root.rglob("*"):
                mode = item.lstat().st_mode
                if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                    raise OSError
                if stat.S_ISREG(mode) and stat.S_IMODE(mode) != 0o600:
                    raise OSError
                if stat.S_ISDIR(mode) and stat.S_IMODE(mode) != 0o700:
                    raise OSError
        except OSError as exc:
            raise LifecycleError("staging bundle is unsafe") from exc

    def _verify(self, path: Path, verify: Callable[[Path], None]) -> None:
        try:
            verify(path)
        except ExportError:
            raise
        except Exception:  # noqa: BLE001 - verifier is an untrusted callback boundary.
            raise LifecycleError("bundle verification failed") from None

    def promote(self, verify: Callable[[Path], None]) -> Path:
        try:
            self._verify_staging_invariant()
            self._verify(self.staging, verify)
            self._verify_staging_invariant()
            if not self.output.exists():
                os.rename(self.staging, self.output)
                try:
                    self._verify(self.output, verify)
                    self._verify_staging_invariant(self.output)
                except Exception:
                    os.rename(self.output, self.staging)
                    self.discard_staging()
                    raise
                return self.output
            if not self.replace:
                raise OutputCollisionError("output already exists; rerun with --replace")
            verify_bundle_manifest(self.output, self.artifact_type, _BUNDLE_INVENTORIES[self.artifact_type])
            self._verify_staging_invariant()
            self.backup = self.output.with_name(f".{self.output.name}.{self.artifact_type}.backup-{secrets.token_hex(8)}")
            os.rename(self.output, self.backup)
            try:
                self._verify_staging_invariant()
                os.rename(self.staging, self.output)
                self._verify(self.output, verify)
                self._verify_staging_invariant(self.output)
            except Exception:
                if self.output.exists():
                    os.rename(self.output, self.staging)
                os.rename(self.backup, self.output)
                self.discard_staging()
                raise
            self.discard_backup()
            return self.output
        except OSError as exc:
            raise LifecycleError("bundle promotion failed") from exc

    def discard_backup(self) -> None:
        if self.backup is None:
            return
        import shutil
        if self.backup.is_dir() and not self.backup.is_symlink():
            shutil.rmtree(self.backup)
            self.backup = None
        else:
            raise LifecycleError("backup cleanup failed")


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
    descriptor_copy = _freeze(descriptor)
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
    if len({resource.csv_path for resource in contracts}) != len(contracts):
        raise DescriptorError("descriptor has duplicate resource path")
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
    if set(dialect) != {"header", "delimiter", "quoteChar", "doubleQuote"}:
        raise DescriptorError("unsupported dialect")
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
        if kind == "logical" and orphan_rows is None:
            raise DescriptorError("logical relationship count is invalid")
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
    if isinstance(value, float) and not math.isfinite(value):
        raise DescriptorError(f"{label} must be finite")
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


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def quote_literal(value: str | int | float | bool) -> str:  # noqa: PYI041
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + value.replace("'", "''") + "'"


def _source_path(data_root: Path, resource: ResourceContract) -> Path:
    return data_root / resource.csv_path


def _source_stat(path: Path) -> Any:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise OSError("source is not a regular file")
    return metadata


def _source_failure(resource: ResourceContract, data_root: Path) -> str:
    path = _source_path(data_root, resource)
    try:
        metadata = _source_stat(path)
        with path.open("r", encoding=ENCODING_MAP[resource.encoding], newline="") as handle:
            rows = csv.reader(handle, delimiter=resource.delimiter, quotechar=resource.quote_char)
            header = next(rows)
            row_count = sum(1 for _ in rows)
        expected = [field.name for field in resource.fields]
        if header != expected:
            return resource.name
        if row_count != resource.row_count:
            return resource.name
        if metadata.st_size < 0:
            return resource.name
    except (OSError, StopIteration, UnicodeError, csv.Error, ValueError):
        return resource.name
    return ""


def preflight_sources(package: PackageContract, data_root: Path) -> tuple[SourceState, ...]:
    root = Path(data_root).resolve()
    failures = [failure for resource in package.resources if (failure := _source_failure(resource, root))]
    if failures:
        raise ExportError("source preflight failed for resources: " + ", ".join(failures))
    states = []
    for resource in package.resources:
        path = _source_path(root, resource)
        metadata = _source_stat(path)
        states.append(
            SourceState(resource, path, metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
        )
    return tuple(states)


def fingerprint_sources(states: tuple[SourceState, ...] | list[SourceState]) -> tuple[SourceFingerprint, ...]:
    fingerprints = []
    for state in states:
        digest = sha256()
        with state.path.open("rb") as handle:
            while block := handle.read(1024 * 1024):
                digest.update(block)
        with state.path.open("r", encoding=ENCODING_MAP[state.resource.encoding], newline="") as handle:
            rows = csv.reader(handle, delimiter=state.resource.delimiter, quotechar=state.resource.quote_char)
            field_count = len(next(rows))
            row_count = sum(1 for _ in rows)
        fingerprints.append(
            SourceFingerprint(
                state.resource.name,
                state.path.name,
                state.size,
                digest.hexdigest(),
                row_count,
                field_count,
            )
        )
    return tuple(fingerprints)


def verify_sources_unchanged(states: tuple[SourceState, ...] | list[SourceState]) -> None:
    changed = []
    for state in states:
        try:
            metadata = _source_stat(state.path)
        except OSError:
            changed.append(state.resource.name)
            continue
        current = (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
        captured = (state.device, state.inode, state.size, state.mtime_ns)
        if current != captured:
            changed.append(state.resource.name)
    if changed:
        raise ExportError("source changed during export for resources: " + ", ".join(changed))


def _integer_expression(resource: str, field: str) -> str:
    raw = quote_identifier(field)
    error = quote_literal(f"{resource}.{field} failed integer conversion")
    return (
        f"CASE WHEN {raw} IS NULL OR {raw} = '' THEN NULL "
        f"WHEN NOT regexp_full_match({raw}, '^[+-]?[0-9]+$') "
        f"OR try_cast({raw} AS BIGINT) IS NULL THEN error({error}) "
        f"ELSE cast({raw} AS BIGINT) END"
    )


def _number_expression(resource: str, field: str) -> str:
    raw = quote_identifier(field)
    error = quote_literal(f"{resource}.{field} failed number conversion")
    return (
        f"CASE WHEN {raw} IS NULL OR {raw} = '' THEN NULL "
        f"WHEN try_cast({raw} AS DOUBLE) IS NULL "
        f"OR NOT isfinite(try_cast({raw} AS DOUBLE)) THEN error({error}) "
        f"ELSE cast({raw} AS DOUBLE) END"
    )


def typed_csv_query(
    resource: ResourceContract,
    source_path: Path,
    *,
    temporary_directory: Path | None = None,
) -> str:
    csv_path = Path(source_path)
    duckdb_encoding = ENCODING_MAP[resource.encoding]
    if resource.encoding == "iso-8859-1":
        # DuckDB's latin-1 codec rejects C1 bytes that are valid ISO-8859-1.
        # Decode strictly here, then let DuckDB read the UTF-8 projection; the
        # descriptor source remains untouched.
        decoded = csv_path.read_bytes().decode("iso-8859-1")
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            delete=False,
            dir=temporary_directory,
        ) as temporary:
            temporary.write(decoded)
        csv_path = Path(temporary.name)
        _TRANSCODED_SOURCES.append(csv_path)
        duckdb_encoding = "utf-8"
    columns = "{" + ", ".join(
        f"{quote_literal(field.name)}: {quote_literal('VARCHAR')}" for field in resource.fields
    ) + "}"
    read_csv = (
        f"read_csv({quote_literal(str(csv_path))}, header=true, all_varchar=true, "
        f"columns={columns}, delim={quote_literal(resource.delimiter)}, "
        f"quote={quote_literal(resource.quote_char)}, escape={quote_literal(resource.quote_char)}, "
        f"encoding={quote_literal(duckdb_encoding)})"
    )
    projections = []
    for field in resource.fields:
        if field.frictionless_type == "integer":
            expression = _integer_expression(resource.name, field.name)
        elif field.frictionless_type == "number":
            expression = _number_expression(resource.name, field.name)
        else:
            expression = f"NULLIF({quote_identifier(field.name)}, '')"
        projections.append(f"{expression} AS {quote_identifier(field.name)}")
    return f"SELECT {', '.join(projections)} FROM {read_csv}"


def _validation_record(
    resource: ResourceContract,
    field: str | None,
    rule: str,
    expected: float | str | list[object],
    observed: float | str | list[object],
) -> ValidationRecord:
    if observed != expected:
        target = resource.name if field is None else f"{resource.name}.{field}"
        raise ValidationError(f"{target} {rule} did not match")
    return ValidationRecord(resource.name, field, rule, expected, observed)


def validate_relation_schema(
    connection: duckdb.DuckDBPyConnection,
    resource: ResourceContract,
    relation: str,
) -> list[ValidationRecord]:
    """Validate ordered names and mapped types through DESCRIBE."""
    described = connection.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()
    observed = [[str(column[0]), str(column[1]).upper()] for column in described]
    expected = [[field.name, field.duckdb_type] for field in resource.fields]
    return [_validation_record(resource, None, "schema", expected, observed)]


def validate_resource_rules(
    connection: duckdb.DuckDBPyConnection,
    resource: ResourceContract,
    relation: str,
) -> list[ValidationRecord]:
    """Validate row count, requiredness, enum, minimum, and maximum rules."""
    checks: list[tuple[str | None, str, str, int]] = [
        (None, "row count", "count(*)", resource.row_count)
    ]
    for field in resource.fields:
        column = quote_identifier(field.name)
        if field.required:
            checks.append((field.name, "required count", f"count(*) FILTER (WHERE {column} IS NULL)", 0))
        if field.enum is not None:
            values = ", ".join(quote_literal(value) for value in field.enum)
            checks.append(
                (field.name, "enum count", f"count(*) FILTER (WHERE {column} IS NOT NULL AND {column} NOT IN ({values}))", 0)
            )
        if field.minimum is not None:
            checks.append(
                (field.name, "minimum count", f"count(*) FILTER (WHERE {column} IS NOT NULL AND {column} < {quote_literal(field.minimum)})", 0)
            )
        if field.maximum is not None:
            checks.append(
                (field.name, "maximum count", f"count(*) FILTER (WHERE {column} IS NOT NULL AND {column} > {quote_literal(field.maximum)})", 0)
            )
    aggregates = ", ".join(f"{expression} AS check_{index}" for index, (_, _, expression, _) in enumerate(checks))
    observed = connection.execute(f"SELECT {aggregates} FROM {relation}").fetchone()
    return [
        _validation_record(resource, field, rule, expected, int(value))
        for (field, rule, _, expected), value in zip(checks, observed, strict=True)
    ]


def validate_primary_key(
    connection: duckdb.DuckDBPyConnection,
    resource: ResourceContract,
    relation: str,
) -> list[ValidationRecord]:
    """Validate a scalar primary key when declared."""
    if resource.primary_key is None:
        return []
    key = quote_identifier(resource.primary_key)
    null_count, duplicate_count = connection.execute(
        f"SELECT "
        f"(SELECT count(*) FILTER (WHERE {key} IS NULL) FROM {relation}), "
        f"(SELECT count(*) FROM (SELECT {key} FROM {relation} WHERE {key} IS NOT NULL "
        f"GROUP BY {key} HAVING count(*) > 1))"
    ).fetchone()
    records = []
    if int(null_count) != 0:
        raise ValidationError(f"{resource.name} primary key was not complete")
    records.append(ValidationRecord(resource.name, resource.primary_key, "primary key completeness", 0, int(null_count)))
    if int(duplicate_count) != 0:
        raise ValidationError(f"{resource.name} primary key was not unique")
    records.append(ValidationRecord(resource.name, resource.primary_key, "primary key uniqueness", 0, int(duplicate_count)))
    return records


def validate_foreign_keys(
    connection: duckdb.DuckDBPyConnection,
    resource: ResourceContract,
    relations: dict[str, str],
) -> list[ValidationRecord]:
    """Validate every strict scalar foreign key by aggregate anti-join."""
    child_relation = relations[resource.name]
    records = []
    for relationship in resource.foreign_keys:
        child = quote_identifier(relationship.field)
        reference = quote_identifier(relationship.reference_field)
        parent_relation = relations[relationship.reference_resource]
        (observed,) = connection.execute(
            f"SELECT count(*) FILTER (WHERE child.{child} IS NOT NULL AND NOT EXISTS "
            f"(SELECT 1 FROM {parent_relation} AS parent WHERE parent.{reference} = child.{child})) "
            f"FROM {child_relation} AS child"
        ).fetchone()
        records.append(_validation_record(resource, relationship.field, "foreign key count", 0, int(observed)))
    return records


def validate_logical_foreign_keys(
    connection: duckdb.DuckDBPyConnection,
    resource: ResourceContract,
    relations: dict[str, str],
) -> list[ValidationRecord]:
    """Compare null and nonnull-orphan counts with descriptor metadata."""
    child_relation = relations[resource.name]
    records = []
    for relationship in resource.logical_foreign_keys:
        child = quote_identifier(relationship.field)
        reference = quote_identifier(relationship.reference_field)
        parent_relation = relations[relationship.reference_resource]
        null_rows, orphan_rows = connection.execute(
            f"SELECT count(*) FILTER (WHERE child.{child} IS NULL), "
            f"count(*) FILTER (WHERE child.{child} IS NOT NULL AND NOT EXISTS "
            f"(SELECT 1 FROM {parent_relation} AS parent WHERE parent.{reference} = child.{child})) "
            f"FROM {child_relation} AS child"
        ).fetchone()
        records.append(
            _validation_record(resource, relationship.field, "logical null count", relationship.null_rows or 0, int(null_rows))
        )
        records.append(
            _validation_record(resource, relationship.field, "logical orphan count", relationship.orphan_rows or 0, int(orphan_rows))
        )
    return records


def validate_artifact(
    connection: duckdb.DuckDBPyConnection,
    package: PackageContract,
    relation_for: Callable[[ResourceContract], str],
) -> tuple[ValidationRecord, ...]:
    records: list[ValidationRecord] = []
    relations = {resource.name: relation_for(resource) for resource in package.resources}
    for resource in package.resources:
        records.extend(validate_relation_schema(connection, resource, relations[resource.name]))
        records.extend(validate_resource_rules(connection, resource, relations[resource.name]))
        records.extend(validate_primary_key(connection, resource, relations[resource.name]))
        records.extend(validate_foreign_keys(connection, resource, relations))
        records.extend(validate_logical_foreign_keys(connection, resource, relations))
    return tuple(records)


def _arrow_schema(resource: ResourceContract) -> Any:
    import pyarrow as pa

    types = {"string": pa.string(), "integer": pa.int64(), "number": pa.float64()}
    return pa.schema([pa.field(field.name, types[field.frictionless_type]) for field in resource.fields])


def _verify_parquet_with_pyarrow(bundle: Path, package: PackageContract) -> None:
    """Independently check typed Parquet metadata without exposing clinical values."""
    import pyarrow.parquet as pq

    root = Path(bundle)
    for resource in package.resources:
        try:
            parquet = pq.ParquetFile(root / f"{resource.name}.parquet")
            metadata = parquet.metadata
            if metadata is None or parquet.schema_arrow != _arrow_schema(resource):
                raise ValueError
            if metadata.num_rows != resource.row_count:
                raise ValueError
            for row_group_index in range(metadata.num_row_groups):
                row_group = metadata.row_group(row_group_index)
                for column_index in range(row_group.num_columns):
                    if row_group.column(column_index).compression != "ZSTD":
                        raise ValueError
        except Exception as exc:
            raise ValidationError("Parquet artifact validation failed") from exc


def _parquet_output_fingerprint(path: Path, resource: ResourceContract) -> OutputFingerprint:
    return OutputFingerprint(
        path.name,
        path.stat().st_size,
        sha256_file(path),
        resource.row_count,
        len(resource.fields),
        tuple((field.name, str(_arrow_schema(resource).field(index).type)) for index, field in enumerate(resource.fields)),
    )


def _finish_parquet_manifest(
    staging: Path,
    package: PackageContract,
    source_hashes: tuple[SourceFingerprint, ...],
    records: tuple[ValidationRecord, ...],
) -> None:
    descriptor = staging / "source-datapackage.json"
    descriptor.write_bytes(package.descriptor_bytes)
    descriptor.chmod(0o600)
    outputs = [
        _parquet_output_fingerprint(staging / f"{resource.name}.parquet", resource)
        for resource in package.resources
    ]
    outputs.append(OutputFingerprint(descriptor.name, descriptor.stat().st_size, sha256_file(descriptor)))
    write_manifest(
        staging / "manifest.json",
        build_manifest("parquet-bundle", package, build_provenance(), source_hashes, tuple(outputs), records),
    )


def verify_parquet_bundle(path: Path, package: PackageContract) -> None:
    """Verify exact inventory, integrity binding, and Parquet metadata of a promoted bundle."""
    root = Path(path)
    manifest = verify_bundle_manifest(root, "parquet-bundle", _BUNDLE_INVENTORIES["parquet-bundle"])
    descriptor = manifest["descriptor"]
    if (
        manifest["package"] != {"name": package.name, "version": package.version, "snapshot": package.snapshot}
        or descriptor != {"basename": package.descriptor_path.name, "size": len(package.descriptor_bytes), "sha256": package.descriptor_sha256}
    ):
        raise LifecycleError("existing bundle is not a verified bundle")
    try:
        copied_descriptor = root / "source-datapackage.json"
        if copied_descriptor.read_bytes() != package.descriptor_bytes:
            raise OSError
        _verify_parquet_with_pyarrow(root, package)
        expected_outputs = {
            f"{resource.name}.parquet": _parquet_output_fingerprint(root / f"{resource.name}.parquet", resource)
            for resource in package.resources
        }
        expected_outputs["source-datapackage.json"] = OutputFingerprint(
            "source-datapackage.json", len(package.descriptor_bytes), package.descriptor_sha256
        )
        for output in manifest["outputs"]:
            expected = expected_outputs.get(output["basename"])
            if expected is None or output != {
                "basename": expected.basename, "size": expected.size, "sha256": expected.sha256,
                "rowCount": expected.row_count, "fieldCount": expected.field_count,
                "columns": [list(column) for column in expected.columns],
                "tables": [list(table) for table in expected.tables],
            }:
                raise OSError
    except (OSError, ValidationError) as exc:
        raise LifecycleError("existing bundle is not a verified bundle") from exc


def export_parquet_bundle(config: ExportConfig) -> Path:
    """Export one verified, typed, unpartitioned Zstandard Parquet bundle."""
    package = load_package_contract(config.descriptor)
    sources = preflight_sources(package, config.data_root)
    output = ensure_safe_output(ROOT, package, sources, config.output)
    source_hashes = fingerprint_sources(sources)
    run = BundleRun.start(output, "parquet-bundle", config.replace)
    connection: duckdb.DuckDBPyConnection | None = None
    try:
        connection = duckdb.connect()
        spill = run.staging / ".duckdb-tmp"
        spill.mkdir(mode=0o700)
        spill.chmod(0o700)
        connection.execute(f"SET temp_directory={quote_literal(str(spill))}")
        for source in sources:
            target = run.staging / f"{source.resource.name}.parquet"
            query = typed_csv_query(
                source.resource,
                source.path,
                temporary_directory=run.staging,
            )
            try:
                connection.execute(
                    f"COPY ({query}) TO {quote_literal(str(target))} "
                    "(FORMAT PARQUET, COMPRESSION ZSTD)"
                )
            finally:
                _remove_transcoded_sources()
            target.chmod(0o600)
        records = validate_artifact(
            connection,
            package,
            lambda resource: f"read_parquet({quote_literal(str(run.staging / (resource.name + '.parquet')))})",
        )
        _verify_parquet_with_pyarrow(run.staging, package)
        verify_sources_unchanged(sources)
        connection.close()
        connection = None
        shutil.rmtree(spill)
        _finish_parquet_manifest(run.staging, package, source_hashes, records)
        return run.promote(lambda bundle: verify_parquet_bundle(bundle, package))
    except Exception as error:  # noqa: BLE001 - public export boundary must redact dependencies.
        try:
            run.discard_staging()
        except (LifecycleError, OSError):
            raise ExportError("parquet export failed") from None
        raise _redacted_duckdb_error(error, package, "parquet export failed") from None
    finally:
        if connection is not None:
            connection.close()


def _redacted_duckdb_error(error: Exception, package: PackageContract, fallback: str) -> ExportError:
    message = str(error)
    tokens = {
        f"{resource.name}.{field.name} failed {kind} conversion"
        for resource in package.resources
        for field in resource.fields
        for kind in ("integer", "number")
        if field.frictionless_type in {"integer", "number"}
    }
    for token in tokens:
        if token in message:
            return ExportError(token)
    return ExportError(fallback)


def resource_table_ddl(resource: ResourceContract) -> str:
    """Build the constrained physical table definition for one descriptor resource."""
    columns: list[str] = []
    for field in resource.fields:
        column = quote_identifier(field.name)
        clauses = [column, field.duckdb_type]
        if field.required:
            clauses.append("NOT NULL")
        checks: list[str] = []
        if field.enum is not None:
            checks.append(f"{column} IN ({', '.join(quote_literal(value) for value in field.enum)})")
        if field.minimum is not None:
            checks.append(f"{column} >= {quote_literal(field.minimum)}")
        if field.maximum is not None:
            checks.append(f"{column} <= {quote_literal(field.maximum)}")
        if checks:
            clauses.append("CHECK (" + " AND ".join(checks) + ")")
        columns.append(" ".join(clauses))
    return f"CREATE TABLE main.{quote_identifier(resource.name)} (" + ", ".join(columns) + ")"


_DUCKDB_META_DDL = """
CREATE SCHEMA ppoc_meta;
CREATE TABLE ppoc_meta.build (manifest_version INTEGER NOT NULL, package_name VARCHAR NOT NULL, package_version VARCHAR NOT NULL, snapshot VARCHAR NOT NULL, created_at_utc VARCHAR NOT NULL, descriptor_sha256 VARCHAR NOT NULL, python_version VARCHAR NOT NULL, duckdb_version VARCHAR NOT NULL, pyarrow_version VARCHAR NOT NULL, exporter_git_revision VARCHAR, exporter_git_dirty BOOLEAN, exporter_module_sha256 VARCHAR NOT NULL);
CREATE TABLE ppoc_meta.resources (ordinal INTEGER NOT NULL, resource_name VARCHAR NOT NULL, source_basename VARCHAR NOT NULL, source_size BIGINT NOT NULL, source_sha256 VARCHAR NOT NULL, row_count BIGINT NOT NULL, table_name VARCHAR NOT NULL, field_count BIGINT NOT NULL);
CREATE TABLE ppoc_meta.descriptor (descriptor_sha256 VARCHAR NOT NULL, descriptor_json VARCHAR NOT NULL);
CREATE TABLE ppoc_meta.validations (ordinal INTEGER NOT NULL, resource_name VARCHAR NOT NULL, field_name VARCHAR, rule VARCHAR NOT NULL, expected_json VARCHAR NOT NULL, observed_json VARCHAR NOT NULL, status VARCHAR NOT NULL CHECK (status = 'PASS'));
"""

_DUCKDB_META_SCHEMAS = {
    "build": (("manifest_version", "INTEGER", "NO"), ("package_name", "VARCHAR", "NO"), ("package_version", "VARCHAR", "NO"), ("snapshot", "VARCHAR", "NO"), ("created_at_utc", "VARCHAR", "NO"), ("descriptor_sha256", "VARCHAR", "NO"), ("python_version", "VARCHAR", "NO"), ("duckdb_version", "VARCHAR", "NO"), ("pyarrow_version", "VARCHAR", "NO"), ("exporter_git_revision", "VARCHAR", "YES"), ("exporter_git_dirty", "BOOLEAN", "YES"), ("exporter_module_sha256", "VARCHAR", "NO")),
    "resources": (("ordinal", "INTEGER", "NO"), ("resource_name", "VARCHAR", "NO"), ("source_basename", "VARCHAR", "NO"), ("source_size", "BIGINT", "NO"), ("source_sha256", "VARCHAR", "NO"), ("row_count", "BIGINT", "NO"), ("table_name", "VARCHAR", "NO"), ("field_count", "BIGINT", "NO")),
    "descriptor": (("descriptor_sha256", "VARCHAR", "NO"), ("descriptor_json", "VARCHAR", "NO")),
    "validations": (("ordinal", "INTEGER", "NO"), ("resource_name", "VARCHAR", "NO"), ("field_name", "VARCHAR", "YES"), ("rule", "VARCHAR", "NO"), ("expected_json", "VARCHAR", "NO"), ("observed_json", "VARCHAR", "NO"), ("status", "VARCHAR", "NO")),
}
_DUCKDB_META_NON_NULL_CONSTRAINTS = {
    "build": (),
    "resources": (),
    "descriptor": (),
    "validations": (("CHECK", "CHECK((status = 'PASS'))"),),
}


def _canonical_json(value: object) -> str:
    def thaw(item: object) -> object:
        if isinstance(item, Mapping):
            return {key: thaw(value) for key, value in item.items()}
        if isinstance(item, tuple):
            return [thaw(value) for value in item]
        return item

    return json.dumps(thaw(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _duckdb_output_fingerprint(path: Path, package: PackageContract) -> OutputFingerprint:
    return OutputFingerprint(path.name, path.stat().st_size, sha256_file(path), tables=tuple((resource.name, resource.row_count, len(resource.fields)) for resource in package.resources))


def _table_constraints(connection: duckdb.DuckDBPyConnection, schema: str, table: str) -> tuple[tuple[str, str], ...]:
    return tuple(connection.execute("SELECT constraint_type, constraint_text FROM duckdb_constraints() WHERE schema_name = ? AND table_name = ? ORDER BY constraint_type, constraint_text", (schema, table)).fetchall())


def _reference_resource_table_ddl(resource: ResourceContract) -> str:
    columns: list[str] = []
    for field in resource.fields:
        column = quote_identifier(field.name)
        clauses = [column, field.duckdb_type]
        if field.required:
            clauses.append("NOT NULL")
        checks: list[str] = []
        if field.enum is not None:
            checks.append(f"{column} IN ({', '.join(quote_literal(value) for value in field.enum)})")
        if field.minimum is not None:
            checks.append(f"{column} >= {quote_literal(field.minimum)}")
        if field.maximum is not None:
            checks.append(f"{column} <= {quote_literal(field.maximum)}")
        if checks:
            clauses.append("CHECK (" + " AND ".join(checks) + ")")
        columns.append(" ".join(clauses))
    return f"CREATE TABLE main.{quote_identifier(resource.name)} (" + ", ".join(columns) + ")"


def _reference_resource_constraints(resource: ResourceContract) -> tuple[tuple[str, str], ...]:
    connection = duckdb.connect()
    try:
        connection.execute(_reference_resource_table_ddl(resource))
        return _table_constraints(connection, "main", resource.name)
    finally:
        connection.close()


def _validation_rows(records: tuple[ValidationRecord, ...]) -> list[tuple[int, str, str | None, str, str, str, str]]:
    return [
        (ordinal, record.resource, record.field, record.rule, _canonical_json(record.expected), _canonical_json(record.observed), record.status)
        for ordinal, record in enumerate(records, start=1)
    ]


def _populate_duckdb_metadata(connection: duckdb.DuckDBPyConnection, package: PackageContract, provenance: BuildProvenance, source_hashes: tuple[SourceFingerprint, ...], records: tuple[ValidationRecord, ...]) -> None:
    connection.execute(_DUCKDB_META_DDL)
    connection.execute("INSERT INTO ppoc_meta.build VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (1, package.name, package.version, package.snapshot, provenance.created_at_utc, package.descriptor_sha256, provenance.python_version, provenance.duckdb_version, provenance.pyarrow_version, provenance.exporter_git_revision, provenance.exporter_git_dirty, provenance.exporter_module_sha256))
    connection.executemany("INSERT INTO ppoc_meta.resources VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [(ordinal, source.resource_name, source.basename, source.size, source.sha256, source.row_count, source.resource_name, source.field_count) for ordinal, source in enumerate(source_hashes, start=1)])
    connection.execute("INSERT INTO ppoc_meta.descriptor VALUES (?, ?)", (package.descriptor_sha256, _canonical_json(package.descriptor)))
    connection.executemany("INSERT INTO ppoc_meta.validations VALUES (?, ?, ?, ?, ?, ?, ?)", _validation_rows(records))


def _verify_duckdb_database(path: Path, package: PackageContract, manifest: dict[str, Any] | None = None) -> None:
    connection: duckdb.DuckDBPyConnection | None = None
    try:
        connection = duckdb.connect(str(path), read_only=True)
        tables = set(connection.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema IN ('main', 'ppoc_meta')").fetchall())
        expected_tables = {*(('main', resource.name) for resource in package.resources), *(('ppoc_meta', name) for name in ('build', 'resources', 'descriptor', 'validations'))}
        if tables != expected_tables:
            raise ValueError
        for resource in package.resources:
            columns = connection.execute(f"DESCRIBE main.{quote_identifier(resource.name)}").fetchall()
            expected_columns = [(field.name, field.duckdb_type, "NO" if field.required else "YES") for field in resource.fields]
            if [(column[0], column[1], column[2]) for column in columns] != expected_columns or _table_constraints(connection, "main", resource.name) != _reference_resource_constraints(resource) or connection.execute(f"SELECT count(*) FROM main.{quote_identifier(resource.name)}").fetchone() != (resource.row_count,):
                raise ValueError
        for table, expected_columns in _DUCKDB_META_SCHEMAS.items():
            columns = connection.execute(f"DESCRIBE ppoc_meta.{quote_identifier(table)}").fetchall()
            constraints = tuple(item for item in _table_constraints(connection, "ppoc_meta", table) if item[0] != "NOT NULL")
            if [(column[0], column[1], column[2]) for column in columns] != list(expected_columns) or constraints != _DUCKDB_META_NON_NULL_CONSTRAINTS[table]:
                raise ValueError
        constraints = connection.execute("SELECT constraint_type FROM duckdb_constraints() WHERE schema_name IN ('main', 'ppoc_meta')").fetchall()
        if any(kind in {'PRIMARY KEY', 'FOREIGN KEY'} for (kind,) in constraints) or connection.execute("SELECT count(*) FROM duckdb_indexes() WHERE schema_name IN ('main', 'ppoc_meta')").fetchone() != (0,) or connection.execute("SELECT count(*) FROM duckdb_views() WHERE schema_name IN ('main', 'ppoc_meta') AND NOT internal").fetchone() != (0,) or connection.execute("SELECT count(*) FROM duckdb_sequences() WHERE schema_name IN ('main', 'ppoc_meta')").fetchone() != (0,) or connection.execute("SELECT count(*) FROM duckdb_functions() WHERE schema_name IN ('main', 'ppoc_meta') AND function_type = 'macro' AND NOT internal").fetchone() != (0,):
            raise ValueError
        build = connection.execute("SELECT * FROM ppoc_meta.build").fetchall()
        if len(build) != 1 or build[0][0:4] != (1, package.name, package.version, package.snapshot) or build[0][5] != package.descriptor_sha256:
            raise ValueError
        descriptor = connection.execute("SELECT descriptor_sha256, descriptor_json FROM ppoc_meta.descriptor").fetchall()
        if descriptor != [(package.descriptor_sha256, _canonical_json(package.descriptor))]:
            raise ValueError
        resources = connection.execute("SELECT ordinal, resource_name, row_count, table_name, field_count FROM ppoc_meta.resources ORDER BY ordinal").fetchall()
        if resources != [(index, item.name, item.row_count, item.name, len(item.fields)) for index, item in enumerate(package.resources, start=1)]:
            raise ValueError
        fresh_records = validate_artifact(connection, package, lambda resource: f"main.{quote_identifier(resource.name)}")
        validations = connection.execute("SELECT ordinal, resource_name, field_name, rule, expected_json, observed_json, status FROM ppoc_meta.validations ORDER BY ordinal").fetchall()
        if validations != _validation_rows(fresh_records):
            raise ValueError
        if manifest is not None:
            output = _duckdb_output_fingerprint(path, package)
            expected_output = {"basename": output.basename, "size": output.size, "sha256": output.sha256, "rowCount": None, "fieldCount": None, "columns": [], "tables": [list(item) for item in output.tables]}
            expected_build = manifest["build"]
            expected_sources = [
                (index, item["resource"], item["basename"], item["size"], item["sha256"], item["rowCount"], item["resource"], item["fieldCount"])
                for index, item in enumerate(manifest["sources"], start=1)
            ]
            source_metadata = connection.execute("SELECT * FROM ppoc_meta.resources ORDER BY ordinal").fetchall()
            if manifest["outputs"] != [expected_output] or manifest["validation"] != {"status": "PASS", "checkCount": len(fresh_records), "failedChecks": 0} or build[0] != (1, package.name, package.version, package.snapshot, expected_build["createdAtUtc"], package.descriptor_sha256, expected_build["pythonVersion"], expected_build["duckdbVersion"], expected_build["pyarrowVersion"], expected_build["exporterGitRevision"], expected_build["exporterGitDirty"], expected_build["exporterModuleSha256"]) or source_metadata != expected_sources:
                raise ValueError
    except Exception as exc:
        raise ValidationError("DuckDB artifact validation failed") from exc
    finally:
        if connection is not None:
            connection.close()


def verify_duckdb_bundle(path: Path, package: PackageContract) -> None:
    """Verify inventory, manifest binding, and read-only physical DuckDB contents."""
    root = Path(path)
    try:
        manifest = verify_bundle_manifest(root, "duckdb-bundle", _BUNDLE_INVENTORIES["duckdb-bundle"])
        if manifest["package"] != {"name": package.name, "version": package.version, "snapshot": package.snapshot} or manifest["descriptor"] != {"basename": package.descriptor_path.name, "size": len(package.descriptor_bytes), "sha256": package.descriptor_sha256}:
            raise ValueError
        _verify_duckdb_database(root / "ppoc.duckdb", package, manifest)
    except (LifecycleError, ValidationError, OSError, ValueError) as exc:
        raise LifecycleError("existing bundle is not a verified bundle") from exc


def export_duckdb_bundle(config: ExportConfig) -> Path:
    """Export a verified, materialized typed DuckDB analytical bundle."""
    package = load_package_contract(config.descriptor)
    sources = preflight_sources(package, config.data_root)
    output = ensure_safe_output(ROOT, package, sources, config.output)
    source_hashes = fingerprint_sources(sources)
    provenance = build_provenance()
    run = BundleRun.start(output, "duckdb-bundle", config.replace)
    connection: duckdb.DuckDBPyConnection | None = None
    try:
        database = run.staging / "ppoc.duckdb"
        connection = duckdb.connect(str(database))
        for source in sources:
            connection.execute(resource_table_ddl(source.resource))
            query = typed_csv_query(
                source.resource,
                source.path,
                temporary_directory=run.staging,
            )
            try:
                connection.execute(
                    f"INSERT INTO main.{quote_identifier(source.resource.name)} {query}"
                )
            finally:
                _remove_transcoded_sources()
        records = validate_artifact(connection, package, lambda resource: f"main.{quote_identifier(resource.name)}")
        verify_sources_unchanged(sources)
        _populate_duckdb_metadata(connection, package, provenance, source_hashes, records)
        connection.execute("CHECKPOINT")
        connection.close()
        connection = None
        database.chmod(0o600)
        _verify_duckdb_database(database, package)
        write_manifest(run.staging / "manifest.json", build_manifest("duckdb-bundle", package, provenance, source_hashes, (_duckdb_output_fingerprint(database, package),), records))
        return run.promote(lambda bundle: verify_duckdb_bundle(bundle, package))
    except Exception as error:  # noqa: BLE001 - public export boundary must redact dependencies.
        try:
            run.discard_staging()
        except (LifecycleError, OSError):
            raise ExportError("duckdb export failed") from None
        raise _redacted_duckdb_error(error, package, "duckdb export failed") from None
    finally:
        if connection is not None:
            connection.close()


def parse_args(artifact_type: str, argv: Sequence[str] | None = None) -> ExportConfig:
    """Parse the common, explicit analytical-export operator interface."""
    if artifact_type not in {"parquet", "duckdb"}:
        raise ValueError("unsupported CLI artifact type")
    parser = argparse.ArgumentParser(
        description=(
            "Export typed PPOC Parquet resources"
            if artifact_type == "parquet"
            else "Build a materialized typed PPOC DuckDB"
        )
    )
    parser.add_argument("--descriptor", type=Path, default=DEFAULT_DESCRIPTOR)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args(argv)
    data_root = args.data_root
    if data_root is None:
        value = os.environ.get("PPOC_DATA_ROOT")
        if not value:
            parser.error("--data-root is required when PPOC_DATA_ROOT is unset")
        data_root = Path(value)
    return ExportConfig(args.descriptor, data_root, args.output, args.replace)


def cli_main(artifact_type: str, argv: Sequence[str] | None = None) -> int:
    """Run an export while keeping expected operator failures redacted."""
    try:
        config = parse_args(artifact_type, argv)
        output = (
            export_parquet_bundle(config)
            if artifact_type == "parquet"
            else export_duckdb_bundle(config)
        )
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        total_rows = sum(item["rowCount"] for item in manifest["sources"])
        print(
            f"artifact={manifest['artifactType']} output={output} "
            f"snapshot={manifest['package']['snapshot']} resources=8 "
            f"rows={total_rows} status={manifest['status']}"
        )
        return 0
    except ExportError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:  # noqa: BLE001 - public CLI boundary must redact unexpected failures.
        print("analytical export failed", file=sys.stderr)
        return 1


@atexit.register
def _remove_transcoded_sources() -> None:
    while _TRANSCODED_SOURCES:
        path = _TRANSCODED_SOURCES.pop()
        try:
            path.unlink()
        except FileNotFoundError:
            pass

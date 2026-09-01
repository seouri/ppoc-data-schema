from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

from synthetic.derivation import DerivationResult, DerivationUnavailable
from synthetic.schema_contract import resource_spec

AUGMENTER_ORACLE_ID = "augmenter-cli-v1"
AUGMENTER_RUNTIME_MANIFEST_SHA256 = (
    "b50afc36eca61684380154129cdacf484e62d56fa6da55914adab18c2d94d1d6"
)
UV_LOCK_SHA256 = "d17f8c2613da7c59dd858fe1e39025ce72e0241fb0bbc400772ab4273a694810"

_UNAVAILABLE_MESSAGE = "source-matched augmenter unavailable"
_MANIFEST_PATH = Path("data/augment-runtime-manifest.json")
_EXPECTED_RUNTIME_PATHS = frozenset(
    {
        "scripts/__init__.py",
        "scripts/augment.py",
        "scripts/harrall_outliers.py",
        "data/statage_combined.csv",
        "data/wtage_combined.csv",
        "data/bmiagerev.csv",
        "data/hcageinf.csv",
        "data/wtstat.csv",
        "data/wtleninf.csv",
        "data/hvage_no_pub.csv",
        "data/hvage_earlier_pub.csv",
        "data/hvage_average_pub.csv",
        "data/hvage_later_pub.csv",
        "data/icd10cm-tabular-2026.csv",
    }
)
_OUTPUT_PATTERN = re.compile(r"^(visits|patients)_augmented-[0-9]{14}\.csv$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class _AdapterFailure(Exception):
    pass


def _unavailable() -> NoReturn:
    raise DerivationUnavailable(_UNAVAILABLE_MESSAGE) from None


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(_: str) -> NoReturn:
    raise ValueError("non-finite JSON number")


def _require_directory(path: Path) -> None:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise _AdapterFailure


def _require_regular_file(path: Path) -> os.stat_result:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise _AdapterFailure
    return metadata


def _safe_manifest_relative_path(raw_path: object) -> Path:
    if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path:
        raise _AdapterFailure
    pure = PurePosixPath(raw_path)
    if pure.is_absolute() or pure.as_posix() != raw_path:
        raise _AdapterFailure
    if any(part in {"", ".", ".."} for part in pure.parts):
        raise _AdapterFailure
    return Path(*pure.parts)


def _read_regular_bytes(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise _AdapterFailure
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _verify_manifest(root: Path) -> tuple[tuple[Path, int, str], ...]:
    _require_directory(root)
    manifest_path = root / _MANIFEST_PATH
    manifest_bytes = _read_regular_bytes(manifest_path)
    if hashlib.sha256(manifest_bytes).hexdigest() != AUGMENTER_RUNTIME_MANIFEST_SHA256:
        raise _AdapterFailure
    manifest = json.loads(
        manifest_bytes.decode("utf-8"),
        object_pairs_hook=_strict_object,
        parse_constant=_reject_json_constant,
    )
    if not isinstance(manifest, dict) or manifest.get("manifest_version") != 1:
        raise _AdapterFailure
    entries = manifest.get("files")
    if not isinstance(entries, list) or len(entries) != len(_EXPECTED_RUNTIME_PATHS):
        raise _AdapterFailure

    verified: list[tuple[Path, int, str]] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise _AdapterFailure
        relative = _safe_manifest_relative_path(entry.get("path"))
        relative_name = relative.as_posix()
        byte_count = entry.get("bytes")
        digest = entry.get("sha256")
        if (
            relative_name in seen
            or entry.get("source_relative_name") != relative_name
            or not isinstance(entry.get("role"), str)
            or isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count < 0
            or not isinstance(digest, str)
            or _SHA256_PATTERN.fullmatch(digest) is None
        ):
            raise _AdapterFailure
        seen.add(relative_name)

        current = root
        for component in relative.parts[:-1]:
            current /= component
            _require_directory(current)
        source = root / relative
        metadata = _require_regular_file(source)
        source_bytes = _read_regular_bytes(source)
        if (
            metadata.st_size != byte_count
            or len(source_bytes) != byte_count
            or hashlib.sha256(source_bytes).hexdigest() != digest
        ):
            raise _AdapterFailure
        verified.append((relative, byte_count, digest))

    if seen != _EXPECTED_RUNTIME_PATHS:
        raise _AdapterFailure
    return tuple(verified)


def verify_source_matched_runtime(repository_root: Path) -> None:
    """Verify the manifest-listed runtime and locked environment without leaking details."""
    failed = False
    try:
        if not isinstance(repository_root, Path):
            raise _AdapterFailure
        lock_path = repository_root / "uv.lock"
        _require_regular_file(lock_path)
        lock_bytes = _read_regular_bytes(lock_path)
        if hashlib.sha256(lock_bytes).hexdigest() != UV_LOCK_SHA256:
            raise _AdapterFailure
        _verify_manifest(repository_root)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:  # noqa: BLE001 - public closure failures are deliberately redacted.
        failed = True
    if failed:
        _unavailable()


def _snapshot_runtime(
    source_root: Path,
    runtime_root: Path,
    entries: tuple[tuple[Path, int, str], ...],
) -> None:
    runtime_root.mkdir(mode=0o700)
    for relative, byte_count, digest in entries:
        source_bytes = _read_regular_bytes(source_root / relative)
        if len(source_bytes) != byte_count or hashlib.sha256(source_bytes).hexdigest() != digest:
            raise _AdapterFailure
        destination = runtime_root / relative
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(source_bytes)

        copied_metadata = _require_regular_file(destination)
        copied_bytes = _read_regular_bytes(destination)
        if (
            copied_metadata.st_size != byte_count
            or len(copied_bytes) != byte_count
            or hashlib.sha256(copied_bytes).hexdigest() != digest
        ):
            raise _AdapterFailure


def _safe_output_parts(
    descriptor: dict[str, Any],
    resource_name: str,
) -> tuple[str, ...]:
    specification = resource_spec(descriptor, resource_name)
    raw_path = specification.get("path")
    if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path:
        raise _AdapterFailure
    pure = PurePosixPath(raw_path)
    if pure.is_absolute() or pure.as_posix() != raw_path:
        raise _AdapterFailure
    if any(part in {"", ".", ".."} for part in pure.parts):
        raise _AdapterFailure
    return pure.parts


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _open_package_root(package_root: Path) -> tuple[int, tuple[int, int]]:
    descriptor = os.open(package_root, _directory_open_flags())
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISDIR(metadata.st_mode):
            raise _AdapterFailure
        return descriptor, (metadata.st_dev, metadata.st_ino)
    except Exception:
        os.close(descriptor)
        raise


def _require_package_identity(
    package_root: Path,
    identity: tuple[int, int],
) -> None:
    metadata = package_root.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or (metadata.st_dev, metadata.st_ino) != identity
    ):
        raise _AdapterFailure


def _open_parent_directory(root_descriptor: int, parts: tuple[str, ...]) -> int:
    current = os.dup(root_descriptor)
    try:
        for component in parts[:-1]:
            following = os.open(
                component,
                _directory_open_flags(),
                dir_fd=current,
            )
            os.close(current)
            current = following
        return current
    except Exception:
        os.close(current)
        raise


def _require_output_absent(
    root_descriptor: int,
    parts: tuple[str, ...],
) -> None:
    parent_descriptor = _open_parent_directory(root_descriptor, parts)
    try:
        try:
            os.stat(parts[-1], dir_fd=parent_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise _AdapterFailure
    finally:
        os.close(parent_descriptor)


def _validated_output_bytes(output_root: Path) -> dict[str, bytes]:
    entries = list(output_root.iterdir())
    if len(entries) != 2:
        raise _AdapterFailure

    outputs: dict[str, bytes] = {}
    for path in entries:
        _require_regular_file(path)
        match = _OUTPUT_PATTERN.fullmatch(path.name)
        if match is None or match.group(1) in outputs:
            raise _AdapterFailure
        outputs[match.group(1)] = _read_regular_bytes(path)
    if set(outputs) != {"visits", "patients"}:
        raise _AdapterFailure
    return outputs


def _write_exclusive(
    root_descriptor: int,
    parts: tuple[str, ...],
    content: bytes,
) -> tuple[int, int]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    parent_descriptor = _open_parent_directory(root_descriptor, parts)
    try:
        descriptor = os.open(parts[-1], flags, 0o600, dir_fd=parent_descriptor)
        metadata = os.fstat(descriptor)
        identity = metadata.st_dev, metadata.st_ino
        try:
            try:
                with os.fdopen(descriptor, "wb", closefd=False) as stream:
                    stream.write(content)
            finally:
                os.close(descriptor)
        except Exception:
            _remove_created_from_parent(parent_descriptor, parts[-1], identity)
            raise
        return identity
    finally:
        os.close(parent_descriptor)


def _remove_created_from_parent(
    parent_descriptor: int,
    name: str,
    identity: tuple[int, int],
) -> None:
    try:
        metadata = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if (
            stat.S_ISREG(metadata.st_mode)
            and (metadata.st_dev, metadata.st_ino) == identity
        ):
            os.unlink(name, dir_fd=parent_descriptor)
    except OSError:
        pass


def _remove_created(
    root_descriptor: int,
    parts: tuple[str, ...],
    identity: tuple[int, int],
) -> None:
    try:
        parent_descriptor = _open_parent_directory(root_descriptor, parts)
    except OSError:
        return
    try:
        _remove_created_from_parent(parent_descriptor, parts[-1], identity)
    finally:
        os.close(parent_descriptor)


class SourceMatchedAugmenterOracle:
    """Development-only adapter for the pinned source-matched augmenter CLI."""

    oracle_id = AUGMENTER_ORACLE_ID
    implementation_fingerprint = AUGMENTER_RUNTIME_MANIFEST_SHA256

    def __init__(
        self,
        repository_root: Path | None = None,
        *,
        timeout_seconds: float = 300.0,
    ) -> None:
        if repository_root is not None and not isinstance(repository_root, Path):
            raise TypeError("repository_root must be a Path")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be finite and positive")
        self._repository_root = (
            repository_root
            if repository_root is not None
            else Path(__file__).resolve().parents[2]
        )
        self.timeout_seconds = float(timeout_seconds)

    def derive(
        self,
        package_root: Path,
        descriptor: dict[str, Any],
    ) -> DerivationResult:
        failed = False
        try:
            return self._derive(package_root, descriptor)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:  # noqa: BLE001 - replace the entire private failure chain
            failed = True
        del self, package_root, descriptor
        if failed:
            _unavailable()
        raise AssertionError("unreachable")

    def _derive(
        self,
        package_root: Path,
        descriptor: dict[str, Any],
    ) -> DerivationResult:
        failed = False
        try:
            verify_source_matched_runtime(self._repository_root)
            if not isinstance(package_root, Path):
                raise _AdapterFailure
            package_root = Path(os.path.abspath(package_root))
            package_descriptor, package_identity = _open_package_root(package_root)
            try:
                visits_parts = _safe_output_parts(descriptor, "visits_augmented")
                patients_parts = _safe_output_parts(descriptor, "patients_augmented")
                if visits_parts == patients_parts:
                    raise _AdapterFailure
                _require_package_identity(package_root, package_identity)
                _require_output_absent(package_descriptor, visits_parts)
                _require_output_absent(package_descriptor, patients_parts)

                entries = _verify_manifest(self._repository_root)
                with tempfile.TemporaryDirectory(
                    prefix="ppoc-augmenter-oracle-"
                ) as temporary:
                    temporary_root = Path(temporary)
                    runtime_root = temporary_root / "runtime"
                    output_root = temporary_root / "outputs"
                    _snapshot_runtime(self._repository_root, runtime_root, entries)
                    output_root.mkdir(mode=0o700)
                    command = [
                        sys.executable,
                        "-E",
                        "-s",
                        str(runtime_root / "scripts" / "augment.py"),
                        str(package_root),
                        "--output_dir",
                        str(output_root),
                        "--output_format",
                        "csv",
                    ]
                    completed = subprocess.run(
                        command,
                        cwd=runtime_root,
                        shell=False,
                        check=False,
                        capture_output=True,
                        timeout=self.timeout_seconds,
                    )
                    if completed.returncode != 0:
                        raise _AdapterFailure
                    outputs = _validated_output_bytes(output_root)

                    _require_package_identity(package_root, package_identity)
                    _require_output_absent(package_descriptor, visits_parts)
                    _require_output_absent(package_descriptor, patients_parts)
                    created: list[tuple[tuple[str, ...], tuple[int, int]]] = []
                    try:
                        created.append(
                            (
                                visits_parts,
                                _write_exclusive(
                                    package_descriptor,
                                    visits_parts,
                                    outputs["visits"],
                                ),
                            )
                        )
                        created.append(
                            (
                                patients_parts,
                                _write_exclusive(
                                    package_descriptor,
                                    patients_parts,
                                    outputs["patients"],
                                ),
                            )
                        )
                    except Exception:
                        for parts, identity in reversed(created):
                            _remove_created(package_descriptor, parts, identity)
                        raise
            finally:
                os.close(package_descriptor)

            return DerivationResult(
                oracle_id=self.oracle_id,
                implementation_fingerprint=self.implementation_fingerprint,
                test_only=True,
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:  # noqa: BLE001 - redact every implementation-boundary failure
            failed = True
        if failed:
            _unavailable()
        raise AssertionError("unreachable")

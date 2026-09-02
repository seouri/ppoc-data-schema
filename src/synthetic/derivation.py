from __future__ import annotations

import csv
import hashlib
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from synthetic.schema_contract import resource_spec, validate_resource_paths


class DerivationUnavailable(RuntimeError):
    """Raised when authoritative augmented-output derivation is unavailable."""


@dataclass(frozen=True)
class DerivationResult:
    oracle_id: str
    implementation_fingerprint: str = ""
    test_only: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.implementation_fingerprint, str) or re.fullmatch(
            r"[0-9a-f]{64}", self.implementation_fingerprint
        ) is None:
            raise ValueError("implementation_fingerprint must be lowercase SHA-256 hex")
        if not isinstance(self.test_only, bool):
            raise TypeError("test_only must be a boolean")


class DerivationOracle(Protocol):
    oracle_id: str

    def derive(
        self, package_root: Path, descriptor: dict[str, Any]
    ) -> DerivationResult: ...


def require_augmented_outputs(
    package_root: Path,
    descriptor: dict[str, Any],
    *,
    oracle_id: str,
) -> DerivationResult:
    """Verify both descriptor-named augmented outputs from a pinned oracle.

    This check does not derive or validate clinical content.  It only proves
    that the authoritative derivation boundary supplied both required files.
    """
    if not isinstance(oracle_id, str) or not oracle_id.strip():
        raise DerivationUnavailable("authoritative derivation oracle is not configured")

    try:
        validate_resource_paths(descriptor, package_root)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise DerivationUnavailable("unsafe augmented output path") from exc

    for name in ("patients_augmented", "visits_augmented"):
        try:
            output_path = package_root / resource_spec(descriptor, name)["path"]
        except (KeyError, TypeError, ValueError) as exc:
            raise DerivationUnavailable(
                f"descriptor does not name required {name} output"
            ) from exc
        try:
            mode = output_path.lstat().st_mode
        except OSError as exc:
            raise DerivationUnavailable(f"missing {name} output from {oracle_id}") from exc
        if not stat.S_ISREG(mode):
            raise DerivationUnavailable(f"missing {name} output from {oracle_id}")
        resource = resource_spec(descriptor, name)
        expected_header = [field["name"] for field in resource["schema"]["fields"]]
        dialect = resource.get("dialect", {})
        try:
            with output_path.open(encoding=resource.get("encoding", "utf-8"), newline="") as handle:
                reader = csv.reader(
                    handle,
                    delimiter=dialect.get("delimiter", ","),
                    quotechar=dialect.get("quoteChar", '"'),
                    doublequote=dialect.get("doubleQuote", True),
                    strict=True,
                )
                if next(reader, None) != expected_header:
                    raise DerivationUnavailable(f"{name} output header does not match descriptor")
        except DerivationUnavailable:
            raise
        except (LookupError, OSError, TypeError, UnicodeError, ValueError, csv.Error) as exc:
            raise DerivationUnavailable(f"unreadable {name} output from {oracle_id}") from exc

    return DerivationResult(
        oracle_id=oracle_id,
        implementation_fingerprint=hashlib.sha256(oracle_id.encode()).hexdigest(),
    )

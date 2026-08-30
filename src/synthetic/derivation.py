from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from synthetic.schema_contract import resource_spec


class DerivationUnavailable(RuntimeError):
    """Raised when authoritative augmented-output derivation is unavailable."""


@dataclass(frozen=True)
class DerivationResult:
    oracle_id: str
    implementation_fingerprint: str = ""
    test_only: bool = False


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
    if not oracle_id or not oracle_id.strip():
        raise DerivationUnavailable("authoritative derivation oracle is not configured")

    for name in ("patients_augmented", "visits_augmented"):
        try:
            output_path = package_root / resource_spec(descriptor, name)["path"]
        except (KeyError, TypeError) as exc:
            raise DerivationUnavailable(
                f"descriptor does not name required {name} output"
            ) from exc
        if not output_path.is_file():
            raise DerivationUnavailable(f"missing {name} output from {oracle_id}")

    return DerivationResult(oracle_id=oracle_id)

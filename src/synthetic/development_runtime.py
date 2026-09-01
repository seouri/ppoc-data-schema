"""Frozen development-only binding for the pinned CDC augmenter runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from synthetic.augmenter_oracle import (
    AUGMENTER_ORACLE_ID,
    AUGMENTER_RUNTIME_MANIFEST_SHA256,
    UV_LOCK_SHA256,
    SourceMatchedAugmenterOracle,
    verify_source_matched_runtime,
)
from synthetic.cdc_reference import CdcGrowthReference
from synthetic.derivation_binding import (
    REQUIRED_GOLDEN_CATEGORIES,
    DerivationBinding,
)
from synthetic.schema_contract import EXPECTED_SCHEMA_FINGERPRINT

_REFERENCE_ID = "cdc-lms-reference-v1"
_REFERENCE_VERSION = "cdc-lms-mapping-v1"
_BINDING_ID = "development-augmenter-v1"
_SOURCE_REVISION = "augment-runtime-v1"
_SOURCE_KIND = "authoritative_implementation"
_RUNTIME_MISMATCH = "development runtime identities are inconsistent"


@dataclass(frozen=True)
class DevelopmentRuntime:
    """Reference, oracle, and aggregate-only test binding for development."""

    reference: CdcGrowthReference
    derivation_oracle: SourceMatchedAugmenterOracle
    derivation_binding: DerivationBinding
    dependency_fingerprint: str

    def __post_init__(self) -> None:
        try:
            standard = self.derivation_binding.reference_standard
            oracle = self.derivation_binding.oracle
            matches = (
                isinstance(self.reference, CdcGrowthReference)
                and isinstance(self.derivation_oracle, SourceMatchedAugmenterOracle)
                and isinstance(self.derivation_binding, DerivationBinding)
                and self.dependency_fingerprint == UV_LOCK_SHA256
                and self.reference.reference_id == _REFERENCE_ID
                and standard.standard_id == self.reference.reference_id
                and standard.standard_fingerprint == self.reference.source_sha256
                and standard.version == _REFERENCE_VERSION
                and self.derivation_oracle.oracle_id == AUGMENTER_ORACLE_ID
                and oracle.oracle_id == self.derivation_oracle.oracle_id
                and oracle.implementation_fingerprint
                == self.derivation_oracle.implementation_fingerprint
                and oracle.implementation_fingerprint
                == AUGMENTER_RUNTIME_MANIFEST_SHA256
                and oracle.source_revision == _SOURCE_REVISION
                and oracle.source_kind == _SOURCE_KIND
                and oracle.dependency_fingerprint == self.dependency_fingerprint
            )
        except Exception:  # noqa: BLE001 - expose no implementation details at this boundary.
            matches = False
        if not matches:
            raise ValueError(_RUNTIME_MISMATCH)


def build_development_runtime(repository_root: Path) -> DevelopmentRuntime:
    """Build the test-only runtime from the verified checked-in closure."""
    verify_source_matched_runtime(repository_root)
    reference = CdcGrowthReference.from_repository(repository_root)
    oracle = SourceMatchedAugmenterOracle(repository_root)
    binding = DerivationBinding.from_mapping(
        {
            "binding_version": "derivation-binding-v1",
            "binding_id": _BINDING_ID,
            "schema_fingerprint": EXPECTED_SCHEMA_FINGERPRINT,
            "oracle": {
                "oracle_id": AUGMENTER_ORACLE_ID,
                "implementation_fingerprint": AUGMENTER_RUNTIME_MANIFEST_SHA256,
                "source_revision": _SOURCE_REVISION,
                "dependency_fingerprint": UV_LOCK_SHA256,
                "source_kind": _SOURCE_KIND,
            },
            "reference_standard": {
                "standard_id": _REFERENCE_ID,
                "standard_fingerprint": reference.source_sha256,
                "version": _REFERENCE_VERSION,
            },
            "golden_evidence": {
                "manifest_id": None,
                "manifest_fingerprint": None,
                "parity_contract": None,
                "parity_report_id": None,
                "parity_report_fingerprint": None,
                "parity_status": "UNEVALUABLE",
                "candidate_implementation_fingerprint": None,
                "reference_implementation_fingerprint": None,
                "parity_schema_fingerprint": None,
                "covered_categories": list(REQUIRED_GOLDEN_CATEGORIES),
                "bidirectional_case_count": 0,
                "synthetic_fuzz_case_count": 0,
                "fuzz_corpus_fingerprint": None,
            },
            "review": {
                "review_id": None,
                "review_fingerprint": None,
                "reviewed_at": None,
                "reviewer_role": None,
                "status": "PENDING",
            },
            "test_only": True,
        }
    )
    return DevelopmentRuntime(reference, oracle, binding, UV_LOCK_SHA256)

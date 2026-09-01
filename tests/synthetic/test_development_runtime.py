from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from synthetic.augmenter_oracle import (
    AUGMENTER_ORACLE_ID,
    AUGMENTER_RUNTIME_MANIFEST_SHA256,
    UV_LOCK_SHA256,
    SourceMatchedAugmenterOracle,
    verify_source_matched_runtime,
)
from synthetic.derivation import DerivationResult, DerivationUnavailable
from synthetic.derivation_binding import (
    REQUIRED_GOLDEN_CATEGORIES,
    BoundDerivationOracle,
    DerivationBindingOracle,
    DerivationBindingStatus,
    DerivationBindingUnavailable,
    DerivationReferenceStandard,
    validate_derivation_binding,
)
from synthetic.development_runtime import DevelopmentRuntime, build_development_runtime
from synthetic.schema_contract import EXPECTED_SCHEMA_FINGERPRINT

ROOT = Path(__file__).resolve().parents[2]
UNAVAILABLE_MESSAGE = "source-matched augmenter unavailable"


def _copied_runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    manifest = json.loads(
        (ROOT / "data" / "augment-runtime-manifest.json").read_text(encoding="utf-8")
    )
    for entry in manifest["files"]:
        relative = Path(entry["path"])
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    manifest_destination = root / "data" / "augment-runtime-manifest.json"
    manifest_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "data" / "augment-runtime-manifest.json", manifest_destination)
    shutil.copy2(ROOT / "uv.lock", root / "uv.lock")
    return root


def _assert_unavailable(root: Path) -> None:
    with pytest.raises(DerivationUnavailable) as caught:
        verify_source_matched_runtime(root)

    assert str(caught.value) == UNAVAILABLE_MESSAGE
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert str(root) not in str(caught.value)
    assert "subprocess" not in str(caught.value)


def test_source_matched_runtime_verification_accepts_checked_in_root() -> None:
    """Catches a valid locked source closure rejected by the public gate."""
    assert verify_source_matched_runtime(ROOT) is None


@pytest.mark.parametrize(
    "mutation",
    (
        "lock-drift",
        "lock-symlink",
        "missing-lock",
        "manifest-drift",
        "runtime-drift",
        "runtime-symlink",
    ),
)
def test_source_matched_runtime_verification_redacts_closure_drift(
    tmp_path: Path,
    mutation: str,
) -> None:
    """Catches lock, manifest, runtime, or symlink drift bypassing the gate."""
    root = _copied_runtime_root(tmp_path)
    if mutation == "lock-drift":
        lock = root / "uv.lock"
        lock.write_bytes(lock.read_bytes() + b"\n")
    elif mutation == "lock-symlink":
        lock = root / "uv.lock"
        lock.unlink()
        lock.symlink_to(ROOT / "uv.lock")
    elif mutation == "missing-lock":
        (root / "uv.lock").unlink()
    elif mutation == "manifest-drift":
        manifest = root / "data" / "augment-runtime-manifest.json"
        manifest.write_bytes(manifest.read_bytes() + b"\n")
    elif mutation == "runtime-drift":
        runtime = root / "scripts" / "augment.py"
        runtime.write_bytes(runtime.read_bytes() + b"\n")
    else:
        runtime = root / "scripts" / "augment.py"
        runtime.unlink()
        runtime.symlink_to(ROOT / "scripts" / "augment.py")

    _assert_unavailable(root)


def test_direct_oracle_redacts_lock_drift(tmp_path: Path) -> None:
    """Catches direct derivation bypassing the locked runtime verifier."""
    root = _copied_runtime_root(tmp_path)
    lock = root / "uv.lock"
    lock.write_bytes(lock.read_bytes() + b"\n")

    with pytest.raises(DerivationUnavailable) as caught:
        SourceMatchedAugmenterOracle(root).derive(ROOT, {})

    assert str(caught.value) == UNAVAILABLE_MESSAGE
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert str(root) not in str(caught.value)
    assert "subprocess" not in str(caught.value)


def test_development_runtime_binds_reference_and_test_only_oracle() -> None:
    """Catches a factory that composes identities other than the locked runtime."""
    runtime = build_development_runtime(ROOT)

    assert runtime.reference.reference_id == "cdc-lms-reference-v1"
    assert runtime.reference.source_sha256 == runtime.derivation_binding.reference_standard.standard_fingerprint
    assert runtime.derivation_oracle.oracle_id == "augmenter-cli-v1"
    assert runtime.derivation_binding.binding_id == "development-augmenter-v1"
    assert runtime.derivation_binding.test_only is True
    assert runtime.derivation_binding.oracle.source_kind == "authoritative_implementation"
    assert runtime.derivation_binding.review.status == "PENDING"
    assert runtime.derivation_binding.golden_evidence.bidirectional_case_count == 0
    assert runtime.derivation_binding.golden_evidence.synthetic_fuzz_case_count == 0
    assert runtime.derivation_binding.schema_fingerprint == EXPECTED_SCHEMA_FINGERPRINT
    assert runtime.derivation_binding.golden_evidence.covered_categories == REQUIRED_GOLDEN_CATEGORIES
    assert runtime.dependency_fingerprint == hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest()
    assert runtime.dependency_fingerprint == UV_LOCK_SHA256
    assert runtime.derivation_binding.oracle.implementation_fingerprint == AUGMENTER_RUNTIME_MANIFEST_SHA256
    assert runtime.derivation_binding.oracle.oracle_id == AUGMENTER_ORACLE_ID
    assert validate_derivation_binding(
        runtime.derivation_binding,
        expected_schema_fingerprint=EXPECTED_SCHEMA_FINGERPRINT,
    ).status is not DerivationBindingStatus.FAIL


@pytest.mark.parametrize(
    "mismatch",
    (
        "reference",
        "reference-id",
        "reference-version",
        "oracle-id",
        "oracle-fingerprint",
        "oracle-dependency",
        "oracle-revision",
        "oracle-kind",
        "runtime-dependency",
        "binding-id",
        "schema",
        "test-only",
    ),
)
def test_development_runtime_rejects_mismatched_composition_before_derivation(
    mismatch: str,
) -> None:
    """Catches reference or oracle identity drift entering a composed runtime."""
    runtime = build_development_runtime(ROOT)
    binding = runtime.derivation_binding
    if mismatch == "reference":
        binding = replace(
            binding,
            reference_standard=DerivationReferenceStandard(
                standard_id="cdc-lms-reference-v1",
                standard_fingerprint="1" * 64,
                version="cdc-lms-mapping-v1",
            ),
        )
    elif mismatch == "reference-id":
        binding = replace(
            binding,
            reference_standard=DerivationReferenceStandard(
                standard_id="different-standard-v1",
                standard_fingerprint=runtime.reference.source_sha256,
                version="cdc-lms-mapping-v1",
            ),
        )
    elif mismatch == "reference-version":
        binding = replace(
            binding,
            reference_standard=DerivationReferenceStandard(
                standard_id="cdc-lms-reference-v1",
                standard_fingerprint=runtime.reference.source_sha256,
                version="different-mapping-v1",
            ),
        )
    elif mismatch == "oracle-id":
        binding = replace(
            binding,
            oracle=DerivationBindingOracle(
                oracle_id="different-oracle-v1",
                implementation_fingerprint=AUGMENTER_RUNTIME_MANIFEST_SHA256,
                source_revision="augment-runtime-v1",
                dependency_fingerprint=UV_LOCK_SHA256,
                source_kind="authoritative_implementation",
            ),
        )
    elif mismatch == "oracle-fingerprint":
        binding = replace(
            binding,
            oracle=DerivationBindingOracle(
                oracle_id=AUGMENTER_ORACLE_ID,
                implementation_fingerprint="2" * 64,
                source_revision="augment-runtime-v1",
                dependency_fingerprint=UV_LOCK_SHA256,
                source_kind="authoritative_implementation",
            ),
        )
    elif mismatch == "oracle-dependency":
        binding = replace(
            binding,
            oracle=DerivationBindingOracle(
                oracle_id=AUGMENTER_ORACLE_ID,
                implementation_fingerprint=AUGMENTER_RUNTIME_MANIFEST_SHA256,
                source_revision="augment-runtime-v1",
                dependency_fingerprint="4" * 64,
                source_kind="authoritative_implementation",
            ),
        )
    elif mismatch == "oracle-revision":
        binding = replace(
            binding,
            oracle=DerivationBindingOracle(
                oracle_id=AUGMENTER_ORACLE_ID,
                implementation_fingerprint=AUGMENTER_RUNTIME_MANIFEST_SHA256,
                source_revision="different-runtime-v1",
                dependency_fingerprint=UV_LOCK_SHA256,
                source_kind="authoritative_implementation",
            ),
        )
    elif mismatch == "oracle-kind":
        binding = replace(
            binding,
            oracle=DerivationBindingOracle(
                oracle_id=AUGMENTER_ORACLE_ID,
                implementation_fingerprint=AUGMENTER_RUNTIME_MANIFEST_SHA256,
                source_revision="augment-runtime-v1",
                dependency_fingerprint=UV_LOCK_SHA256,
                source_kind="approved_parity_harness",
            ),
        )
    elif mismatch == "binding-id":
        binding = replace(binding, binding_id="different-binding-v1")
    elif mismatch == "schema":
        binding = replace(binding, schema_fingerprint="4" * 64)
    elif mismatch == "test-only":
        binding = replace(binding, test_only=False)

    with pytest.raises(ValueError):
        DevelopmentRuntime(
            runtime.reference,
            runtime.derivation_oracle,
            binding,
            "5" * 64 if mismatch == "runtime-dependency" else runtime.dependency_fingerprint,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("manifest_id", "golden-evidence-v1"),
        ("manifest_fingerprint", "4" * 64),
        ("parity_contract", "parity-contract-v1"),
        ("parity_report_id", "parity-report-v1"),
        ("parity_report_fingerprint", "4" * 64),
        ("parity_status", "PASS"),
        ("candidate_implementation_fingerprint", "4" * 64),
        ("reference_implementation_fingerprint", "4" * 64),
        ("parity_schema_fingerprint", "4" * 64),
        ("covered_categories", tuple(reversed(REQUIRED_GOLDEN_CATEGORIES))),
        ("bidirectional_case_count", 1),
        ("synthetic_fuzz_case_count", 1),
        ("fuzz_corpus_fingerprint", "4" * 64),
    ),
)
def test_development_runtime_rejects_every_golden_evidence_substitution(
    field: str,
    value: object,
) -> None:
    """Catches a valid evidence field changing the frozen UNEVALUABLE contract."""
    runtime = build_development_runtime(ROOT)
    binding = replace(
        runtime.derivation_binding,
        golden_evidence=replace(runtime.derivation_binding.golden_evidence, **{field: value}),
    )

    with pytest.raises(ValueError):
        DevelopmentRuntime(
            runtime.reference,
            runtime.derivation_oracle,
            binding,
            runtime.dependency_fingerprint,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("review_id", "review-v1"),
        ("review_fingerprint", "4" * 64),
        ("reviewed_at", "2026-09-01T00:00:00Z"),
        ("reviewer_role", "data-custodian"),
        ("status", "APPROVED"),
    ),
)
def test_development_runtime_rejects_every_review_substitution(
    field: str,
    value: object,
) -> None:
    """Catches a valid review field changing the frozen pending-review contract."""
    runtime = build_development_runtime(ROOT)
    binding = replace(
        runtime.derivation_binding,
        review=replace(runtime.derivation_binding.review, **{field: value}),
    )

    with pytest.raises(ValueError):
        DevelopmentRuntime(
            runtime.reference,
            runtime.derivation_oracle,
            binding,
            runtime.dependency_fingerprint,
        )


def test_bound_oracle_rejects_mismatched_derivation_result() -> None:
    """Catches a derivation result that drifts from an otherwise valid binding."""
    runtime = build_development_runtime(ROOT)

    class WrongResultOracle:
        oracle_id = AUGMENTER_ORACLE_ID

        def derive(self, package_root: Path, descriptor: dict[str, object]) -> DerivationResult:
            del package_root, descriptor
            return DerivationResult(AUGMENTER_ORACLE_ID, "3" * 64, True)

    bound = BoundDerivationOracle(WrongResultOracle(), runtime.derivation_binding)
    with pytest.raises(DerivationBindingUnavailable):
        bound.derive(ROOT, {})

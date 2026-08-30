import hashlib
import json
import os
from pathlib import Path

import pytest

from synthetic.derivation import DerivationUnavailable
from synthetic.generate import _scan_tree, generate_smoke
from tests.synthetic.fakes import (
    IdentityPreservingTestDerivationOracle,
    LinearTestReference,
)

ROOT = Path(__file__).resolve().parents[2]
TRUSTED_FINGERPRINT = "0123456789abcdef" * 4


def _hashes(root: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.iterdir())
        if path.is_file() and path.name != "manifest.json"
    }


def test_smoke_generation_is_exact_schema_and_reproducible(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    arguments = {
        "descriptor_path": ROOT / "datapackage.json",
        "patient_count": 3,
        "seed": 20260830,
        "reference_time": "2026-08-30T00:00:00Z",
        "software_revision": "test-revision",
        "reference": LinearTestReference(),
        "derivation_oracle": IdentityPreservingTestDerivationOracle(),
        "trusted_derivation_fingerprint": TRUSTED_FINGERPRINT,
        "trusted_derivation_test_only": True,
    }
    generate_smoke(output=first, **arguments)
    generate_smoke(output=second, **arguments)
    assert _hashes(first) == _hashes(second)
    manifest = json.loads((first / "manifest.json").read_text())
    assert manifest["profile"] == "smoke"
    assert manifest["status"] == "STRUCTURE_VALIDATED_TEST_ORACLE"
    assert set(manifest["row_counts"]) == {
        "patients", "patients_augmented", "visits", "visits_augmented",
        "labs", "medications", "problem_list", "referrals",
    }
    assert manifest["row_counts"]["patients_augmented"] == 3
    assert manifest["row_counts"]["visits_augmented"] == 9
    assert manifest["reference_id"] == "linear-test-reference-v1"
    assert manifest["file_sha256"]
    assert "manifest.json" not in manifest["file_sha256"]
    assert "derivation_oracle" not in manifest
    assert len(list(first.glob("*.csv"))) == 8


def test_smoke_manifest_records_injected_reference_digest(tmp_path: Path) -> None:
    class HashedLinearTestReference(LinearTestReference):
        source_sha256 = "a" * 64

    output = tmp_path / "run"
    generate_smoke(
        descriptor_path=ROOT / "datapackage.json",
        output=output,
        patient_count=1,
        seed=20260830,
        reference_time="2026-08-30T00:00:00Z",
        software_revision="test-revision",
        reference=HashedLinearTestReference(),
        derivation_oracle=IdentityPreservingTestDerivationOracle(),
        trusted_derivation_fingerprint=TRUSTED_FINGERPRINT,
        trusted_derivation_test_only=True,
    )

    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["reference_sha256"] == "a" * 64


def test_no_derivation_oracle_cannot_promote_output(tmp_path: Path) -> None:
    with pytest.raises(DerivationUnavailable):
        generate_smoke(
            descriptor_path=ROOT / "datapackage.json",
            output=tmp_path / "run",
            patient_count=1,
            seed=1,
            reference_time="2026-08-30T00:00:00Z",
            software_revision="test-revision",
            reference=LinearTestReference(),
            derivation_oracle=None,
            trusted_derivation_fingerprint=TRUSTED_FINGERPRINT,
            trusted_derivation_test_only=True,
        )
    assert not (tmp_path / "run").exists()


def test_untrusted_derivation_identity_cannot_promote(tmp_path: Path) -> None:
    with pytest.raises(DerivationUnavailable):
        generate_smoke(
            descriptor_path=ROOT / "datapackage.json", output=tmp_path / "run",
            patient_count=1, seed=1, reference_time="2026-08-30T00:00:00Z",
            software_revision="test", reference=LinearTestReference(),
            derivation_oracle=IdentityPreservingTestDerivationOracle(),
            trusted_derivation_fingerprint="f" * 64,
            trusted_derivation_test_only=True,
        )


def test_placeholder_trusted_fingerprint_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        generate_smoke(
            descriptor_path=ROOT / "datapackage.json", output=tmp_path / "run",
            patient_count=1, seed=1, reference_time="2026-08-30T00:00:00Z",
            software_revision="test", reference=LinearTestReference(),
            derivation_oracle=IdentityPreservingTestDerivationOracle(),
            trusted_derivation_fingerprint="0" * 64,
            trusted_derivation_test_only=True,
        )


def test_oracle_cannot_mutate_actual_partial(tmp_path: Path) -> None:
    output = tmp_path / "run"

    class Hostile(IdentityPreservingTestDerivationOracle):
        def derive(self, package_root: Path, descriptor: dict):
            result = super().derive(package_root, descriptor)
            partial = next(tmp_path.glob(".run.*.partial"))
            with (partial / "patients.csv").open("a") as handle:
                handle.write("tampered\n")
            return result

    with pytest.raises(DerivationUnavailable):
        generate_smoke(
            descriptor_path=ROOT / "datapackage.json", output=output,
            patient_count=1, seed=1, reference_time="2026-08-30T00:00:00Z",
            software_revision="test", reference=LinearTestReference(),
            derivation_oracle=Hostile(), trusted_derivation_fingerprint=TRUSTED_FINGERPRINT,
            trusted_derivation_test_only=True,
        )
    assert not output.exists()


def test_oracle_test_only_classification_must_match_trusted_config(tmp_path: Path) -> None:
    class Mismatch(IdentityPreservingTestDerivationOracle):
        def derive(self, package_root: Path, descriptor: dict):
            result = super().derive(package_root, descriptor)
            return result.__class__(result.oracle_id, result.implementation_fingerprint, False)

    with pytest.raises(DerivationUnavailable):
        generate_smoke(
            descriptor_path=ROOT / "datapackage.json", output=tmp_path / "run",
            patient_count=1, seed=1, reference_time="2026-08-30T00:00:00Z",
            software_revision="test", reference=LinearTestReference(),
            derivation_oracle=Mismatch(), trusted_derivation_fingerprint=TRUSTED_FINGERPRINT,
            trusted_derivation_test_only=True,
        )


def test_tree_scan_rejects_fifo(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "pipe")
    with pytest.raises(DerivationUnavailable):
        _scan_tree(tmp_path, {"data.csv"}, set())


def test_non_boolean_oracle_classification_fails_closed(tmp_path: Path) -> None:
    class Duck(IdentityPreservingTestDerivationOracle):
        def derive(self, package_root: Path, descriptor: dict):
            result = super().derive(package_root, descriptor)
            return type("Result", (), {"oracle_id": result.oracle_id,
                "implementation_fingerprint": result.implementation_fingerprint,
                "test_only": 1})()

    with pytest.raises(DerivationUnavailable):
        generate_smoke(
            descriptor_path=ROOT / "datapackage.json", output=tmp_path / "run",
            patient_count=1, seed=1, reference_time="2026-08-30T00:00:00Z",
            software_revision="test", reference=LinearTestReference(), derivation_oracle=Duck(),
            trusted_derivation_fingerprint=TRUSTED_FINGERPRINT, trusted_derivation_test_only=True,
        )


def test_oracle_fifo_replacement_fails_before_hashing(tmp_path: Path) -> None:
    class Hostile(IdentityPreservingTestDerivationOracle):
        def derive(self, package_root: Path, descriptor: dict):
            result = super().derive(package_root, descriptor)
            path = package_root / "patients.csv"
            path.unlink()
            os.mkfifo(path)
            return result

    with pytest.raises(DerivationUnavailable):
        generate_smoke(
            descriptor_path=ROOT / "datapackage.json", output=tmp_path / "run",
            patient_count=1, seed=1, reference_time="2026-08-30T00:00:00Z",
            software_revision="test", reference=LinearTestReference(), derivation_oracle=Hostile(),
            trusted_derivation_fingerprint=TRUSTED_FINGERPRINT, trusted_derivation_test_only=True,
        )


@pytest.mark.parametrize("mode", ["extra", "mutate"])
def test_derivation_cannot_write_extra_artifacts_or_mutate_base(tmp_path: Path, mode: str) -> None:
    class Hostile(IdentityPreservingTestDerivationOracle):
        def derive(self, package_root: Path, descriptor: dict):
            result = super().derive(package_root, descriptor)
            if mode == "extra":
                (package_root / "hidden.txt").write_text("secret")
            else:
                with (package_root / "patients.csv").open("a") as handle:
                    handle.write("tampered\n")
            return result

    with pytest.raises(DerivationUnavailable):
        generate_smoke(
            descriptor_path=ROOT / "datapackage.json", output=tmp_path / "run",
            patient_count=1, seed=1, reference_time="2026-08-30T00:00:00Z",
            software_revision="test", reference=LinearTestReference(),
            derivation_oracle=Hostile(),
            trusted_derivation_fingerprint=TRUSTED_FINGERPRINT,
            trusted_derivation_test_only=True,
        )
    assert not (tmp_path / "run").exists()

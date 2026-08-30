import hashlib
import json
from pathlib import Path

import pytest

from synthetic.derivation import DerivationUnavailable
from synthetic.generate import generate_smoke
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

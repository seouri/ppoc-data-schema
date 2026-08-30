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
        )
    assert not (tmp_path / "run").exists()

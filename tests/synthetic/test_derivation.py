from pathlib import Path

import pytest

from synthetic.derivation import (
    DerivationResult,
    DerivationUnavailable,
    require_augmented_outputs,
)
from synthetic.schema_contract import load_descriptor

ROOT = Path(__file__).resolve().parents[2]


def test_missing_oracle_is_not_a_success_state() -> None:
    with pytest.raises(DerivationUnavailable, match="authoritative derivation"):
        raise DerivationUnavailable("authoritative derivation oracle is not configured")


def test_unconfigured_oracle_is_rejected(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    with pytest.raises(DerivationUnavailable, match="authoritative derivation"):
        require_augmented_outputs(tmp_path, descriptor, oracle_id="")


def test_requires_both_descriptor_named_augmented_outputs(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    (tmp_path / "patients_augmented.csv").write_text("patient_id\n", encoding="utf-8")
    with pytest.raises(DerivationUnavailable, match="visits_augmented"):
        require_augmented_outputs(tmp_path, descriptor, oracle_id="fake-v1")


def test_returns_pinned_identity_when_both_outputs_exist(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    for name in ("patients_augmented", "visits_augmented"):
        resource = next(
            item for item in descriptor["resources"] if item["name"] == name
        )
        (tmp_path / resource["path"]).write_text(
            "header\n", encoding=resource["encoding"]
        )
    assert require_augmented_outputs(
        tmp_path, descriptor, oracle_id="fake-v1"
    ) == DerivationResult("fake-v1")

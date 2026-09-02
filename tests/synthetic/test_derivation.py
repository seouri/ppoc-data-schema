import csv
import hashlib
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
    resource = next(item for item in descriptor["resources"] if item["name"] == "patients_augmented")
    fields = [field["name"] for field in resource["schema"]["fields"]]
    with (tmp_path / resource["path"]).open("w", encoding=resource["encoding"], newline="") as handle:
        csv.writer(handle).writerow(fields)
    with pytest.raises(DerivationUnavailable, match="visits_augmented"):
        require_augmented_outputs(tmp_path, descriptor, oracle_id="fake-v1")


def test_returns_pinned_identity_when_both_outputs_exist(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    for name in ("patients_augmented", "visits_augmented"):
        resource = next(
            item for item in descriptor["resources"] if item["name"] == name
        )
        fields = [field["name"] for field in resource["schema"]["fields"]]
        with (tmp_path / resource["path"]).open(
            "w", encoding=resource["encoding"], newline=""
        ) as handle:
            csv.writer(handle).writerow(fields)
    assert require_augmented_outputs(
        tmp_path, descriptor, oracle_id="fake-v1"
    ) == DerivationResult("fake-v1", hashlib.sha256(b"fake-v1").hexdigest())


def test_rejects_symlinked_augmented_output(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    for name in ("patients_augmented", "visits_augmented"):
        resource = next(item for item in descriptor["resources"] if item["name"] == name)
        fields = [field["name"] for field in resource["schema"]["fields"]]
        target = tmp_path / f"real-{name}.csv"
        with target.open("w", encoding=resource["encoding"], newline="") as handle:
            csv.writer(handle).writerow(fields)
        (tmp_path / resource["path"]).symlink_to(target.name)
    with pytest.raises(DerivationUnavailable, match="unsafe|symlink"):
        require_augmented_outputs(tmp_path, descriptor, oracle_id="fake-v1")


def test_rejects_wrong_augmented_header(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    for name in ("patients_augmented", "visits_augmented"):
        resource = next(item for item in descriptor["resources"] if item["name"] == name)
        (tmp_path / resource["path"]).write_text("wrong\n", encoding=resource["encoding"])
    with pytest.raises(DerivationUnavailable, match="header"):
        require_augmented_outputs(tmp_path, descriptor, oracle_id="fake-v1")


@pytest.mark.parametrize(
    "malformation",
    ("fields_none", "schema_none", "dialect_none", "resource_list", "field_name_missing"),
)
def test_rejects_malformed_augmented_descriptor_shapes(
    tmp_path: Path, malformation: str
) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    for name in ("patients_augmented", "visits_augmented"):
        resource = next(item for item in descriptor["resources"] if item["name"] == name)
        fields = [field["name"] for field in resource["schema"]["fields"]]
        with (tmp_path / resource["path"]).open(
            "w", encoding=resource["encoding"], newline=""
        ) as handle:
            csv.writer(handle).writerow(fields)

    augmented = next(
        index for index, item in enumerate(descriptor["resources"])
        if item["name"] == "patients_augmented"
    )
    if malformation == "resource_list":
        descriptor["resources"][augmented] = []
    else:
        resource = descriptor["resources"][augmented]
        if malformation == "fields_none":
            resource["schema"]["fields"] = None
        elif malformation == "schema_none":
            resource["schema"] = None
        elif malformation == "dialect_none":
            resource["dialect"] = None
        else:
            del resource["schema"]["fields"][0]["name"]

    with pytest.raises(DerivationUnavailable, match="descriptor|unsafe|unreadable"):
        require_augmented_outputs(tmp_path, descriptor, oracle_id="fake-v1")

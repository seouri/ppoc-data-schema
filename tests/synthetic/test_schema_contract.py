from pathlib import Path

import pytest

from synthetic.schema_contract import (
    field_names,
    load_descriptor,
    resource_spec,
    schema_fingerprint,
)

ROOT = Path(__file__).resolve().parents[2]


def test_checked_in_schema_fingerprint_is_stable() -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    assert schema_fingerprint(descriptor) == (
        "795724ec4838df8afa9c09b7c059fa76f644d7f8fb6dcc8ce808da203c2f8597"
    )


def test_contract_has_exact_resource_paths_and_field_counts() -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    expected = {
        "patients": ("patients.csv", 11),
        "patients_augmented": ("patients_augmented.csv", 87),
        "visits": ("visits.csv", 43),
        "visits_augmented": ("visits_augmented-20251209150512.csv", 82),
        "labs": ("labs.csv", 12),
        "medications": ("medications.csv", 8),
        "problem_list": ("problem_list.csv", 5),
        "referrals": ("referrals.csv", 6),
    }
    assert {
        resource["name"]: (resource["path"], len(field_names(descriptor, resource["name"])))
        for resource in descriptor["resources"]
    } == expected


def test_unknown_resource_fails_closed() -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    with pytest.raises(KeyError, match="Unknown resource"):
        resource_spec(descriptor, "unknown")

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from synthetic.models import PatientState
from synthetic.native.counterfactual import (
    CounterfactualValidationStatus,
    InterventionKind,
    generate_counterfactual_pair,
    validate_counterfactual_pair,
    write_truth_manifest,
)
from tests.synthetic.test_counterfactual_validation import _familial_kernel

PATIENT = PatientState("syn-counterfactual-manifest", "F", "F")
SEED = 20260831
INDEX = 9
AGES = (0, 365, 730, 1460, 1825, 2190, 4000)


def _validated_pair():
    pair = generate_counterfactual_pair(
        _familial_kernel(),
        PATIENT,
        AGES,
        SEED,
        INDEX,
        InterventionKind.EARLIER_RECOGNITION,
    )
    report = validate_counterfactual_pair(pair)
    assert report.status is CounterfactualValidationStatus.PASS
    return pair, report


def test_truth_manifest_is_external_canonical_and_contains_hidden_evidence(
    tmp_path: Path,
) -> None:
    pair, report = _validated_pair()
    destination = tmp_path / "counterfactual-truth.json"

    returned = write_truth_manifest(pair, report, destination)

    assert returned == destination
    payload = json.loads(destination.read_bytes())
    assert destination.read_bytes().endswith(b"\n")
    assert payload["manifest_version"] == "counterfactual-truth-v1"
    assert payload["status"] == "PASS"
    assert payload["patient"]["patient_id"] == PATIENT.patient_id
    assert set(payload["worlds"]) == {"baseline", "intervention"}
    assert payload["worlds"]["baseline"]["layer_sha256"]
    assert payload["worlds"]["baseline"]["event_trace"]
    assert payload["stream_identities"]["reused"]
    assert payload["checks"] == report.to_mapping()

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii") + b"\n"
    assert destination.read_bytes() == canonical


def test_truth_manifest_is_deterministic_for_the_same_pair(tmp_path: Path) -> None:
    pair, report = _validated_pair()
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    write_truth_manifest(pair, report, first)
    write_truth_manifest(pair, report, second)

    assert first.read_bytes() == second.read_bytes()


def test_truth_manifest_refuses_an_existing_destination(tmp_path: Path) -> None:
    pair, report = _validated_pair()
    destination = tmp_path / "truth.json"
    write_truth_manifest(pair, report, destination)
    original = destination.read_bytes()

    with pytest.raises(FileExistsError, match="already exists"):
        write_truth_manifest(pair, report, destination)

    assert destination.read_bytes() == original


def test_truth_manifest_rejects_symlink_destination(tmp_path: Path) -> None:
    pair, report = _validated_pair()
    target = tmp_path / "target.json"
    target.write_bytes(b"do not replace")
    destination = tmp_path / "truth.json"
    destination.symlink_to(target)

    with pytest.raises(ValueError, match="regular non-symlink"):
        write_truth_manifest(pair, report, destination)

    assert target.read_bytes() == b"do not replace"


def test_truth_manifest_rejects_symlink_parent(tmp_path: Path) -> None:
    pair, report = _validated_pair()
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    symlink_parent = tmp_path / "linked"
    symlink_parent.symlink_to(real_parent, target_is_directory=True)

    with pytest.raises(ValueError, match="regular non-symlink"):
        write_truth_manifest(pair, report, symlink_parent / "truth.json")


@pytest.mark.parametrize("destination", ["truth.json", Path("a") / ".." / "truth.json"])
def test_truth_manifest_rejects_non_path_or_traversal_destination(
    tmp_path: Path, destination: object
) -> None:
    pair, report = _validated_pair()
    if isinstance(destination, Path):
        destination = tmp_path / destination

    with pytest.raises((TypeError, ValueError)):
        write_truth_manifest(pair, report, destination)  # type: ignore[arg-type]


def test_truth_manifest_is_private_file(tmp_path: Path) -> None:
    pair, report = _validated_pair()
    destination = tmp_path / "truth.json"

    write_truth_manifest(pair, report, destination)

    assert os.stat(destination).st_mode & 0o777 == 0o600

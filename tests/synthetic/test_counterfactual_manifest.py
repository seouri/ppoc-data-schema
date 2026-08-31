from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import synthetic.native.counterfactual as counterfactual_module
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


def test_truth_manifest_rejects_symlink_ancestor(tmp_path: Path) -> None:
    pair, report = _validated_pair()
    real_root = tmp_path / "real-root"
    (real_root / "nested").mkdir(parents=True)
    outer = tmp_path / "outer"
    outer.mkdir()
    linked_ancestor = outer / "linked-root"
    linked_ancestor.symlink_to(real_root, target_is_directory=True)

    with pytest.raises(ValueError, match="regular non-symlink"):
        write_truth_manifest(pair, report, linked_ancestor / "nested" / "truth.json")


def test_truth_manifest_pins_parent_when_ancestor_is_swapped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pair, report = _validated_pair()
    outer = tmp_path / "outer"
    (outer / "nested").mkdir(parents=True)
    attacker = tmp_path / "attacker"
    (attacker / "nested").mkdir(parents=True)
    output = outer / "nested" / "truth.json"
    original_outer = tmp_path / "original-outer"
    swapped = False
    real_open = counterfactual_module.os.open

    def swap_ancestor() -> None:
        nonlocal swapped
        if swapped:
            return
        outer.rename(original_outer)
        outer.symlink_to(attacker, target_is_directory=True)
        swapped = True

    def swapping_open(
        path: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        # A path-based temporary-file implementation is forced through the
        # swapped ancestor before it opens its temporary source.  A secure
        # component walk opens `outer` first, then keeps its descriptor pinned
        # while the same swap occurs.
        if dir_fd is None and outer in Path(path).parents:
            swap_ancestor()
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if dir_fd is not None and path == outer.name:
            swap_ancestor()
        return descriptor

    supported_dir_fd = set(counterfactual_module.os.supports_dir_fd)
    monkeypatch.setattr(counterfactual_module.os, "open", swapping_open)
    monkeypatch.setattr(
        counterfactual_module.os,
        "supports_dir_fd",
        supported_dir_fd | {swapping_open},
    )

    write_truth_manifest(pair, report, output)

    assert (original_outer / "nested" / "truth.json").is_file()
    assert not (attacker / "nested" / "truth.json").exists()


def test_truth_manifest_does_not_publish_through_a_temporary_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pair, report = _validated_pair()
    destination = tmp_path / "truth.json"
    link_calls: list[object] = []

    def unexpected_link(*args: object, **kwargs: object) -> object:
        link_calls.append((args, kwargs))
        raise AssertionError("temporary-source publication must not be used")

    monkeypatch.setattr(counterfactual_module.os, "link", unexpected_link)

    write_truth_manifest(pair, report, destination)

    assert not link_calls
    assert destination.is_file()


@pytest.mark.parametrize("failure", ["write", "fsync"])
def test_truth_manifest_write_failure_removes_partial_and_allows_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    pair, report = _validated_pair()
    destination = tmp_path / "truth.json"

    with monkeypatch.context() as patch:
        if failure == "write":

            def fail_write(*_args: object) -> int:
                raise OSError("injected write failure")

            patch.setattr(counterfactual_module.os, "write", fail_write)
        else:

            def fail_fsync(_descriptor: int) -> None:
                raise OSError("injected fsync failure")

            patch.setattr(counterfactual_module.os, "fsync", fail_fsync)

        with pytest.raises(ValueError, match="could not be written"):
            write_truth_manifest(pair, report, destination)

    assert not destination.exists()
    assert not list(tmp_path.glob(".truth.json.*.partial"))

    write_truth_manifest(pair, report, destination)
    assert destination.is_file()


def test_truth_manifest_verification_does_not_read_or_remove_recreated_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pair, report = _validated_pair()
    destination = tmp_path / "truth.json"
    swapped = False
    real_read = counterfactual_module.os.read

    def swapping_read(descriptor: int, size: int) -> bytes:
        nonlocal swapped
        if not swapped:
            destination.unlink()
            destination.write_bytes(b"attacker replacement")
            swapped = True
        return real_read(descriptor, size)

    monkeypatch.setattr(counterfactual_module.os, "read", swapping_read)

    with pytest.raises(ValueError, match="could not be verified"):
        write_truth_manifest(pair, report, destination)

    assert swapped
    assert destination.read_bytes() == b"attacker replacement"


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

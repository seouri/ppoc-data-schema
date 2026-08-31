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


def test_truth_manifest_fstat_creation_failure_quarantines_child_and_allows_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pair, report = _validated_pair()
    destination = tmp_path / "truth.json"

    def fail_fstat(_descriptor: int) -> os.stat_result:
        raise OSError("injected fstat failure")

    with monkeypatch.context() as patch:
        patch.setattr(counterfactual_module.os, "fstat", fail_fstat)
        with pytest.raises(ValueError, match="could not be created"):
            write_truth_manifest(pair, report, destination)

    assert not destination.exists()
    quarantine = next(tmp_path.glob(".counterfactual-truth-cleanup-*"))
    assert quarantine.is_file()
    assert quarantine.read_bytes() == b""

    write_truth_manifest(pair, report, destination)
    assert destination.is_file()


def test_truth_manifest_quarantine_rename_never_overwrites_existing_child(
    tmp_path: Path,
) -> None:
    source_directory = tmp_path / "source"
    quarantine_directory = tmp_path / "quarantine"
    source_directory.mkdir()
    quarantine_directory.mkdir()
    (source_directory / "truth.json").write_bytes(b"owner")
    (quarantine_directory / "truth.json").write_bytes(b"preexisting")
    source_descriptor = os.open(source_directory, os.O_RDONLY)
    quarantine_descriptor = os.open(quarantine_directory, os.O_RDONLY)
    try:
        with pytest.raises(FileExistsError, match="already exists"):
            counterfactual_module._rename_truth_manifest_child_exclusive(
                "truth.json",
                source_descriptor,
                "truth.json",
                quarantine_descriptor,
            )
    finally:
        os.close(source_descriptor)
        os.close(quarantine_descriptor)

    assert (source_directory / "truth.json").read_bytes() == b"owner"
    assert (quarantine_directory / "truth.json").read_bytes() == b"preexisting"


def test_truth_manifest_cleanup_uses_random_parent_quarantine_entry(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "truth.json"
    destination.write_bytes(b"created by this invocation")
    parent_descriptor = os.open(tmp_path, os.O_RDONLY)
    try:
        metadata = os.stat(destination, follow_symlinks=False)
        identity = counterfactual_module._truth_manifest_identity(metadata)
        with pytest.raises(ValueError, match="owner retained"):
            counterfactual_module._remove_truth_manifest_entry_if_owned(
                parent_descriptor, destination.name, identity
            )
    finally:
        os.close(parent_descriptor)

    assert not destination.exists()
    quarantine = next(tmp_path.glob(".counterfactual-truth-cleanup-*"))
    assert quarantine.is_file()
    assert quarantine.read_bytes() == b"created by this invocation"


def test_truth_manifest_cleanup_leaves_replacement_seen_before_first_stat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "truth.json"
    destination.write_bytes(b"created by this invocation")
    _absolute_parent, parent_descriptor = counterfactual_module._open_regular_parent(tmp_path)
    metadata = os.stat(destination, follow_symlinks=False)
    identity = counterfactual_module._truth_manifest_identity(metadata)
    real_stat = counterfactual_module.os.stat
    swapped = False

    def swap_before_first_stat(
        path: object,
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        nonlocal swapped
        if dir_fd == parent_descriptor and path == destination.name and not swapped:
            destination.unlink()
            destination.write_bytes(b"replacement installed before first stat")
            swapped = True
        return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(counterfactual_module.os, "stat", swap_before_first_stat)
    monkeypatch.setattr(
        counterfactual_module.os,
        "supports_dir_fd",
        set(counterfactual_module.os.supports_dir_fd) | {swap_before_first_stat},
    )
    try:
        counterfactual_module._remove_truth_manifest_entry_if_owned(
            parent_descriptor, destination.name, identity
        )
    finally:
        os.close(parent_descriptor)

    assert swapped
    assert destination.read_bytes() == b"replacement installed before first stat"
    assert not list(tmp_path.glob(".counterfactual-truth-cleanup-*"))


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


def test_truth_manifest_cleanup_preserves_replacement_between_check_and_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "truth.json"
    destination.write_bytes(b"created by this invocation")
    _absolute_parent, parent_descriptor = counterfactual_module._open_regular_parent(tmp_path)
    owner_descriptor = os.open(destination, os.O_RDONLY)
    try:
        metadata = os.stat(destination, follow_symlinks=False)
        identity = counterfactual_module._truth_manifest_identity(metadata)
        original_match = counterfactual_module._truth_manifest_entry_matches
        swapped = False

        def swap_after_ownership_check(
            descriptor: int, name: str, expected_identity: tuple[int, int]
        ) -> bool:
            nonlocal swapped
            matches = original_match(descriptor, name, expected_identity)
            if matches and not swapped:
                destination.unlink()
                destination.write_bytes(b"replacement installed by attacker")
                swapped = True
            return matches

        monkeypatch.setattr(
            counterfactual_module,
            "_truth_manifest_entry_matches",
            swap_after_ownership_check,
        )

        with pytest.raises(ValueError, match="replacement retained"):
            counterfactual_module._remove_truth_manifest_entry_if_owned(
                parent_descriptor,
                destination.name,
                identity,
                owner_descriptor=owner_descriptor,
            )
    finally:
        os.close(owner_descriptor)
        os.close(parent_descriptor)

    assert swapped
    assert destination.read_bytes() == b"replacement installed by attacker"
    quarantine = next(tmp_path.glob(".counterfactual-truth-cleanup-*"))
    assert quarantine.read_bytes() == b"replacement installed by attacker"


def test_truth_manifest_cleanup_never_unlinks_post_restore_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "truth.json"
    destination.write_bytes(b"created by this invocation")
    _absolute_parent, parent_descriptor = counterfactual_module._open_regular_parent(tmp_path)
    try:
        metadata = os.stat(destination, follow_symlinks=False)
        identity = counterfactual_module._truth_manifest_identity(metadata)
        original_match = counterfactual_module._truth_manifest_entry_matches
        original_link = counterfactual_module.os.link
        original_unlink = counterfactual_module.os.unlink
        original_open = counterfactual_module.os.open
        ownership_swapped = False
        post_restore_swapped = False

        def swap_after_ownership_check(
            descriptor: int, name: str, expected_identity: tuple[int, int]
        ) -> bool:
            nonlocal ownership_swapped
            matches = original_match(descriptor, name, expected_identity)
            if matches and not ownership_swapped:
                destination.unlink()
                destination.write_bytes(b"replacement before restoration")
                ownership_swapped = True
            return matches

        def swapping_link(
            source: object,
            target: object,
            *,
            src_dir_fd: int | None = None,
            dst_dir_fd: int | None = None,
            follow_symlinks: bool = True,
        ) -> None:
            nonlocal post_restore_swapped
            original_link(
                source,
                target,
                src_dir_fd=src_dir_fd,
                dst_dir_fd=dst_dir_fd,
                follow_symlinks=follow_symlinks,
            )
            if (
                src_dir_fd == parent_descriptor
                and dst_dir_fd == parent_descriptor
                and not post_restore_swapped
            ):
                # Simulate an actor replacing the private quarantine entry
                # immediately after restoration.  Cleanup must not unlink it.
                original_unlink(source, dir_fd=src_dir_fd)
                replacement_descriptor = original_open(
                    source,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=src_dir_fd,
                )
                try:
                    os.write(replacement_descriptor, b"replacement after restoration")
                finally:
                    os.close(replacement_descriptor)
                post_restore_swapped = True

        monkeypatch.setattr(
            counterfactual_module,
            "_truth_manifest_entry_matches",
            swap_after_ownership_check,
        )
        monkeypatch.setattr(counterfactual_module.os, "link", swapping_link)
        monkeypatch.setattr(
            counterfactual_module.os,
            "supports_dir_fd",
            set(counterfactual_module.os.supports_dir_fd) | {swapping_link},
        )

        with pytest.raises(ValueError, match="replacement retained"):
            counterfactual_module._remove_truth_manifest_entry_if_owned(
                parent_descriptor, destination.name, identity
            )
    finally:
        os.close(parent_descriptor)

    assert ownership_swapped
    assert post_restore_swapped
    assert destination.read_bytes() == b"replacement before restoration"
    quarantine = next(tmp_path.glob(".counterfactual-truth-cleanup-*"))
    assert quarantine.read_bytes() == b"replacement after restoration"


def test_truth_manifest_cleanup_quarantines_nonlinkable_directory_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "truth.json"
    destination.write_bytes(b"created by this invocation")
    _absolute_parent, parent_descriptor = counterfactual_module._open_regular_parent(tmp_path)
    try:
        metadata = os.stat(destination, follow_symlinks=False)
        identity = counterfactual_module._truth_manifest_identity(metadata)
        original_match = counterfactual_module._truth_manifest_entry_matches
        swapped = False

        def swap_after_ownership_check(
            descriptor: int, name: str, expected_identity: tuple[int, int]
        ) -> bool:
            nonlocal swapped
            matches = original_match(descriptor, name, expected_identity)
            if matches and not swapped:
                destination.unlink()
                replacement = destination.with_name("replacement-directory")
                replacement.mkdir()
                (replacement / "sentinel").write_bytes(b"directory replacement")
                replacement.rename(destination)
                swapped = True
            return matches

        monkeypatch.setattr(
            counterfactual_module,
            "_truth_manifest_entry_matches",
            swap_after_ownership_check,
        )

        with pytest.raises(ValueError, match="replacement retained"):
            counterfactual_module._remove_truth_manifest_entry_if_owned(
                parent_descriptor, destination.name, identity
            )
    finally:
        os.close(parent_descriptor)

    assert swapped
    assert not destination.exists()
    quarantine = next(tmp_path.glob(".counterfactual-truth-cleanup-*"))
    assert (quarantine / "sentinel").read_bytes() == b"directory replacement"


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

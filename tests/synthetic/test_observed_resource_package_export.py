from __future__ import annotations

import copy
import csv
import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from synthetic.native.observations import generate_observation_frame
from synthetic.native.resources import (
    ResourceShape,
    ResourceValidationStatus,
    project_observed_resources,
)
from synthetic.package_export import (
    PackageExportMetadata,
    PackageExportUnavailable,
    export_observed_resource_package,
)
from synthetic.randomness import NamedRandomStreams
from synthetic.schema_contract import load_descriptor
from synthetic.validate import validate_structure
from tests.synthetic.fakes import (
    IdentityPreservingTestDerivationOracle,
    test_derivation_binding,
)
from tests.synthetic.test_observation_generation import _event_trajectory, _policy

ROOT = Path(__file__).resolve().parents[2]


def _descriptor() -> dict:
    return load_descriptor(ROOT / "datapackage.json")


def _metadata() -> PackageExportMetadata:
    return PackageExportMetadata(
        profile="observed-development",
        seed=20260831,
        reference_time="2026-08-31T00:00:00Z",
        reference_id="fictional-observed-reference-v1",
        software_revision="test-revision",
        configuration_sha256="a" * 64,
        reference_sha256="b" * 64,
    )


def _bundle(patient_id: str, stream_index: int):
    trajectory = _event_trajectory()
    trajectory = dataclasses.replace(
        trajectory,
        physiology=dataclasses.replace(
            trajectory.physiology,
            points=tuple(
                dataclasses.replace(point, patient_id=patient_id)
                for point in trajectory.physiology.points
            ),
        ),
        events=tuple(
            dataclasses.replace(event, patient_id=patient_id)
            for event in trajectory.events
        ),
    )
    frame = generate_observation_frame(
        trajectory,
        _policy(
            length_availability_probability=0.0,
            height_availability_probability=1.0,
            weight_availability_probability=1.0,
            head_circumference_availability_probability=1.0,
            recognition_probability=1.0,
            diagnosis_probability=1.0,
            recognition_delay_days=50,
        ),
        NamedRandomStreams(6, stream_index),
    )
    return project_observed_resources(frame, _descriptor())


def _export(tmp_path: Path, bundles: object, output_name: str = "package") -> Path:
    return export_observed_resource_package(
        bundles,
        _descriptor(),
        tmp_path / output_name,
        metadata=_metadata(),
        derivation_oracle=IdentityPreservingTestDerivationOracle(),
        derivation_binding=test_derivation_binding(),
    )


def _csv_rows(package: Path, name: str) -> list[dict[str, str]]:
    path = next(
        resource["path"] for resource in _descriptor()["resources"] if resource["name"] == name
    )
    with (package / path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _package_bytes(package: Path) -> dict[str, bytes]:
    return {
        path.relative_to(package).as_posix(): path.read_bytes()
        for path in sorted(package.rglob("*"))
        if path.is_file()
    }


def _lifecycle_paths(tmp_path: Path, output_name: str = "package") -> list[Path]:
    return [
        path
        for path in tmp_path.iterdir()
        if path.name == output_name or path.name.startswith(f".{output_name}.")
    ]


def test_export_merges_passing_bundles_deterministically_without_private_evaluator_data(
    tmp_path: Path,
) -> None:
    second = _bundle("syn-observed-b", 1)
    first = _bundle("syn-observed-a", 0)

    package = _export(tmp_path, [second, first], "first")
    replay = _export(tmp_path, [first, second], "second")

    assert _package_bytes(package) == _package_bytes(replay)
    assert [row["patient_id"] for row in _csv_rows(package, "patients")] == [
        "syn-observed-a",
        "syn-observed-b",
    ]
    visits = _csv_rows(package, "visits")
    assert [row["patient_id"] for row in visits] == ["syn-observed-a"] * 5 + [
        "syn-observed-b"
    ] * 5
    assert all(_csv_rows(package, name) == [] for name in (
        "labs",
        "medications",
        "problem_list",
        "referrals",
    ))
    assert [row["enc_diag_1"] for row in visits if row["age_in_days"] == "1000"] == [
        "R62.52",
        "R62.52",
    ]
    assert [row["enc_diag_2"] for row in visits if row["age_in_days"] == "1500"] == [
        "R62.59",
        "R62.59",
    ]
    assert len(_csv_rows(package, "patients_augmented")) == 2
    assert len(_csv_rows(package, "visits_augmented")) == 10
    descriptor = json.loads((package / "datapackage.json").read_text(encoding="utf-8"))
    assert validate_structure(package, descriptor).errors == ()

    public_text = b"".join(_package_bytes(package).values()).decode("utf-8")
    private_tokens = (
        "ObservationFrame",
        "ObservationTruth",
        "observation-stream-identity-v1",
        first.source_frame.truth.truth_hash,
        first.source_frame.truth.latent_trajectory_hash,
        "latent_onset",
        "opportunity_index",
    )
    assert all(token not in public_text for token in private_tokens if token is not None)


@pytest.mark.parametrize(
    "kind",
    ["non-pass", "empty", "shape", "duplicate-patient", "duplicate-visit", "malformed-row"],
)
def test_export_rejects_invalid_bundles_before_creating_lifecycle_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, kind: str
) -> None:
    first = _bundle("syn-observed-a", 0)
    second = _bundle("syn-observed-b", 1)
    bundles: object = [first]
    if kind == "non-pass":
        row = first.rows["visits"][0]
        values = row.to_mapping()
        values["BMI"] = -1.0
        object.__setattr__(row, "values", tuple(values.items()))
        object.__setattr__(first, "source_frame", None)
    elif kind == "empty":
        bundles = []
    elif kind == "shape":
        incompatible_descriptor = copy.deepcopy(_descriptor())
        incompatible_descriptor["resources"][0]["schema"]["fields"][:2] = reversed(
            incompatible_descriptor["resources"][0]["schema"]["fields"][:2]
        )
        object.__setattr__(first, "shape", ResourceShape.from_descriptor(incompatible_descriptor))
        monkeypatch.setattr(
            "synthetic.package_export.validate_observed_resources",
            lambda bundle: type("Report", (), {"status": ResourceValidationStatus.PASS})(),
        )
    elif kind == "duplicate-patient":
        bundles = [first, first]
    elif kind == "duplicate-visit":
        row = second.rows["visits"][0]
        values = row.to_mapping()
        values["visit_id"] = first.rows["visits"][0].to_mapping()["visit_id"]
        object.__setattr__(row, "values", tuple(values.items()))
        bundles = [first, second]
        monkeypatch.setattr(
            "synthetic.package_export.validate_observed_resources",
            lambda bundle: type("Report", (), {"status": ResourceValidationStatus.PASS})(),
        )
    else:
        object.__setattr__(first.rows["patients"][0], "values", ())

    with pytest.raises(PackageExportUnavailable, match="observed package export failed"):
        _export(tmp_path, bundles)
    assert _lifecycle_paths(tmp_path) == []


@pytest.mark.parametrize("failure", ["sort", "mapping"])
def test_export_redacts_post_validation_bundle_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: str
) -> None:
    first = _bundle("syn-observed-a", 0)
    second = _bundle("syn-observed-b", 1)
    monkeypatch.setattr(
        "synthetic.package_export.validate_observed_resources",
        lambda _: SimpleNamespace(status=ResourceValidationStatus.PASS),
    )
    bundles: list[object] = [first]
    if failure == "sort":
        class SyntheticIdWithoutOrdering:
            def __init__(self, value: str) -> None:
                self.value = value

            def __hash__(self) -> int:
                return hash(self.value)

            def __eq__(self, other: object) -> bool:
                return isinstance(other, SyntheticIdWithoutOrdering) and self.value == other.value

        object.__setattr__(first, "patient_id", SyntheticIdWithoutOrdering("first"))
        object.__setattr__(second, "patient_id", SyntheticIdWithoutOrdering("second"))
        bundles.append(second)
    else:
        rows = dict(first.rows)
        rows["patients"] = (object(),)
        object.__setattr__(first, "rows", rows)

    with pytest.raises(PackageExportUnavailable, match="observed package export failed"):
        _export(tmp_path, bundles)
    assert _lifecycle_paths(tmp_path) == []

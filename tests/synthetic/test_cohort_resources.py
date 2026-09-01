from __future__ import annotations

import copy
import dataclasses
import json
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest

import synthetic.cohort as cohort_module
from synthetic.cohort import (
    CalibrationSamplingProfile,
    CohortConfig,
    CohortGenerationUnavailable,
    CohortModuleWeight,
    generate_native_cohort,
)
from synthetic.models import DisorderKind
from synthetic.native.clinical_modules import (
    GrowthHormoneDeficiencyModule,
    HealthyGrowthModule,
)
from synthetic.native.observations import (
    ObservationPolicy,
    ObservationValidationStatus,
)
from synthetic.native.resources import (
    BASE_RESOURCE_NAMES,
    ResourceValidationStatus,
    validate_observed_resources,
)
from synthetic.package_export import (
    PackageExportMetadata,
    export_observed_resource_package,
)
from tests.synthetic.cohort_fixtures import aggregate_calibration_artifact
from tests.synthetic.fakes import (
    IdentityPreservingTestDerivationOracle,
    RegimeLinearTestReference,
)

ROOT = Path(__file__).resolve().parents[2]
_AGES = (0, 365, 730, 1460, 2190)


def _descriptor() -> dict[str, object]:
    return json.loads((ROOT / "datapackage.json").read_text(encoding="utf-8"))


def _calibration() -> CalibrationSamplingProfile:
    return CalibrationSamplingProfile.from_artifact(aggregate_calibration_artifact())


def _modules() -> dict[DisorderKind, object]:
    return {
        DisorderKind.HEALTHY: HealthyGrowthModule(),
        DisorderKind.GROWTH_HORMONE_DEFICIENCY: GrowthHormoneDeficiencyModule(),
    }


def _config(**changes: object) -> CohortConfig:
    values: dict[str, object] = {
        "profile": "development-v1",
        "patient_count": 4,
        "seed": 20260831,
        "ages_days": _AGES,
        "observation_policy": ObservationPolicy(
            "cohort-resource-observation-v1",
            0,
            2201,
            length_availability_probability=0.0,
            height_availability_probability=1.0,
            weight_availability_probability=1.0,
            head_circumference_availability_probability=1.0,
        ),
        "module_weights": (
            CohortModuleWeight(DisorderKind.HEALTHY, 0.5),
            CohortModuleWeight(DisorderKind.GROWTH_HORMONE_DEFICIENCY, 0.5),
        ),
        "reference_sex_mapping": (("F", "F"), ("M", "M"), ("U", "U")),
    }
    values.update(changes)
    return CohortConfig(**values)  # type: ignore[arg-type]


def test_descriptor_projection_emits_passing_exact_six_resource_bundles() -> None:
    descriptor = _descriptor()

    cohort = generate_native_cohort(
        _config(),
        RegimeLinearTestReference(),
        _calibration(),
        modules=_modules(),
        descriptor=descriptor,
    )

    expected_fields = {
        resource["name"]: tuple(
            field["name"] for field in resource["schema"]["fields"]
        )
        for resource in descriptor["resources"]  # type: ignore[index]
        if resource["name"] in BASE_RESOURCE_NAMES
    }
    patient_ids: list[str] = []
    visit_ids: list[str] = []
    for member in cohort.members:
        bundle = member.bundle
        assert bundle is not None
        assert validate_observed_resources(bundle).status is ResourceValidationStatus.PASS
        assert tuple(bundle.rows) == BASE_RESOURCE_NAMES
        assert bundle.rows["patients"][0].to_mapping() == member.demographics.to_mapping()
        assert all(
            tuple(row.to_mapping()) == expected_fields[resource_name]
            for resource_name in BASE_RESOURCE_NAMES
            for row in bundle.rows[resource_name]
        )
        assert all(bundle.rows[name] == () for name in BASE_RESOURCE_NAMES[2:])
        patient_ids.append(bundle.patient_id)
        visit_ids.extend(
            str(row.to_mapping()["visit_id"]) for row in bundle.rows["visits"]
        )

    assert len(patient_ids) == len(set(patient_ids)) == 4
    assert len(visit_ids) == len(set(visit_ids)) == 4 * len(_AGES)


def test_descriptor_base_resource_order_mismatch_fails_closed() -> None:
    descriptor = copy.deepcopy(_descriptor())
    resources = descriptor["resources"]  # type: ignore[assignment]
    patients_index = next(
        index for index, resource in enumerate(resources) if resource["name"] == "patients"
    )
    visits_index = next(
        index for index, resource in enumerate(resources) if resource["name"] == "visits"
    )
    resources[patients_index], resources[visits_index] = (
        resources[visits_index],
        resources[patients_index],
    )

    class RecordingReference(RegimeLinearTestReference):
        def __init__(self) -> None:
            self.calls = 0

        def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
            self.calls += 1
            return super().value(metric, age_days, reference_sex, z)

    reference = RecordingReference()
    with pytest.raises(CohortGenerationUnavailable) as error:
        generate_native_cohort(
            _config(patient_count=1),
            reference,
            _calibration(),
            modules=_modules(),
            descriptor=descriptor,
        )

    assert error.value.args == ("native cohort generation failed",)
    assert reference.calls == 0


@pytest.mark.parametrize(
    ("resource_name", "field_name"),
    [("visits", "height_in"), ("patients", "race_8")],
)
def test_missing_required_projection_field_fails_before_patient_draws(
    resource_name: str,
    field_name: str,
) -> None:
    descriptor = copy.deepcopy(_descriptor())
    resource = next(
        item
        for item in descriptor["resources"]  # type: ignore[index]
        if item["name"] == resource_name
    )
    resource["schema"]["fields"] = [  # type: ignore[index]
        field
        for field in resource["schema"]["fields"]  # type: ignore[index]
        if field["name"] != field_name
    ]

    class RecordingReference(RegimeLinearTestReference):
        def __init__(self) -> None:
            self.calls = 0

        def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
            self.calls += 1
            return super().value(metric, age_days, reference_sex, z)

    reference = RecordingReference()
    with pytest.raises(CohortGenerationUnavailable) as error:
        generate_native_cohort(
            _config(patient_count=1),
            reference,
            _calibration(),
            modules=_modules(),
            descriptor=descriptor,
        )

    assert error.value.args == ("native cohort generation failed",)
    assert reference.calls == 0


def test_global_visit_identifier_collision_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = cohort_module.project_observed_resources
    first_visit_id: str | None = None

    def colliding_projection(frame, descriptor, demographics):
        nonlocal first_visit_id
        bundle = project(frame, descriptor, demographics)
        visit = bundle.rows["visits"][0]
        values = visit.to_mapping()
        if first_visit_id is None:
            first_visit_id = str(values["visit_id"])
        else:
            values["visit_id"] = first_visit_id
            object.__setattr__(visit, "values", tuple(values.items()))
        return bundle

    monkeypatch.setattr(cohort_module, "project_observed_resources", colliding_projection)
    monkeypatch.setattr(
        cohort_module,
        "validate_observed_resources",
        lambda _bundle: SimpleNamespace(status=ResourceValidationStatus.PASS),
    )

    with pytest.raises(CohortGenerationUnavailable) as error:
        generate_native_cohort(
            _config(patient_count=2),
            RegimeLinearTestReference(),
            _calibration(),
            modules=_modules(),
            descriptor=_descriptor(),
        )

    assert error.value.args == ("native cohort generation failed",)


def test_global_frame_visit_identifier_collision_without_descriptor_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generate_frame = cohort_module.generate_observation_frame
    first_visit_id: str | None = None

    def colliding_frame(trajectory, policy, streams):
        nonlocal first_visit_id
        frame = generate_frame(trajectory, policy, streams)
        if first_visit_id is None:
            first_visit_id = frame.visits[0].visit_id
            return frame
        first_visit = dataclasses.replace(frame.visits[0], visit_id=first_visit_id)
        return dataclasses.replace(frame, visits=(first_visit, *frame.visits[1:]))

    monkeypatch.setattr(cohort_module, "generate_observation_frame", colliding_frame)
    monkeypatch.setattr(
        cohort_module,
        "validate_observation_frame",
        lambda _frame: SimpleNamespace(status=ObservationValidationStatus.PASS),
    )

    with pytest.raises(CohortGenerationUnavailable) as error:
        generate_native_cohort(
            _config(patient_count=2),
            RegimeLinearTestReference(),
            _calibration(),
            modules=_modules(),
        )

    assert error.value.args == ("native cohort generation failed",)


def test_no_descriptor_returns_no_bundles_and_creates_no_output(tmp_path: Path) -> None:
    cohort = generate_native_cohort(
        _config(patient_count=2),
        RegimeLinearTestReference(),
        _calibration(),
        modules=_modules(),
    )

    assert all(member.bundle is None for member in cohort.members)
    assert cohort.to_mapping() == {
        "profile": "development-v1",
        "seed": 20260831,
        "member_count": 2,
        "bundle_count": 0,
        "visible_visit_count": 2 * len(_AGES),
        "visible_event_count": 0,
    }
    assert list(tmp_path.iterdir()) == []


def test_descriptor_access_failure_is_redacted_before_patient_draws(
    tmp_path: Path,
) -> None:
    sensitive = "real-patient-44 /governed/datapackage.json truth_hash"

    class SensitiveDescriptor(Mapping[str, object]):
        def __getitem__(self, key: str) -> object:
            del key
            raise RuntimeError(sensitive)

        def __iter__(self):
            return iter(("resources",))

        def __len__(self) -> int:
            return 1

    class RecordingReference(RegimeLinearTestReference):
        def __init__(self) -> None:
            self.calls = 0

        def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
            self.calls += 1
            return super().value(metric, age_days, reference_sex, z)

    reference = RecordingReference()
    with pytest.raises(CohortGenerationUnavailable) as error:
        generate_native_cohort(
            _config(patient_count=1),
            reference,
            _calibration(),
            modules=_modules(),
            descriptor=SensitiveDescriptor(),
        )

    assert error.value.args == ("native cohort generation failed",)
    assert sensitive not in (str(error.value) + repr(error.value))
    assert reference.calls == 0
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "failure",
    ["frame-status", "resource-status", "resource-exception", "projection-exception"],
)
def test_nonpassing_validation_is_redacted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: str,
) -> None:
    sensitive = "real-patient-validator /governed/validator.csv truth_hash"

    def raise_sensitive(_value):
        raise RuntimeError(sensitive)

    if failure == "frame-status":
        monkeypatch.setattr(
            cohort_module,
            "validate_observation_frame",
            lambda _frame: SimpleNamespace(status=ObservationValidationStatus.FAIL),
        )
    elif failure == "resource-status":
        monkeypatch.setattr(
            cohort_module,
            "validate_observed_resources",
            lambda _bundle: SimpleNamespace(status=ResourceValidationStatus.FAIL),
        )
    elif failure == "resource-exception":
        monkeypatch.setattr(
            cohort_module,
            "validate_observed_resources",
            raise_sensitive,
        )
    else:
        monkeypatch.setattr(
            cohort_module,
            "project_observed_resources",
            lambda *_args: raise_sensitive(None),
        )

    with pytest.raises(CohortGenerationUnavailable) as error:
        generate_native_cohort(
            _config(patient_count=1),
            RegimeLinearTestReference(),
            _calibration(),
            modules=_modules(),
            descriptor=_descriptor(),
        )

    assert error.value.args == ("native cohort generation failed",)
    assert sensitive not in (str(error.value) + repr(error.value))
    assert list(tmp_path.iterdir()) == []


def test_observed_infant_length_projection_failure_is_redacted(
    tmp_path: Path,
) -> None:
    policy = ObservationPolicy(
        "cohort-length-observation-v1",
        0,
        2201,
        length_availability_probability=1.0,
    )

    with pytest.raises(CohortGenerationUnavailable) as error:
        generate_native_cohort(
            _config(patient_count=1, observation_policy=policy),
            RegimeLinearTestReference(),
            _calibration(),
            modules=_modules(),
            descriptor=_descriptor(),
        )

    assert error.value.args == ("native cohort generation failed",)
    assert "LENGTH" not in (str(error.value) + repr(error.value))
    assert list(tmp_path.iterdir()) == []


def test_visible_mappings_retain_rows_and_exclude_evaluator_only_data() -> None:
    cohort = generate_native_cohort(
        _config(patient_count=3),
        RegimeLinearTestReference(),
        _calibration(),
        modules=_modules(),
        descriptor=_descriptor(),
    )

    member_mappings = [member.to_mapping() for member in cohort.members]
    assert all(set(mapping) == {"demographics", "frame", "bundle"} for mapping in member_mappings)
    assert all(mapping["bundle"]["resources"]["visits"] for mapping in member_mappings)  # type: ignore[index]
    assert cohort.to_mapping() == {
        "profile": "development-v1",
        "seed": 20260831,
        "member_count": 3,
        "bundle_count": 3,
        "visible_visit_count": 3 * len(_AGES),
        "visible_event_count": 0,
    }
    encoded = json.dumps(member_mappings, sort_keys=True)
    for forbidden in (
        "growth_hormone_deficiency",
        "severity",
        "source_events",
        "truth_hash",
        "latent_trajectory",
        "stream",
        "support_count",
        "denominator",
        "calibration",
    ):
        assert forbidden not in encoded


def test_member_mapping_rejects_shape_preserving_sensitive_patient_value() -> None:
    sensitive = "/governed/real-patient.csv truth_hash"
    generated = generate_native_cohort(
        _config(patient_count=1),
        RegimeLinearTestReference(),
        _calibration(),
        modules=_modules(),
        descriptor=_descriptor(),
    )
    member = generated.members[0]
    assert member.bundle is not None
    patient_row = member.bundle.rows["patients"][0]
    object.__setattr__(
        patient_row,
        "values",
        tuple(
            (field_name, sensitive if field_name == "sex" else value)
            for field_name, value in patient_row.values
        ),
    )

    with pytest.raises((TypeError, ValueError), match="bundle.rows") as error:
        member.to_mapping()
    assert sensitive not in str(error.value)


def test_member_mapping_redacts_semantic_validator_status_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sensitive = "/governed/real-patient.csv truth_hash"
    generated = generate_native_cohort(
        _config(patient_count=1),
        RegimeLinearTestReference(),
        _calibration(),
        modules=_modules(),
        descriptor=_descriptor(),
    )

    class SensitiveReport:
        @property
        def status(self) -> object:
            raise RuntimeError(sensitive)

    monkeypatch.setattr(
        cohort_module,
        "validate_observed_resources",
        lambda _bundle: SensitiveReport(),
    )
    with pytest.raises((TypeError, ValueError), match="bundle.rows") as error:
        generated.members[0].to_mapping()
    assert sensitive not in str(error.value)


def test_caller_can_export_returned_bundles_separately(tmp_path: Path) -> None:
    descriptor = _descriptor()
    cohort = generate_native_cohort(
        _config(patient_count=2),
        RegimeLinearTestReference(),
        _calibration(),
        modules=_modules(),
        descriptor=descriptor,
    )
    bundles = tuple(member.bundle for member in cohort.members if member.bundle is not None)

    package = export_observed_resource_package(
        bundles,
        descriptor,
        tmp_path / "caller-export",
        metadata=PackageExportMetadata(
            profile="cohort-export",
            seed=20260831,
            reference_time="2026-08-31T00:00:00Z",
            reference_id="fictional-cohort-reference-v1",
            software_revision="task-4-test",
            configuration_sha256="a" * 64,
            reference_sha256="b" * 64,
        ),
        derivation_oracle=IdentityPreservingTestDerivationOracle(),
        trusted_derivation_fingerprint="0123456789abcdef" * 4,
        trusted_derivation_test_only=True,
    )

    assert package == tmp_path / "caller-export"
    assert package.is_dir()

from __future__ import annotations

import json

import pytest

from synthetic.cohort import CohortMember
from synthetic.models import DisorderKind
from synthetic.native.multidisorder_ancillary import (
    MULTIDISORDER_ANCILLARY_BUNDLE_CHECK_NAMES,
    MULTIDISORDER_ANCILLARY_CHECK_NAMES,
    MultidisorderAncillaryBundleUnavailable,
    MultidisorderAncillaryProjection,
    MultidisorderAncillaryValidationStatus,
    merge_multidisorder_ancillary_resources,
    project_multidisorder_ancillary_resources,
    validate_multidisorder_ancillary_bundle,
    validate_multidisorder_ancillary_resources,
)
from synthetic.native.observations import generate_observation_frame
from synthetic.native.resources import ObservedResourceBundle, project_observed_resources
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.test_multidisorder_ancillary_projection import (
    _descriptor,
    _member_for_kind,
    _policy,
    _shape,
)
from tests.synthetic.test_observation_generation import _policy as _observation_policy


def _member_and_base(kind: DisorderKind) -> tuple[CohortMember, ObservedResourceBundle]:
    source = _member_for_kind(kind)
    frame = generate_observation_frame(
        source.trajectory,
        _observation_policy(
            length_availability_probability=0.0,
            height_availability_probability=1.0,
            weight_availability_probability=1.0,
            head_circumference_availability_probability=1.0,
            recognition_probability=1.0,
            diagnosis_probability=1.0,
        ),
        NamedRandomStreams(6, 0),
    )
    member = CohortMember(source.demographics, source.trajectory, frame, None)
    return member, project_observed_resources(
        frame, _descriptor(), member.demographics
    )


def _check(report: object, name: str) -> tuple[str, str]:
    check = next(item for item in report.checks if item.name == name)  # type: ignore[union-attr]
    return check.status.value, check.reason_code


@pytest.mark.parametrize("kind", tuple(DisorderKind))
def test_projection_validator_passes_every_kind_with_fixed_redacted_checks(
    kind: DisorderKind,
) -> None:
    member = _member_for_kind(kind)
    projection = project_multidisorder_ancillary_resources(member, _shape(), _policy())

    report = validate_multidisorder_ancillary_resources(member, projection, _policy())

    assert report.status is MultidisorderAncillaryValidationStatus.PASS
    assert tuple(check.name for check in report.checks) == MULTIDISORDER_ANCILLARY_CHECK_NAMES
    assert all(check.status is MultidisorderAncillaryValidationStatus.PASS for check in report.checks)
    rendered = repr(report) + json.dumps(report.to_mapping(), sort_keys=True)
    assert member.demographics.patient_id not in rendered
    assert "source_frame" not in rendered
    assert "result_value" not in rendered


def test_projection_validator_maps_concrete_failure_without_copying_payload_or_reason() -> None:
    member = _member_for_kind(DisorderKind.CELIAC_DISEASE)
    projection = project_multidisorder_ancillary_resources(member, _shape(), _policy())
    lab = projection.rows["labs"][0]
    marker = "SYN-PRIVATE-WRONG"
    object.__setattr__(
        lab,
        "values",
        tuple(
            (name, marker if name == "result_component_name" else value)
            for name, value in lab.values
        ),
    )

    report = validate_multidisorder_ancillary_resources(member, projection, _policy())

    assert report.status is MultidisorderAncillaryValidationStatus.FAIL
    assert _check(report, "row_schema") == ("FAIL", "ANCILLARY_VALIDATION_FAILED")
    rendered = repr(report) + json.dumps(report.to_mapping(), sort_keys=True)
    assert marker not in rendered
    assert "INVALID_VALUE" not in rendered


def test_empty_pathway_rejects_nonempty_rows() -> None:
    empty_member = _member_for_kind(DisorderKind.FAMILIAL_SHORT_STATURE)
    donor_member = _member_for_kind(DisorderKind.GROWTH_HORMONE_DEFICIENCY)
    donor = project_multidisorder_ancillary_resources(donor_member, _shape(), _policy())
    projection = MultidisorderAncillaryProjection(
        empty_member.demographics.patient_id,
        donor.shape,
        donor.rows,
    )

    report = validate_multidisorder_ancillary_resources(empty_member, projection, _policy())

    assert report.status is MultidisorderAncillaryValidationStatus.FAIL
    assert _check(report, "pathway_scope") == ("FAIL", "ANCILLARY_VALIDATION_FAILED")


@pytest.mark.parametrize("kind", tuple(DisorderKind))
def test_merge_returns_fresh_validated_sidecar_and_never_mutates_member(
    kind: DisorderKind,
) -> None:
    member, base = _member_and_base(kind)
    projection = project_multidisorder_ancillary_resources(member, _shape(), _policy())
    before_base = base.to_mapping()

    merged = merge_multidisorder_ancillary_resources(base, member, projection, _policy())
    report = validate_multidisorder_ancillary_bundle(merged, member, _policy())

    assert merged is not base
    assert member.bundle is None
    assert base.to_mapping() == before_base
    assert report.status is MultidisorderAncillaryValidationStatus.PASS
    assert tuple(check.name for check in report.checks) == (
        MULTIDISORDER_ANCILLARY_BUNDLE_CHECK_NAMES
    )
    for name in projection.rows:
        assert merged.rows[name] == projection.rows[name]
    if any(projection.rows.values()):
        with pytest.raises(
            MultidisorderAncillaryBundleUnavailable,
            match=r"^multidisorder ancillary bundle unavailable$",
        ):
            merge_multidisorder_ancillary_resources(
                merged, member, projection, _policy()
            )


def test_bundle_validation_fails_unresolved_visit_without_rendering_it() -> None:
    member, base = _member_and_base(DisorderKind.GROWTH_HORMONE_DEFICIENCY)
    projection = project_multidisorder_ancillary_resources(member, _shape(), _policy())
    merged = merge_multidisorder_ancillary_resources(
        base, member, projection, _policy()
    )
    missing = "syn-00000000000000000000000000000000"
    lab = merged.rows["labs"][0]
    object.__setattr__(
        lab,
        "values",
        tuple((name, missing if name == "visit_id" else value) for name, value in lab.values),
    )

    report = validate_multidisorder_ancillary_bundle(merged, member, _policy())

    assert report.status is MultidisorderAncillaryValidationStatus.FAIL
    assert _check(report, "ancillary_resources") == (
        "FAIL",
        "ANCILLARY_RESOURCES_INVALID",
    )
    assert missing not in repr(report) + json.dumps(report.to_mapping(), sort_keys=True)

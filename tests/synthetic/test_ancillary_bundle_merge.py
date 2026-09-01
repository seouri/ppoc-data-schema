from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from synthetic.cohort import CohortMember
from synthetic.models import DisorderKind
from synthetic.native.ancillary import GhdAncillaryPolicy, project_ghd_ancillary_resources
from synthetic.native.ancillary_bundle import (
    AncillaryBundleUnavailable,
    merge_ghd_ancillary_resources,
)
from synthetic.native.observations import generate_observation_frame
from synthetic.native.resources import (
    BASE_RESOURCE_NAMES,
    ResourceShape,
    ResourceSpec,
    project_observed_resources,
    validate_observed_resources,
)
from synthetic.randomness import NamedRandomStreams
from tests.synthetic.test_ancillary_projection import _member
from tests.synthetic.test_observation_generation import _policy as observation_policy

ROOT = Path(__file__).resolve().parents[2]


def _descriptor() -> dict[str, object]:
    return json.loads((ROOT / "datapackage.json").read_text(encoding="utf-8"))


def _shape() -> ResourceShape:
    return ResourceShape.from_descriptor(_descriptor())


def _policy() -> GhdAncillaryPolicy:
    return GhdAncillaryPolicy("ghd-ancillary-policy-v1", "1", 7)


def _member_and_base(
    *, treatment: bool = True, recognized: bool = True, kind: DisorderKind = DisorderKind.GROWTH_HORMONE_DEFICIENCY
) -> tuple[CohortMember, object]:
    source_member = _member(treatment=treatment, recognized=recognized, kind=kind)
    frame = generate_observation_frame(
        source_member.trajectory,
        observation_policy(
            length_availability_probability=0.0,
            height_availability_probability=1.0,
            weight_availability_probability=1.0,
            head_circumference_availability_probability=1.0,
            recognition_probability=1.0 if recognized else 0.0,
            diagnosis_probability=1.0 if recognized else 0.0,
        ),
        NamedRandomStreams(6, 0),
    )
    member = CohortMember(source_member.demographics, source_member.trajectory, frame, None)
    return member, project_observed_resources(frame, _descriptor(), member.demographics)


def _merge_inputs(**member_changes: object):
    member, base = _member_and_base(**member_changes)
    projection = project_ghd_ancillary_resources(member, _shape(), _policy())
    return member, base, projection


def test_merge_composes_valid_ghd_rows_in_exact_six_resource_order_without_mutation() -> None:
    member, base, projection = _merge_inputs()
    before_base = base.to_mapping()
    before_projection = projection.to_mapping()

    merged = merge_ghd_ancillary_resources(base, member, projection, _policy())

    assert merged is not base
    assert tuple(merged.rows) == BASE_RESOURCE_NAMES
    assert merged.rows["patients"] == base.rows["patients"]
    assert merged.rows["visits"] == base.rows["visits"]
    for resource_name in ("labs", "medications", "problem_list", "referrals"):
        assert merged.rows[resource_name] == projection.rows[resource_name]
        assert all(
            tuple(field for field, _ in row.values) == merged.shape.field_names(resource_name)
            for row in merged.rows[resource_name]
        )
    assert base.to_mapping() == before_base
    assert projection.to_mapping() == before_projection
    assert validate_observed_resources(merged).status.value == "FAIL"


@pytest.mark.parametrize(
    "member_changes",
    ({"recognized": False}, {"kind": DisorderKind.FAMILIAL_SHORT_STATURE}),
)
def test_merge_preserves_empty_ancillary_projection_for_non_ghd_or_unrecognized_member(
    member_changes: dict[str, object],
) -> None:
    member, base, projection = _merge_inputs(**member_changes)

    merged = merge_ghd_ancillary_resources(base, member, projection, _policy())

    assert merged is not base
    assert all(not merged.rows[name] for name in ("labs", "medications", "problem_list", "referrals"))
    assert merged.to_mapping() == base.to_mapping()


def test_merge_rejects_duplicate_nonempty_base_and_identity_shape_or_frame_mismatches() -> None:
    member, base, projection = _merge_inputs()
    merged = merge_ghd_ancillary_resources(base, member, projection, _policy())
    other_member = dataclasses.replace(
        member,
        frame=dataclasses.replace(member.frame, policy_version="observation-v2"),
    )

    mismatched_projection = dataclasses.replace(projection)
    object.__setattr__(mismatched_projection, "patient_id", "syn-other-patient")
    mismatched_shape = dataclasses.replace(projection)
    object.__setattr__(
        mismatched_shape,
        "shape",
        ResourceShape(
            tuple(
                ResourceSpec(spec.name, (*spec.field_names, "unused_field"))
                for spec in projection.shape.resources
            )
        ),
    )

    for candidate_member, candidate_projection, candidate_base in (
        (member, projection, merged),
        (member, mismatched_projection, base),
        (member, mismatched_shape, base),
        (other_member, projection, base),
    ):
        with pytest.raises(AncillaryBundleUnavailable, match=r"^GHD ancillary bundle unavailable$") as error:
            merge_ghd_ancillary_resources(candidate_base, candidate_member, candidate_projection, _policy())
        assert member.demographics.patient_id not in str(error.value)


def test_merge_rejects_invalid_base_or_projection_at_a_redacted_typed_boundary() -> None:
    member, base, projection = _merge_inputs()
    visit = base.rows["visits"][0]
    object.__setattr__(visit, "values", tuple(reversed(visit.values)))
    with pytest.raises(AncillaryBundleUnavailable, match=r"^GHD ancillary bundle unavailable$"):
        merge_ghd_ancillary_resources(base, member, projection, _policy())

    member, base, projection = _merge_inputs()
    lab = projection.rows["labs"][0]
    object.__setattr__(
        lab,
        "values",
        tuple((name, "SYN-WRONG" if name == "result_component_name" else value) for name, value in lab.values),
    )
    with pytest.raises(AncillaryBundleUnavailable, match=r"^GHD ancillary bundle unavailable$"):
        merge_ghd_ancillary_resources(base, member, projection, _policy())

    with pytest.raises(AncillaryBundleUnavailable, match=r"^GHD ancillary bundle unavailable$"):
        merge_ghd_ancillary_resources(object(), member, projection, _policy())


def test_merge_is_deterministic_and_returns_a_fresh_immutable_bundle_mapping() -> None:
    member, base, projection = _merge_inputs()

    first = merge_ghd_ancillary_resources(base, member, projection, _policy())
    replay = merge_ghd_ancillary_resources(base, member, projection, _policy())

    assert first is not base
    assert replay is not base
    assert first is not replay
    assert first.to_mapping() == replay.to_mapping()
    with pytest.raises(TypeError):
        first.rows["labs"] = ()  # type: ignore[index]
    rendered = repr(first) + json.dumps(first.to_mapping(), sort_keys=True)
    assert "truth" not in rendered
    assert "trajectory" not in rendered
    assert member.demographics.patient_id not in repr(first)

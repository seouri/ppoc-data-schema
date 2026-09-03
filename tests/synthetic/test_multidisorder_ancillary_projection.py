from __future__ import annotations

import json
from pathlib import Path

import pytest

from synthetic.models import DisorderKind
from synthetic.native.ancillary import GhdAncillaryPolicy, project_ghd_ancillary_resources
from synthetic.native.celiac_ancillary import (
    CeliacAncillaryPolicy,
    project_celiac_ancillary_resources,
)
from synthetic.native.excess_weight_ancillary import (
    ExcessWeightAncillaryPolicy,
    project_excess_weight_ancillary_resources,
)
from synthetic.native.multidisorder_ancillary import (
    MULTIDISORDER_ANCILLARY_RESOURCE_NAMES,
    MultidisorderAncillaryPolicy,
    MultidisorderAncillaryProjectionUnavailable,
    project_multidisorder_ancillary_resources,
)
from synthetic.native.pediatric_hypothyroidism_ancillary import (
    PediatricHypothyroidismAncillaryPolicy,
    project_pediatric_hypothyroidism_ancillary_resources,
)
from synthetic.native.resources import ResourceShape
from synthetic.native.sga_ancillary import SgaAncillaryPolicy, project_sga_ancillary_resources
from synthetic.native.turner_ancillary import (
    TurnerAncillaryPolicy,
    project_turner_ancillary_resources,
)
from synthetic.native.undernutrition_ancillary import (
    UndernutritionAncillaryPolicy,
    project_undernutrition_ancillary_resources,
)
from tests.synthetic.test_ancillary_projection import _member as _ghd_member
from tests.synthetic.test_celiac_ancillary_projection import _member as _celiac_member
from tests.synthetic.test_excess_weight_ancillary_projection import (
    _member as _excess_weight_member,
)
from tests.synthetic.test_pediatric_hypothyroidism_ancillary_projection import (
    _member as _hypothyroidism_member,
)
from tests.synthetic.test_sga_ancillary_projection import _member as _sga_member
from tests.synthetic.test_turner_ancillary_projection import _member as _turner_member
from tests.synthetic.test_undernutrition_ancillary_projection import (
    _member as _undernutrition_member,
)

ROOT = Path(__file__).resolve().parents[2]


def _descriptor() -> dict[str, object]:
    return json.loads((ROOT / "datapackage.json").read_text(encoding="utf-8"))


def _shape() -> ResourceShape:
    return ResourceShape.from_descriptor(_descriptor())


def _policy(**changes: object) -> MultidisorderAncillaryPolicy:
    values: dict[str, object] = {
        "policy_id": "multidisorder-ancillary-v1",
        "policy_version": "1",
        "result_delay_days": 7,
    }
    values.update(changes)
    return MultidisorderAncillaryPolicy(**values)  # type: ignore[arg-type]


def _member_for_kind(kind: DisorderKind):
    builders = {
        DisorderKind.HEALTHY: lambda: _turner_member(kind=DisorderKind.HEALTHY),
        DisorderKind.FAMILIAL_SHORT_STATURE: lambda: _ghd_member(kind=kind),
        DisorderKind.CONSTITUTIONAL_DELAY: lambda: _ghd_member(kind=kind),
        DisorderKind.GROWTH_HORMONE_DEFICIENCY: _ghd_member,
        DisorderKind.PEDIATRIC_HYPOTHYROIDISM: _hypothyroidism_member,
        DisorderKind.CELIAC_DISEASE: _celiac_member,
        DisorderKind.SMALL_FOR_GESTATIONAL_AGE: _sga_member,
        DisorderKind.TURNER_SYNDROME: _turner_member,
        DisorderKind.UNDERNUTRITION: _undernutrition_member,
        DisorderKind.EXCESS_WEIGHT: _excess_weight_member,
    }
    return builders[kind]()


_CONCRETE = {
    DisorderKind.GROWTH_HORMONE_DEFICIENCY: (
        GhdAncillaryPolicy,
        project_ghd_ancillary_resources,
    ),
    DisorderKind.PEDIATRIC_HYPOTHYROIDISM: (
        PediatricHypothyroidismAncillaryPolicy,
        project_pediatric_hypothyroidism_ancillary_resources,
    ),
    DisorderKind.CELIAC_DISEASE: (CeliacAncillaryPolicy, project_celiac_ancillary_resources),
    DisorderKind.SMALL_FOR_GESTATIONAL_AGE: (SgaAncillaryPolicy, project_sga_ancillary_resources),
    DisorderKind.TURNER_SYNDROME: (TurnerAncillaryPolicy, project_turner_ancillary_resources),
    DisorderKind.UNDERNUTRITION: (
        UndernutritionAncillaryPolicy,
        project_undernutrition_ancillary_resources,
    ),
    DisorderKind.EXCESS_WEIGHT: (
        ExcessWeightAncillaryPolicy,
        project_excess_weight_ancillary_resources,
    ),
}


@pytest.mark.parametrize("kind", tuple(_CONCRETE))
def test_dispatch_matches_each_reviewed_concrete_projection(kind: DisorderKind) -> None:
    member = _member_for_kind(kind)
    shape = _shape()
    policy = _policy()
    policy_class, projector = _CONCRETE[kind]
    concrete_policy = policy_class(
        f"{policy.policy_id}-{kind.value}",
        policy.policy_version,
        policy.result_delay_days,
    )

    actual = project_multidisorder_ancillary_resources(member, shape, policy)
    expected = projector(member, shape, concrete_policy)

    assert actual.rows == expected.rows
    assert tuple(actual.rows) == MULTIDISORDER_ANCILLARY_RESOURCE_NAMES


@pytest.mark.parametrize(
    "kind",
    (
        DisorderKind.HEALTHY,
        DisorderKind.FAMILIAL_SHORT_STATURE,
        DisorderKind.CONSTITUTIONAL_DELAY,
    ),
)
def test_kinds_without_reviewed_ancillary_pathways_project_four_empty_tuples(
    kind: DisorderKind,
) -> None:
    projection = project_multidisorder_ancillary_resources(
        _member_for_kind(kind), _shape(), _policy()
    )

    assert tuple(projection.rows) == MULTIDISORDER_ANCILLARY_RESOURCE_NAMES
    assert all(projection.rows[name] == () for name in projection.rows)


def test_projector_uses_one_fixed_redacted_boundary_for_malformed_inputs() -> None:
    member = _ghd_member()
    malformed_member = _ghd_member()
    object.__setattr__(malformed_member, "trajectory", object())

    for args in (
        (object(), _shape(), _policy()),
        (member, object(), _policy()),
        (member, _shape(), object()),
        (malformed_member, _shape(), _policy()),
    ):
        with pytest.raises(
            MultidisorderAncillaryProjectionUnavailable,
            match=r"^multidisorder ancillary projection unavailable$",
        ) as error:
            project_multidisorder_ancillary_resources(*args)  # type: ignore[arg-type]
        assert member.demographics.patient_id not in str(error.value)

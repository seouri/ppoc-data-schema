from __future__ import annotations

import dataclasses
import json
from types import MappingProxyType

import pytest

from synthetic.native.multidisorder_ancillary import (
    MULTIDISORDER_ANCILLARY_BUNDLE_CHECK_NAMES,
    MULTIDISORDER_ANCILLARY_CHECK_NAMES,
    MULTIDISORDER_ANCILLARY_RESOURCE_NAMES,
    MultidisorderAncillaryCheck,
    MultidisorderAncillaryPolicy,
    MultidisorderAncillaryValidationReport,
    MultidisorderAncillaryValidationStatus,
    project_multidisorder_ancillary_resources,
)
from synthetic.native.resources import ResourceRow
from tests.synthetic.test_ancillary_projection import _member as _ghd_member
from tests.synthetic.test_multidisorder_ancillary_projection import _policy, _shape


class _StringSubclass(str):
    pass


class _IntegerSubclass(int):
    pass


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("policy_id", 3),
        ("policy_id", "unsafe/path"),
        ("policy_id", "uuid"),
        ("policy_id", ["mutable"]),
        ("policy_id", _StringSubclass("mutable-token")),
        ("policy_version", object()),
        ("policy_version", "patient-version"),
        ("policy_version", _StringSubclass("1")),
        ("result_delay_days", True),
        ("result_delay_days", -1),
        ("result_delay_days", []),
        ("result_delay_days", _IntegerSubclass(7)),
    ),
)
def test_policy_rejects_non_scalar_unsafe_and_negative_values(
    field: str, value: object
) -> None:
    values: dict[str, object] = {
        "policy_id": "multidisorder-ancillary-v1",
        "policy_version": "1",
        "result_delay_days": 7,
    }
    values[field] = value

    with pytest.raises((TypeError, ValueError)):
        MultidisorderAncillaryPolicy(**values)  # type: ignore[arg-type]


def test_policy_reserves_space_for_every_concrete_kind_suffix() -> None:
    longest_suffix = "-growth_hormone_deficiency"
    maximum = "a" * (128 - len(longest_suffix))

    accepted = MultidisorderAncillaryPolicy(maximum, "1", 7)
    assert accepted.policy_id == maximum
    with pytest.raises(ValueError, match="policy_id"):
        MultidisorderAncillaryPolicy(f"{maximum}a", "1", 7)


def test_policy_and_projection_constructors_reject_subclassed_records() -> None:
    class PolicySubclass(MultidisorderAncillaryPolicy):
        pass

    with pytest.raises(TypeError):
        PolicySubclass("multidisorder-ancillary-v1", "1", 7)

    member = _ghd_member()
    projection = project_multidisorder_ancillary_resources(member, _shape(), _policy())

    class ProjectionSubclass(type(projection)):
        pass

    with pytest.raises(TypeError):
        ProjectionSubclass(projection.patient_id, projection.shape, projection.rows)

    class RowsSubclass(dict[str, tuple[ResourceRow, ...]]):
        pass

    with pytest.raises(TypeError):
        type(projection)(projection.patient_id, projection.shape, RowsSubclass(projection.rows))

    class RowSubclass(ResourceRow):
        pass

    rows = dict(projection.rows)
    source = rows["labs"][0]
    rows["labs"] = (RowSubclass(source.resource_name, source.values), *rows["labs"][1:])
    with pytest.raises(TypeError):
        type(projection)(projection.patient_id, projection.shape, rows)


def test_policy_and_projection_are_frozen_and_aggregate_safe() -> None:
    policy = _policy()
    projection = project_multidisorder_ancillary_resources(
        _ghd_member(), _shape(), policy
    )

    assert MULTIDISORDER_ANCILLARY_RESOURCE_NAMES == (
        "labs",
        "medications",
        "problem_list",
        "referrals",
    )
    assert tuple(projection.rows) == MULTIDISORDER_ANCILLARY_RESOURCE_NAMES
    for resource_name, rows in projection.rows.items():
        assert all(
            tuple(field for field, _ in row.values)
            == projection.shape.field_names(resource_name)
            for row in rows
        )
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.result_delay_days = 0  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        projection.patient_id = "syn-other"  # type: ignore[misc]
    with pytest.raises(TypeError):
        projection.rows["labs"] = ()  # type: ignore[index]

    mapping = projection.to_mapping()
    rendered = repr(policy) + repr(projection) + json.dumps(mapping, sort_keys=True)
    assert mapping == {
        "contract": "multidisorder-ancillary-projection-v1",
        "resource_counts": {
            name: len(projection.rows[name])
            for name in MULTIDISORDER_ANCILLARY_RESOURCE_NAMES
        },
    }
    assert projection.patient_id not in rendered
    assert "source_frame" not in rendered
    assert "trajectory" not in rendered
    assert "result_value" not in rendered


def _checks(
    names: tuple[str, ...], status: MultidisorderAncillaryValidationStatus
) -> tuple[MultidisorderAncillaryCheck, ...]:
    reason = {
        MultidisorderAncillaryValidationStatus.PASS: "OK",
        MultidisorderAncillaryValidationStatus.FAIL: "ANCILLARY_VALIDATION_FAILED",
        MultidisorderAncillaryValidationStatus.UNEVALUABLE: "INSUFFICIENT_EVIDENCE",
    }[status]
    return tuple(MultidisorderAncillaryCheck(name, status, reason) for name in names)


@pytest.mark.parametrize(
    "names",
    (MULTIDISORDER_ANCILLARY_CHECK_NAMES, MULTIDISORDER_ANCILLARY_BUNDLE_CHECK_NAMES),
)
def test_validation_report_is_ordered_frozen_and_status_precedence_is_fixed(
    names: tuple[str, ...],
) -> None:
    checks = list(_checks(names, MultidisorderAncillaryValidationStatus.PASS))
    checks[0] = MultidisorderAncillaryCheck(
        names[0],
        MultidisorderAncillaryValidationStatus.FAIL,
        "ANCILLARY_VALIDATION_FAILED",
    )
    checks[-1] = MultidisorderAncillaryCheck(
        names[-1],
        MultidisorderAncillaryValidationStatus.UNEVALUABLE,
        "INSUFFICIENT_EVIDENCE",
    )
    report = MultidisorderAncillaryValidationReport(
        MultidisorderAncillaryValidationStatus.FAIL, tuple(reversed(checks))
    )

    assert tuple(check.name for check in report.checks) == names
    assert report.check_counts == {"PASS": len(names) - 2, "FAIL": 1, "UNEVALUABLE": 1}
    assert isinstance(report.check_counts, MappingProxyType)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.status = MultidisorderAncillaryValidationStatus.PASS  # type: ignore[misc]
    with pytest.raises(ValueError, match="status"):
        MultidisorderAncillaryValidationReport(
            MultidisorderAncillaryValidationStatus.PASS, tuple(checks)
        )

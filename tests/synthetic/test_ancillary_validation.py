from __future__ import annotations

import dataclasses
import json
from types import MappingProxyType

from synthetic.native.ancillary import (
    ANCILLARY_CHECK_NAMES,
    AncillaryValidationStatus,
    GhdAncillaryPolicy,
    validate_ghd_ancillary_resources,
)
from synthetic.native.resources import ResourceRow, ResourceShape
from tests.synthetic.test_ancillary_projection import _member


def _shape() -> ResourceShape:
    return ResourceShape.from_descriptor(
        json.loads(open("datapackage.json", encoding="utf-8").read())
    )


def _policy() -> GhdAncillaryPolicy:
    return GhdAncillaryPolicy("ghd-ancillary-policy-v1", "1", 7)


def _projection(*, treatment: bool = True):
    from synthetic.native.ancillary import project_ghd_ancillary_resources

    member = _member(treatment=treatment)
    return member, project_ghd_ancillary_resources(member, _shape(), _policy())


def _check(report: object, name: str) -> tuple[AncillaryValidationStatus, str]:
    check = next(item for item in report.checks if item.name == name)  # type: ignore[union-attr]
    return check.status, check.reason_code


def _tamper_row(projection: object, resource: str, index: int, values: tuple[tuple[str, object], ...]):
    rows = dict(projection.rows)  # type: ignore[union-attr]
    current = rows[resource][index]
    rows[resource] = (*rows[resource][:index], ResourceRow(resource, values), *rows[resource][index + 1 :])
    object.__setattr__(projection, "rows", MappingProxyType(rows))
    return current


def test_validator_passes_clean_ghd_and_healthy_projections_with_fixed_checks() -> None:
    member, projection = _projection()
    before = projection.to_mapping()
    report = validate_ghd_ancillary_resources(member, projection, _policy())

    assert report.status is AncillaryValidationStatus.PASS
    assert tuple(check.name for check in report.checks) == ANCILLARY_CHECK_NAMES
    assert all(check.status is AncillaryValidationStatus.PASS for check in report.checks)
    assert projection.to_mapping() == before

    healthy = _member(recognized=False)
    from synthetic.native.ancillary import project_ghd_ancillary_resources

    empty = project_ghd_ancillary_resources(healthy, _shape(), _policy())
    assert validate_ghd_ancillary_resources(healthy, empty, _policy()).status is AncillaryValidationStatus.PASS


def test_validator_fails_visible_tampering_without_payload_leakage() -> None:
    member, projection = _projection()
    row = projection.rows["labs"][0]
    changed = tuple((name, "SYN-LEAK" if name == "result_component_name" else value) for name, value in row.values)
    _tamper_row(projection, "labs", 0, changed)

    report = validate_ghd_ancillary_resources(member, projection, _policy())
    rendered = repr(report) + json.dumps(report.to_mapping(), sort_keys=True)
    assert report.status is AncillaryValidationStatus.FAIL
    assert _check(report, "row_schema") == (AncillaryValidationStatus.FAIL, "INVALID_CODE")
    assert "SYN-LEAK" not in rendered
    assert member.demographics.patient_id not in rendered


def test_validator_fails_delay_duplicate_and_cross_resource_link_tampering() -> None:
    member, projection = _projection()
    lab = projection.rows["labs"][0]
    changed = tuple((name, value + 1 if name == "lab_result_date_age_in_days" else value) for name, value in lab.values)
    _tamper_row(projection, "labs", 0, changed)
    assert _check(validate_ghd_ancillary_resources(member, projection, _policy()), "causal_timing")[0] is AncillaryValidationStatus.FAIL

    member, projection = _projection()
    rows = dict(projection.rows)
    rows["referrals"] = (rows["referrals"][0], rows["referrals"][0])
    object.__setattr__(projection, "rows", MappingProxyType(rows))
    assert _check(validate_ghd_ancillary_resources(member, projection, _policy()), "row_schema") == (AncillaryValidationStatus.FAIL, "DUPLICATE_ROW")

    member, projection = _projection()
    row = projection.rows["medications"][0]
    changed = tuple((name, "syn-wrong-visit" if name == "visit_id" else value) for name, value in row.values)
    _tamper_row(projection, "medications", 0, changed)
    assert _check(validate_ghd_ancillary_resources(member, projection, _policy()), "cross_resource_links") == (AncillaryValidationStatus.FAIL, "VISIT_REFERENCE_INVALID")


def test_validator_rejects_float_for_descriptor_integer_even_when_values_compare_equal() -> None:
    member, projection = _projection()
    row = projection.rows["labs"][0]
    _tamper_row(
        projection,
        "labs",
        0,
        tuple((name, 1.0 if name == "result_line_num" else value) for name, value in row.values),
    )
    report = validate_ghd_ancillary_resources(member, projection, _policy())
    assert report.status is AncillaryValidationStatus.FAIL
    assert _check(report, "row_schema")[0] is AncillaryValidationStatus.FAIL

    malformed_frame = dataclasses.replace(member.frame)
    object.__setattr__(malformed_frame, "truth", None)
    malformed_member = dataclasses.replace(member, frame=malformed_frame)
    report = validate_ghd_ancillary_resources(malformed_member, projection, _policy())
    assert report.status is AncillaryValidationStatus.FAIL
    assert _check(report, "row_schema")[0] is AncillaryValidationStatus.FAIL
    assert _check(report, "source_evidence")[0] is AncillaryValidationStatus.UNEVALUABLE


def test_validator_rejects_ids_fixed_values_and_required_shape_without_private_truth() -> None:
    for field_name, replacement in (
        ("lab_order_id", "syn-tampered-order"),
        ("result_flag", "not-synthetic"),
    ):
        member, projection = _projection()
        malformed_frame = dataclasses.replace(member.frame)
        object.__setattr__(malformed_frame, "truth", None)
        malformed_member = dataclasses.replace(member, frame=malformed_frame)
        row = projection.rows["labs"][0]
        _tamper_row(
            projection,
            "labs",
            0,
            tuple((name, replacement if name == field_name else value) for name, value in row.values),
        )
        report = validate_ghd_ancillary_resources(malformed_member, projection, _policy())
        assert report.status is AncillaryValidationStatus.FAIL
        assert _check(report, "row_schema")[0] is AncillaryValidationStatus.FAIL
        assert _check(report, "source_evidence")[0] is AncillaryValidationStatus.UNEVALUABLE

    member, projection = _projection()
    malformed_frame = dataclasses.replace(member.frame)
    object.__setattr__(malformed_frame, "truth", None)
    malformed_member = dataclasses.replace(member, frame=malformed_frame)
    lab_spec = next(spec for spec in projection.shape.resources if spec.name == "labs")
    object.__setattr__(lab_spec, "field_names", tuple(name for name in lab_spec.field_names if name != "result_flag"))
    report = validate_ghd_ancillary_resources(malformed_member, projection, _policy())
    assert report.status is AncillaryValidationStatus.FAIL
    assert _check(report, "row_schema")[0] is AncillaryValidationStatus.FAIL


def test_validator_marks_malformed_private_evidence_unevaluable_unless_row_is_invalid() -> None:
    member, projection = _projection()
    malformed_frame = dataclasses.replace(member.frame)
    object.__setattr__(malformed_frame, "truth", None)
    malformed = dataclasses.replace(member, frame=malformed_frame)
    report = validate_ghd_ancillary_resources(malformed, projection, _policy())
    assert report.status is AncillaryValidationStatus.UNEVALUABLE
    assert _check(report, "source_evidence")[0] is AncillaryValidationStatus.UNEVALUABLE

    row = projection.rows["labs"][0]
    _tamper_row(projection, "labs", 0, tuple(reversed(row.values)))
    report = validate_ghd_ancillary_resources(malformed, projection, _policy())
    assert report.status is AncillaryValidationStatus.FAIL
    assert _check(report, "row_schema")[0] is AncillaryValidationStatus.FAIL

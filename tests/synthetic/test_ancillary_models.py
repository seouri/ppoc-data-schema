from __future__ import annotations

import dataclasses
import inspect
import json
import math
from types import MappingProxyType

import pytest

from synthetic.native.ancillary import (
    ANCILLARY_CHECK_NAMES,
    ANCILLARY_REASON_CODES,
    GHD_ANCILLARY_RESOURCE_NAMES,
    GHD_DIAGNOSIS_CODE,
    GHD_IGF1_COMPONENT,
    GHD_LAB_RESULT_FLAG,
    GHD_MEDICATION_NAME,
    GHD_MEDICATION_RECORD_TYPE,
    GHD_REFERRAL_SPECIALTY,
    AncillaryCheck,
    AncillaryProjectionUnavailable,
    AncillaryResourceProjection,
    AncillaryValidationReport,
    AncillaryValidationStatus,
    GhdAncillaryPolicy,
    project_ghd_ancillary_resources,
    validate_ghd_ancillary_resources,
)
from synthetic.native.resources import ResourceRow, ResourceShape, ResourceSpec


def _shape() -> ResourceShape:
    return ResourceShape(
        tuple(
            ResourceSpec(name, ("patient_id", f"{name}_field"))
            for name in (
                "patients",
                "visits",
                "labs",
                "medications",
                "problem_list",
                "referrals",
            )
        )
    )


def _row(resource_name: str, patient_id: str = "syn-ancillary-patient") -> ResourceRow:
    shape = _shape()
    return ResourceRow(
        resource_name,
        tuple(
            (field_name, patient_id if field_name == "patient_id" else None)
            for field_name in shape.field_names(resource_name)
        ),
    )


def _rows(patient_id: str = "syn-ancillary-patient") -> dict[str, tuple[ResourceRow, ...]]:
    return {
        resource_name: (_row(resource_name, patient_id),)
        for resource_name in GHD_ANCILLARY_RESOURCE_NAMES
    }


def _projection(**changes: object) -> AncillaryResourceProjection:
    values: dict[str, object] = {
        "patient_id": "syn-ancillary-patient",
        "shape": _shape(),
        "rows": _rows(),
    }
    values.update(changes)
    return AncillaryResourceProjection(**values)  # type: ignore[arg-type]


def _policy(**changes: object) -> GhdAncillaryPolicy:
    values: dict[str, object] = {
        "policy_id": "ghd-ancillary-policy-v1",
        "policy_version": "1",
        "result_delay_days": 7,
    }
    values.update(changes)
    return GhdAncillaryPolicy(**values)  # type: ignore[arg-type]


def _checks(status: AncillaryValidationStatus) -> tuple[AncillaryCheck, ...]:
    reason = "OK" if status is AncillaryValidationStatus.PASS else (
        "MALFORMED_ANCILLARY" if status is AncillaryValidationStatus.UNEVALUABLE else "ROW_SCHEMA_INVALID"
    )
    return tuple(AncillaryCheck(name, status, reason) for name in ANCILLARY_CHECK_NAMES)


def test_policy_and_projection_are_frozen_records() -> None:
    policy = _policy()
    projection = _projection()

    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.policy_id = "other"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        projection.patient_id = "other"  # type: ignore[misc]
    assert dataclasses.is_dataclass(policy)
    assert dataclasses.is_dataclass(projection)


def test_policy_rejects_unsafe_tokens_and_invalid_delay() -> None:
    for field_name, value in (
        ("policy_id", "patient-policy"),
        ("policy_id", "../policy"),
        ("policy_id", "policy.json"),
        ("policy_version", "truth-v1"),
        ("policy_version", "policy with spaces"),
    ):
        with pytest.raises((TypeError, ValueError), match=field_name):
            _policy(**{field_name: value})

    for value in (True, -1, 1.5, math.inf, math.nan):
        with pytest.raises((TypeError, ValueError), match="result_delay_days"):
            _policy(result_delay_days=value)


def test_fixed_status_pathway_constants_and_registries_are_closed() -> None:
    assert tuple(status.value for status in AncillaryValidationStatus) == (
        "PASS",
        "FAIL",
        "UNEVALUABLE",
    )
    assert GHD_ANCILLARY_RESOURCE_NAMES == (
        "labs",
        "medications",
        "problem_list",
        "referrals",
    )
    assert GHD_DIAGNOSIS_CODE == "SYN-GHD"
    assert GHD_IGF1_COMPONENT == "SYN-GHD-IGF1"
    assert GHD_LAB_RESULT_FLAG == "Synthetic"
    assert GHD_MEDICATION_NAME == "Synthetic growth hormone"
    assert GHD_MEDICATION_RECORD_TYPE == "Internal"
    assert GHD_REFERRAL_SPECIALTY == "Synthetic Pediatric Endocrinology"
    assert ANCILLARY_CHECK_NAMES == (
        "pathway_scope",
        "row_schema",
        "causal_timing",
        "cross_resource_links",
        "source_evidence",
    )
    assert "OK" in ANCILLARY_REASON_CODES
    assert isinstance(ANCILLARY_REASON_CODES, frozenset)


def test_projection_requires_four_rows_in_fixed_order_and_freezes_mapping() -> None:
    projection = _projection(rows=MappingProxyType(_rows()))

    assert isinstance(projection.rows, MappingProxyType)
    assert tuple(projection.rows) == GHD_ANCILLARY_RESOURCE_NAMES
    with pytest.raises(TypeError):
        projection.rows["labs"] = ()  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        projection.rows = {}  # type: ignore[misc]

    for omitted in GHD_ANCILLARY_RESOURCE_NAMES:
        rows = _rows()
        del rows[omitted]
        with pytest.raises(ValueError, match="resource"):
            _projection(rows=rows)

    reordered = {name: _rows()[name] for name in reversed(GHD_ANCILLARY_RESOURCE_NAMES)}
    with pytest.raises(ValueError, match="order"):
        _projection(rows=reordered)


@pytest.mark.parametrize(
    ("resource_name", "mutate"),
    [
        ("labs", lambda row: ResourceRow("medications", row.values)),
        ("labs", lambda row: ResourceRow("labs", tuple(reversed(row.values)))),
        ("labs", lambda row: ResourceRow("labs", (("patient_id", "syn-p"),))),
    ],
)
def test_projection_rejects_wrong_resource_identity_or_descriptor_field_order(
    resource_name: str, mutate: object
) -> None:
    rows = _rows()
    bad_row = mutate(rows[resource_name][0])  # type: ignore[operator]
    rows[resource_name] = (bad_row,)
    with pytest.raises((TypeError, ValueError), match="(resource|field|descriptor|patient)"):
        _projection(rows=rows)


def test_projection_normalizes_missing_row_values_and_requires_synthetic_patient_ids() -> None:
    projection = _projection()
    row = projection.rows["labs"][0]
    assert row.to_mapping()["labs_field"] == ""

    with pytest.raises(ValueError, match="synthetic"):
        _projection(patient_id="real-patient")
    with pytest.raises(ValueError, match="synthetic"):
        _projection(rows=_rows("real-patient"))


def test_check_and_report_use_fixed_order_and_status_precedence() -> None:
    checks = list(_checks(AncillaryValidationStatus.PASS))
    checks[-1] = AncillaryCheck("source_evidence", AncillaryValidationStatus.UNEVALUABLE, "MALFORMED_ANCILLARY")
    checks[0] = AncillaryCheck("pathway_scope", AncillaryValidationStatus.FAIL, "ROW_SCHEMA_INVALID")
    report = AncillaryValidationReport(AncillaryValidationStatus.FAIL, tuple(reversed(checks)))

    assert tuple(check.name for check in report.checks) == ANCILLARY_CHECK_NAMES
    assert report.status is AncillaryValidationStatus.FAIL
    assert report.check_counts == {"PASS": 3, "FAIL": 1, "UNEVALUABLE": 1}
    assert isinstance(report.check_counts, MappingProxyType)
    assert report.to_mapping() == {
        "status": "FAIL",
        "check_counts": {"PASS": 3, "FAIL": 1, "UNEVALUABLE": 1},
        "checks": [check.to_mapping() for check in report.checks],
    }

    with pytest.raises(ValueError, match="status"):
        AncillaryValidationReport(AncillaryValidationStatus.PASS, tuple(checks))


def test_check_rejects_unknown_names_and_status_reason_mismatches() -> None:
    with pytest.raises(ValueError, match="check"):
        AncillaryCheck("unknown", AncillaryValidationStatus.PASS, "OK")
    with pytest.raises(ValueError, match="reason"):
        AncillaryCheck("pathway_scope", AncillaryValidationStatus.PASS, "ROW_SCHEMA_INVALID")
    with pytest.raises(ValueError, match="reason"):
        AncillaryCheck("pathway_scope", AncillaryValidationStatus.FAIL, "OK")
    with pytest.raises(ValueError, match="reason"):
        AncillaryCheck("pathway_scope", AncillaryValidationStatus.UNEVALUABLE, "ROW_SCHEMA_INVALID")


def test_projection_mapping_has_exact_keys_and_safe_repr() -> None:
    projection = _projection()
    mapping = projection.to_mapping()
    assert tuple(mapping) == ("contract", "patient_id", "resources")
    assert tuple(mapping["resources"]) == GHD_ANCILLARY_RESOURCE_NAMES  # type: ignore[index]
    encoded = json.dumps(mapping, sort_keys=True)
    assert "truth" not in encoded
    assert "trajectory" not in encoded
    assert "severity" not in encoded
    assert "source_frame" not in encoded
    assert "AncillaryResourceProjection" not in repr(projection) or "patient_id" not in repr(projection)
    assert "syn-ancillary-patient" not in repr(projection)


def test_report_mapping_and_repr_are_aggregate_only() -> None:
    report = AncillaryValidationReport(AncillaryValidationStatus.PASS, _checks(AncillaryValidationStatus.PASS))
    encoded = json.dumps(report.to_mapping(), sort_keys=True)
    assert set(report.to_mapping()) == {"status", "check_counts", "checks"}
    assert "patient" not in encoded
    assert "row_id" not in encoded
    assert "truth" not in encoded
    assert "AncillaryValidationReport" in repr(report)
    assert "patient" not in repr(report)


def test_public_stubs_have_narrow_signatures_and_fixed_assembly_errors() -> None:
    assert tuple(inspect.signature(project_ghd_ancillary_resources).parameters) == (
        "member",
        "shape",
        "policy",
    )
    assert tuple(inspect.signature(validate_ghd_ancillary_resources).parameters) == (
        "member",
        "projection",
        "policy",
    )
    for function, args in (
        (project_ghd_ancillary_resources, (object(), object(), object())),
        (validate_ghd_ancillary_resources, (object(), object(), object())),
    ):
        with pytest.raises(AncillaryProjectionUnavailable, match="GHD ancillary projection unavailable"):
            function(*args)  # type: ignore[arg-type]

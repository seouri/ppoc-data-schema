"""Dependency-leaf visible contracts for fictional GHD ancillary rows."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping

from synthetic.native.resources import ResourceRow, ResourceShape

GHD_ANCILLARY_RESOURCE_NAMES = (
    "labs",
    "medications",
    "problem_list",
    "referrals",
)

GHD_DIAGNOSIS_CODE = "SYN-GHD"
GHD_IGF1_COMPONENT = "SYN-GHD-IGF1"
GHD_STIM_COMPONENT = "SYN-GHD-STIM"
GHD_LAB_COMPONENT_NAMES = (GHD_IGF1_COMPONENT, GHD_STIM_COMPONENT)
GHD_LAB_RESULT_FLAG = "Synthetic"
GHD_REFERRAL_SPECIALTY = "Synthetic Pediatric Endocrinology"
GHD_MEDICATION_RECORD_TYPE = "Internal"
GHD_MEDICATION_NAME = "Synthetic growth hormone"

_SYNTHETIC_PATIENT_TOKEN = re.compile(r"^syn-[A-Za-z0-9][A-Za-z0-9._-]*$")
_SYNTHETIC_VISIT_TOKEN = re.compile(r"^syn-[A-Za-z0-9][A-Za-z0-9._:-]*$")
_ANCILLARY_INTEGER_FIELDS = frozenset(
    {
        "result_line_num",
        "lab_order_date_age_in_days",
        "lab_result_date_age_in_days",
        "med_order_date_age_in_days",
        "med_start_date_age_in_days",
        "med_end_date_age_in_days",
        "noted_date_age_in_days",
        "resolved_date_age_in_days",
        "referral_date_age_in_days",
        "referral_number_of_visits",
    }
)
_ANCILLARY_OPTIONAL_INTEGER_FIELDS = frozenset(
    {"med_end_date_age_in_days", "resolved_date_age_in_days"}
)
_ANCILLARY_REQUIRED_FIELDS: Mapping[str, frozenset[str]] = {
    "labs": frozenset(
        {
            "patient_id",
            "visit_id",
            "lab_order_id",
            "result_line_num",
            "lab_order_date_age_in_days",
            "lab_result_date_age_in_days",
            "result_component_name",
            "result_loinc_code",
            "result_value",
            "result_flag",
        }
    ),
    "medications": frozenset(
        {
            "patient_id",
            "visit_id",
            "med_record_id",
            "med_order_date_age_in_days",
            "med_start_date_age_in_days",
            "med_end_date_age_in_days",
            "med_record_type",
            "med_simple_generic_name",
        }
    ),
    "problem_list": frozenset(
        {
            "patient_id",
            "problem_list_id",
            "noted_date_age_in_days",
            "resolved_date_age_in_days",
            "pl_diag",
        }
    ),
    "referrals": frozenset(
        {
            "patient_id",
            "visit_id",
            "referral_id",
            "referral_date_age_in_days",
            "requested_specialty",
            "referral_number_of_visits",
        }
    ),
}


def _synthetic_ancillary_id(patient_id: str, role: str) -> str:
    material = f"ghd-ancillary-id-v1\x1f{patient_id}\x1f{role}".encode()
    return f"syn-{hashlib.sha256(material).hexdigest()}"


def _row_values(row: ResourceRow) -> dict[str, object]:
    values: dict[str, object] = {}
    for pair in row.values:
        if type(pair) is not tuple or len(pair) != 2:
            raise TypeError
        field_name, value = pair
        if not isinstance(field_name, str) or field_name in values:
            raise ValueError
        values[field_name] = value
    return values


def _row_types_are_valid(values: Mapping[str, object]) -> bool:
    for field_name, value in values.items():
        if field_name in _ANCILLARY_INTEGER_FIELDS:
            if value == "":
                if field_name not in _ANCILLARY_OPTIONAL_INTEGER_FIELDS:
                    return False
            elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
                return False
        elif not isinstance(value, str):
            return False
    return True


def _fixed_values_are_valid(
    resource_name: str,
    values: Mapping[str, object],
    patient_id: str,
) -> bool:
    expected: dict[str, object] = {name: "" for name in values}
    expected["patient_id"] = patient_id
    if resource_name == "labs":
        expected.update(
            {
                "lab_order_id": _synthetic_ancillary_id(patient_id, "lab-order"),
                "result_loinc_code": "",
                "result_value": "",
                "result_flag": GHD_LAB_RESULT_FLAG,
            }
        )
    elif resource_name == "medications":
        expected.update(
            {
                "med_record_id": _synthetic_ancillary_id(patient_id, "medication"),
                "med_end_date_age_in_days": "",
                "med_record_type": GHD_MEDICATION_RECORD_TYPE,
                "med_simple_generic_name": GHD_MEDICATION_NAME,
            }
        )
    elif resource_name == "problem_list":
        expected.update(
            {
                "problem_list_id": _synthetic_ancillary_id(patient_id, "problem-list"),
                "resolved_date_age_in_days": "",
                "pl_diag": GHD_DIAGNOSIS_CODE,
            }
        )
    else:
        expected.update(
            {
                "referral_id": _synthetic_ancillary_id(patient_id, "referral"),
                "requested_specialty": GHD_REFERRAL_SPECIALTY,
                "referral_number_of_visits": 1,
            }
        )
    variable_fields = _ANCILLARY_INTEGER_FIELDS | {
        "visit_id",
        "result_component_name",
        "patient_id",
    }
    fixed_values_match = all(
        field_name in variable_fields or values.get(field_name) == expected_value
        for field_name, expected_value in expected.items()
    )
    return (
        fixed_values_match
        and all(
            values.get(field_name) == ""
            for field_name in _ANCILLARY_OPTIONAL_INTEGER_FIELDS
            if field_name in values
        )
        and (
            resource_name != "referrals"
            or values.get("referral_number_of_visits") == 1
        )
    )


def ghd_ancillary_rows_are_valid(
    patient_id: object,
    shape: object,
    rows: object,
    visit_ids: object,
) -> bool:
    """Return whether retained visible ancillary rows satisfy fictional semantics.

    This check deliberately uses only visible, already-snapshotted values. It
    does not inspect trajectory or observation truth and therefore remains a
    dependency leaf that the ordinary cohort serializer can call safely.
    """

    try:
        if (
            not isinstance(patient_id, str)
            or _SYNTHETIC_PATIENT_TOKEN.fullmatch(patient_id) is None
            or type(shape) is not ResourceShape
            or not isinstance(rows, Mapping)
            or tuple(rows) != GHD_ANCILLARY_RESOURCE_NAMES
            or type(visit_ids) is not frozenset
            or not all(
                isinstance(visit_id, str)
                and _SYNTHETIC_VISIT_TOKEN.fullmatch(visit_id) is not None
                for visit_id in visit_ids
            )
        ):
            return False
        for resource_name in GHD_ANCILLARY_RESOURCE_NAMES:
            resource_rows = rows[resource_name]
            if type(resource_rows) is not tuple:
                return False
            maximum = 2 if resource_name == "labs" else 1
            if len(resource_rows) > maximum or (
                resource_name == "labs" and len(resource_rows) == 1
            ):
                return False
            if not resource_rows:
                continue
            fields = shape.field_names(resource_name)
            if not _ANCILLARY_REQUIRED_FIELDS[resource_name].issubset(fields):
                return False
            for row in resource_rows:
                if (
                    type(row) is not ResourceRow
                    or row.resource_name != resource_name
                    or type(row.values) is not tuple
                    or tuple(name for name, _ in row.values) != fields
                ):
                    return False
                values = _row_values(row)
                if (
                    not _row_types_are_valid(values)
                    or not _fixed_values_are_valid(resource_name, values, patient_id)
                    or values.get("patient_id") != patient_id
                ):
                    return False
                if resource_name in {"labs", "medications", "referrals"}:
                    visit_id = values.get("visit_id")
                    if visit_id not in visit_ids:
                        return False
                if resource_name == "medications" and (
                    values["med_start_date_age_in_days"]
                    < values["med_order_date_age_in_days"]
                ):
                    return False
        labs = rows["labs"]
        if labs:
            lab_values = tuple(_row_values(row) for row in labs)
            if tuple(
                (values["result_line_num"], values["result_component_name"])
                for values in lab_values
            ) != ((1, GHD_IGF1_COMPONENT), (2, GHD_STIM_COMPONENT)):
                return False
            if (
                len({values["lab_order_id"] for values in lab_values}) != 1
                or len({values["visit_id"] for values in lab_values}) != 1
                or len(
                    {values["lab_order_date_age_in_days"] for values in lab_values}
                )
                != 1
                or len(
                    {values["lab_result_date_age_in_days"] for values in lab_values}
                )
                != 1
                or lab_values[0]["lab_result_date_age_in_days"]
                < lab_values[0]["lab_order_date_age_in_days"]
            ):
                return False
        return True
    except Exception:  # noqa: BLE001 - malformed visible values are invalid
        return False


__all__ = [
    "GHD_ANCILLARY_RESOURCE_NAMES",
    "GHD_DIAGNOSIS_CODE",
    "GHD_IGF1_COMPONENT",
    "GHD_LAB_COMPONENT_NAMES",
    "GHD_LAB_RESULT_FLAG",
    "GHD_MEDICATION_NAME",
    "GHD_MEDICATION_RECORD_TYPE",
    "GHD_REFERRAL_SPECIALTY",
    "GHD_STIM_COMPONENT",
    "ghd_ancillary_rows_are_valid",
]

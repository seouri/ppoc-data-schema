"""Wholly synthetic input package for governed calibration tests."""

from __future__ import annotations

import csv
from pathlib import Path

from synthetic.csv_package import write_synthetic_descriptor as _write_synthetic_descriptor
from synthetic.schema_contract import field_names, load_descriptor

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _patient_id(index: int, id_prefix: str = "SYN") -> str:
    return f"{id_prefix}-P-{index:03d}"


def _visit_id(index: int, age_index: int, id_prefix: str = "SYN") -> str:
    return f"{id_prefix}-V-{((index - 1) * 4) + age_index + 1:03d}"


def _row(fields: tuple[str, ...], **values: str) -> dict[str, str]:
    return {field: values.get(field, "") for field in fields}


def _fill_required_numeric_values(
    row: dict[str, str], resource: dict[str, object]
) -> dict[str, str]:
    schema = resource["schema"]
    assert isinstance(schema, dict)
    fields = schema["fields"]
    assert isinstance(fields, list)
    for field in fields:
        assert isinstance(field, dict)
        constraints = field.get("constraints") or {}
        name = field.get("name")
        field_type = field.get("type")
        if (
            isinstance(name, str)
            and field_type in {"integer", "number"}
            and isinstance(constraints, dict)
            and constraints.get("required")
            and not row[name]
        ):
            row[name] = "0" if field_type == "integer" else "0.5"
    return row


def _write_rows(
    root: Path, resource: dict[str, object], rows: list[dict[str, str]], descriptor: dict[str, object]
) -> None:
    resource_name = resource["name"]
    assert isinstance(resource_name, str)
    resource_path = resource["path"]
    encoding = resource.get("encoding", "utf-8")
    dialect = resource.get("dialect", {})
    assert isinstance(resource_path, str) and isinstance(encoding, str) and isinstance(dialect, dict)
    fields = field_names(descriptor, resource_name)
    with (root / resource_path).open("w", encoding=encoding, newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter=dialect.get("delimiter", ","),
            quotechar=dialect.get("quoteChar", '"'),
            doublequote=dialect.get("doubleQuote", True),
            extrasaction="raise",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_mock_snapshot(root: Path, *, patient_count: int = 12, id_prefix: str = "SYN") -> Path:
    """Create an exact-schema package containing deterministic fictional records only."""
    if patient_count < 3:
        raise ValueError("patient_count must be at least 3 to cover F/M/U")
    root.mkdir(parents=True, exist_ok=False)
    descriptor = load_descriptor(REPOSITORY_ROOT / "datapackage.json")
    resources = descriptor["resources"]
    assert isinstance(resources, list)
    rows_by_name: dict[str, list[dict[str, str]]] = {resource["name"]: [] for resource in resources}
    sex_values = ("F", "M", "U")
    ethnicities = ("Not Hispanic or Latino", "Hispanic or Latino", "Unknown")
    races = ("White", "Asian", "Black or African American", "")
    encounter_types = ("Office Visit", "Well Visit (Conv.)", "Sick", "Follow-Up")
    age_days = (100, 800, 3500, 6000)
    fields_by_name = {
        resource["name"]: field_names(descriptor, resource["name"])
        for resource in resources
        if isinstance(resource.get("name"), str)
    }

    for index in range(1, patient_count + 1):
        patient_id = _patient_id(index, id_prefix)
        sex = sex_values[(index - 1) % len(sex_values)]
        ethnicity = ethnicities[(index - 1) % len(ethnicities)]
        augmented_ethnicity = ethnicity if ethnicity != "Unknown" else ""
        race_1 = races[(index - 1) % len(races)]
        demographics = {
            "patient_id": patient_id,
            "sex": sex,
            "ethnicity": ethnicity,
            "race_1": race_1,
            "race_2": "Another Race" if index % 4 == 0 else "",
        }
        rows_by_name["patients"].append(_row(fields_by_name["patients"], **demographics))
        rows_by_name["patients_augmented"].append(
            _row(
                fields_by_name["patients_augmented"],
                **(demographics | {"ethnicity": augmented_ethnicity}),
                healthy_flag="1" if index % 2 else "0",
                chronic_dx_flag="1" if index % 3 == 0 else "0",
                growth_dx_flag="1" if index % 4 == 0 else "0",
                ever_stunting_flag="1" if index % 5 == 0 else "0",
                ever_wasting_flag="1" if index % 6 == 0 else "0",
                ever_underweight_flag="1" if index % 7 == 0 else "0",
                ever_obesity_flag="1" if index % 8 == 0 else "0",
                visits_count="4",
                visits_count_pre_dx="2",
                min_visit_age_days="100",
                max_visit_age_days="6000",
                visits_span_days="5900",
                dx_age_years="4.5" if index % 2 else "",
            )
        )
        for age_index, age in enumerate(age_days):
            visit_id = _visit_id(index, age_index, id_prefix)
            nullable_measurement = index % 3 == 0 and age_index == 1
            values = {
                "patient_id": patient_id,
                "visit_id": visit_id,
                "age_in_days": str(age),
                "encounter_type": encounter_types[age_index],
                "orig_enc_source_Epic_yn": "Y" if index % 2 else "N",
                "weight_oz": "" if nullable_measurement else str(120 + index + age_index),
                "height_in": "" if nullable_measurement else str(20 + index + age_index),
                "head_circ_cm": "" if nullable_measurement else str(35 + index),
                "BMI": "" if nullable_measurement else str(15 + index / 10),
            }
            rows_by_name["visits"].append(_row(fields_by_name["visits"], **values))
            rows_by_name["visits_augmented"].append(
                _row(
                    fields_by_name["visits_augmented"],
                    **values,
                    sex=sex,
                    ethnicity=augmented_ethnicity,
                    race_1=race_1,
                    age_in_months=str(age / 30.4375),
                    age_in_years=str(age / 365.25),
                    weight_kg="" if nullable_measurement else str(4 + index / 10),
                    weight_outlier_flag="1" if index == 1 and age_index == 3 else "0",
                    weight_velocity="" if nullable_measurement else "0.12",
                    weight_z_score="" if nullable_measurement else "0.2",
                    height_cm="" if nullable_measurement else str(50 + index),
                    height_outlier_flag="1" if index == 2 and age_index == 3 else "0",
                    height_velocity="" if nullable_measurement else "0.08",
                    height_z_score="" if nullable_measurement else "0.1",
                    head_circ_z_score="" if nullable_measurement else "0.05",
                    bmi="" if nullable_measurement else str(15 + index / 10),
                    bmi_z_score="" if nullable_measurement else "0.15",
                )
            )
        nullable_link_id = (
            _visit_id(index, 0, id_prefix)
            if index % 3 == 1
            else f"{id_prefix}-ORPHAN-L-{index:03d}"
            if index % 3 == 2
            else ""
        )
        medication_link_id = (
            _visit_id(index, 0, id_prefix) if index % 2 else f"{id_prefix}-ORPHAN-M-{index:03d}"
        )
        rows_by_name["labs"].append(
            _row(
                fields_by_name["labs"], patient_id=patient_id, visit_id=nullable_link_id,
                lab_order_id=f"{id_prefix}-L-{index:03d}", result_line_num="1", lab_order_date_age_in_days="100",
                lab_procedure_name="Synthetic panel", lab_procedure_description="Synthetic test",
                lab_result_date_age_in_days="101", result_component_name="Synthetic component",
                result_loinc_code="00000-0", result_value="1", result_flag="",
            )
        )
        rows_by_name["medications"].append(
            _row(
                fields_by_name["medications"], patient_id=patient_id, visit_id=medication_link_id,
                med_record_id=f"{id_prefix}-M-{index:03d}", med_order_date_age_in_days="100",
                med_start_date_age_in_days="100", med_end_date_age_in_days="101",
                med_record_type="Internal", med_simple_generic_name="synthetic-medication",
            )
        )
        rows_by_name["problem_list"].append(
            _row(
                fields_by_name["problem_list"], patient_id=patient_id, problem_list_id=f"{id_prefix}-PL-{index:03d}",
                noted_date_age_in_days="100", resolved_date_age_in_days="", pl_diag="SYN-DX",
            )
        )
        rows_by_name["referrals"].append(
            _row(
                fields_by_name["referrals"], patient_id=patient_id, visit_id=nullable_link_id,
                referral_id=f"{id_prefix}-R-{index:03d}", referral_date_age_in_days="100",
                requested_specialty="Synthetic specialty", referral_number_of_visits="1",
            )
        )
    for resource in resources:
        assert isinstance(resource, dict)
        name = resource["name"]
        assert isinstance(name, str)
        rows_by_name[name] = [
            _fill_required_numeric_values(row, resource) for row in rows_by_name[name]
        ]
        _write_rows(root, resource, rows_by_name[name], descriptor)
    return root


def write_synthetic_descriptor(root: Path) -> Path:
    """Attach a synthetic descriptor to exact-schema fictional fixture rows."""
    descriptor = load_descriptor(REPOSITORY_ROOT / "datapackage.json")
    row_counts: dict[str, int] = {}
    for resource in descriptor["resources"]:
        name = resource["name"]
        path = root / resource["path"]
        with path.open(encoding=resource.get("encoding", "utf-8"), newline="") as handle:
            row_counts[name] = sum(1 for _ in csv.reader(handle)) - 1
    return _write_synthetic_descriptor(root, descriptor, row_counts)

import csv
import json
from collections.abc import Callable
from pathlib import Path

import duckdb
import pytest

from synthetic.calibrate import (
    DEFAULT_AGE_WINDOWS,
    CalibrationAgeWindow,
    CalibrationRunConfig,
    PartitionPolicy,
)
from synthetic.calibration import CalibrationDisclosurePolicy
from synthetic.calibration_input import prepare_input
from synthetic.calibration_targets import (
    ENCOUNTER_CATEGORY_SLUGS,
    ETHNICITY_CATEGORY_SLUGS,
    PHYSIOLOGY_METRICS,
    RACE_CATEGORY_SLUGS,
    RECORDED_FLAGS,
    TARGET_REGISTRY_VERSION,
    RawTarget,
    compute_raw_targets,
)
from synthetic.schema_contract import load_descriptor, resource_spec
from tests.synthetic.calibration_fixtures import write_mock_snapshot

ROOT = Path(__file__).resolve().parents[2]


def _valid_snapshot(root: Path) -> Path:
    snapshot = write_mock_snapshot(root)
    descriptor = load_descriptor(ROOT / "datapackage.json")
    for resource in descriptor["resources"]:
        required_numeric = {
            field["name"]: "0" if field["type"] == "integer" else "0.5"
            for field in resource["schema"]["fields"]
            if field["type"] in {"integer", "number"}
            and (field.get("constraints") or {}).get("required")
        }
        if not required_numeric:
            continue
        path = snapshot / resource["path"]
        encoding = resource.get("encoding", "utf-8")
        with path.open(newline="", encoding=encoding) as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            headers = reader.fieldnames
        assert headers is not None
        for row in rows:
            for field, value in required_numeric.items():
                if not row[field]:
                    row[field] = value
        with path.open("w", newline="", encoding=encoding) as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
    return snapshot


def _config(root: Path, **changes: object) -> CalibrationRunConfig:
    values: dict[str, object] = {
        "data_root": root,
        "source_descriptor": ROOT / "datapackage.json",
        "source_snapshot": "synthetic-v1",
        "artifact_id": "calibration-v1",
        "created_at": "2026-08-31T12:00:00Z",
        "partition_policy": PartitionPolicy("partition-v1", "1", "key-2026", 5_000, 2),
        "disclosure_policy": CalibrationDisclosurePolicy("disclosure-v1", "1", 2, 3),
        "partition_key": b"0123456789abcdef",
        "age_windows": DEFAULT_AGE_WINDOWS,
    }
    values.update(changes)
    return CalibrationRunConfig(**values)  # type: ignore[arg-type]


def _filter_resource(
    root: Path, resource_name: str, keep: Callable[[dict[str, str]], bool]
) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    resource = resource_spec(descriptor, resource_name)
    path = root / resource["path"]
    encoding = resource.get("encoding", "utf-8")
    with path.open(newline="", encoding=encoding) as handle:
        reader = csv.DictReader(handle)
        rows = [row for row in reader if keep(row)]
        headers = reader.fieldnames
    assert headers is not None
    with path.open("w", newline="", encoding=encoding) as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def _computed(root: Path, **changes: object) -> tuple[RawTarget, ...]:
    config = _config(root, **changes)
    with duckdb.connect(":memory:") as connection:
        prepared = prepare_input(connection, config)
        return compute_raw_targets(connection, prepared, config)


def _find(
    targets: tuple[RawTarget, ...],
    stratum_id: str,
    target_name: str,
    statistic: str = "proportion",
) -> RawTarget:
    matches = [
        target
        for target in targets
        if target.stratum_id == stratum_id
        and target.target_name == target_name
        and target.statistic == statistic
    ]
    assert len(matches) == 1
    return matches[0]


@pytest.fixture
def snapshot(tmp_path: Path) -> Path:
    return _valid_snapshot(tmp_path / "snapshot")


def test_registry_covers_descriptor_categories_with_explicit_safe_slugs() -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    resources = {resource["name"]: resource for resource in descriptor["resources"]}
    fields = {
        resource_name: {
            field["name"]: field for field in resources[resource_name]["schema"]["fields"]
        }
        for resource_name in ("patients", "visits")
    }

    assert TARGET_REGISTRY_VERSION == "calibration-targets-v1"
    assert set(ETHNICITY_CATEGORY_SLUGS) == {
        "",
        *fields["patients"]["ethnicity"]["constraints"]["enum"],
    }
    assert set(RACE_CATEGORY_SLUGS) == {
        "",
        *fields["patients"]["race_1"]["constraints"]["enum"],
    }
    assert set(ENCOUNTER_CATEGORY_SLUGS) == set(
        fields["visits"]["encounter_type"]["constraints"]["enum"]
    )
    assert len(set(ETHNICITY_CATEGORY_SLUGS.values())) == len(ETHNICITY_CATEGORY_SLUGS)
    assert len(set(RACE_CATEGORY_SLUGS.values())) == len(RACE_CATEGORY_SLUGS)
    assert len(set(ENCOUNTER_CATEGORY_SLUGS.values())) == len(ENCOUNTER_CATEGORY_SLUGS)
    assert set(RECORDED_FLAGS) == {
        "healthy_flag",
        "chronic_dx_flag",
        "growth_dx_flag",
        "ever_stunting_flag",
        "ever_wasting_flag",
        "ever_underweight_flag",
        "ever_obesity_flag",
    }
    assert set(PHYSIOLOGY_METRICS) == {
        "height_z_score",
        "weight_z_score",
        "bmi_z_score",
        "height_velocity",
        "weight_velocity",
    }


def test_versioned_registries_cannot_be_mutated_at_runtime() -> None:
    try:
        with pytest.raises(TypeError):
            ENCOUNTER_CATEGORY_SLUGS["Unapproved"] = "unapproved"  # type: ignore[index]
    finally:
        if isinstance(ENCOUNTER_CATEGORY_SLUGS, dict):
            ENCOUNTER_CATEGORY_SLUGS.pop("Unapproved", None)


def test_demographic_targets_preserve_empty_and_multiselect_categories(snapshot: Path) -> None:
    targets = _computed(snapshot)
    stratum = "outcome_layer=observed"

    assert _find(targets, stratum, "sex_f") == RawTarget(
        stratum, (("outcome_layer", "observed"),), "sex_f", "demographics",
        "proportion", "proportion", 2 / 9, 2, 9,
    )
    assert _find(targets, stratum, "sex_m").support_count == 3
    assert _find(targets, stratum, "sex_u").support_count == 4
    assert _find(targets, stratum, "ethnicity_not_hispanic_or_latino").support_count == 2
    assert _find(targets, stratum, "ethnicity_hispanic_or_latino").support_count == 3
    assert _find(targets, stratum, "ethnicity_unknown").support_count == 4
    assert _find(targets, stratum, "ethnicity_blank").value == 0
    assert _find(targets, stratum, "race_white").support_count == 2
    assert _find(targets, stratum, "race_asian").support_count == 2
    assert _find(targets, stratum, "race_black_or_african_american").support_count == 3
    assert _find(targets, stratum, "race_blank").support_count == 2
    assert _find(targets, stratum, "race_multiselect").support_count == 0
    assert _find(targets, stratum, "race_multiselect").denominator == 9


def test_multiselect_race_requires_more_than_one_nonblank_selection(snapshot: Path) -> None:
    config = _config(snapshot)
    with duckdb.connect(":memory:") as connection:
        prepared = prepare_input(connection, config)
        connection.execute(
            "UPDATE calibration_stage_patients SET race_2 = 'Another Race' "
            "WHERE patient_id = 'SYN-P-003'"
        )
        targets = compute_raw_targets(connection, prepared, config)

    target = _find(targets, "outcome_layer=observed", "race_multiselect")
    assert (target.value, target.support_count, target.denominator) == (1 / 9, 1, 9)


def test_recorded_flag_targets_use_patient_level_positive_support(snapshot: Path) -> None:
    targets = _computed(snapshot)
    expected = {
        "healthy_flag": 5,
        "chronic_dx_flag": 4,
        "stature_dx_flag": 2,
        "ever_stunting_flag": 2,
        "ever_wasting_flag": 2,
        "ever_underweight_flag": 1,
        "ever_obesity_flag": 1,
    }

    for name, numerator in expected.items():
        target = _find(targets, "outcome_layer=observed", name)
        assert target.family == "recorded_outcome"
        assert target.support_count == numerator
        assert target.denominator == 9
        assert target.value == numerator / 9


def test_diagnosis_age_targets_are_recorded_finite_summaries(snapshot: Path) -> None:
    targets = _computed(snapshot)
    stratum = "outcome_layer=observed"

    mean = _find(targets, stratum, "diagnosis_age_years_mean", "mean")
    q50 = _find(targets, stratum, "diagnosis_age_years_q50", "quantile")
    q90 = _find(targets, stratum, "diagnosis_age_years_q90", "quantile")
    for target in (mean, q50, q90):
        assert target.family == "recorded_outcome"
        assert target.unit == "year"
        assert target.value == 4.5
        assert target.support_count == 5
        assert target.denominator is None
    assert mean.quantile_level is None
    assert q50.quantile_level == 0.5
    assert q90.quantile_level == 0.9


def test_utilization_targets_have_patient_and_encounter_grain_semantics(snapshot: Path) -> None:
    targets = _computed(snapshot)
    stratum = "visit_window=all"

    assert _find(targets, stratum, "encounters_per_person_mean", "mean").value == 4
    assert _find(targets, stratum, "encounters_per_person_q50", "quantile").value == 4
    assert _find(targets, stratum, "encounters_per_person_q90", "quantile").value == 4
    assert _find(targets, stratum, "observation_span_days_mean", "mean").value == 5900
    assert _find(targets, stratum, "observation_span_days_q50", "quantile").value == 5900
    assert _find(targets, stratum, "observation_span_days_q90", "quantile").value == 5900
    office = _find(targets, stratum, "encounter_office")
    assert (office.value, office.support_count, office.denominator) == (0.25, 9, 36)
    unsupported_in_fixture = _find(targets, stratum, "encounter_walk_in")
    assert (unsupported_in_fixture.value, unsupported_in_fixture.support_count) == (0, 0)
    epic = _find(targets, stratum, "epic_origin")
    assert (epic.value, epic.support_count, epic.denominator) == (20 / 36, 20, 36)
    childhood_interval = _find(
        targets, "age_regime=childhood", "encounter_interval_days_mean", "mean"
    )
    assert (childhood_interval.value, childhood_interval.support_count) == (700, 9)
    assert _find(
        targets, "age_regime=puberty_window", "encounter_interval_days_q90", "quantile"
    ).value == 2700


def test_zero_calibration_encounters_omit_undefined_proportions(tmp_path: Path) -> None:
    snapshot = _valid_snapshot(tmp_path / "snapshot")
    calibration_ids = {
        "SYN-P-003", "SYN-P-005", "SYN-P-006", "SYN-P-007", "SYN-P-008",
        "SYN-P-009", "SYN-P-010", "SYN-P-011", "SYN-P-012",
    }
    for resource_name in ("visits", "visits_augmented"):
        _filter_resource(
            snapshot,
            resource_name,
            lambda row: row["patient_id"] not in calibration_ids,
        )
    config = _config(snapshot)

    with duckdb.connect(":memory:") as connection:
        prepared = prepare_input(connection, config)
        assert prepared.partition_summary.resource_row_counts["visits"]["calibration"] == 0
        targets = compute_raw_targets(connection, prepared, config)

    all_encounter_names = {
        f"encounter_{slug}" for slug in ENCOUNTER_CATEGORY_SLUGS.values()
    } | {"epic_origin"}
    assert not any(
        target.stratum_id == "visit_window=all" and target.target_name in all_encounter_names
        for target in targets
    )


def test_singleton_interval_is_emitted_for_minimum_one_policy(tmp_path: Path) -> None:
    snapshot = _valid_snapshot(tmp_path / "snapshot")
    held_out_ids = {"SYN-P-001", "SYN-P-002", "SYN-P-004"}
    for resource_name in ("visits", "visits_augmented"):
        _filter_resource(
            snapshot,
            resource_name,
            lambda row: row["patient_id"] in held_out_ids
            or (row["patient_id"] == "SYN-P-003" and row["age_in_days"] in {"100", "800"}),
        )
    config = _config(
        snapshot,
        partition_policy=PartitionPolicy("partition-v1", "1", "key-2026", 5_000, 1),
        disclosure_policy=CalibrationDisclosurePolicy("disclosure-v1", "1", 1, 3),
        age_windows=(CalibrationAgeWindow("edge", 0, 1000),),
    )

    with duckdb.connect(":memory:") as connection:
        prepared = prepare_input(connection, config)
        assert prepared.partition_summary.resource_row_counts["visits"]["calibration"] == 2
        targets = compute_raw_targets(connection, prepared, config)

    for name, statistic, level in (
        ("encounter_interval_days_mean", "mean", None),
        ("encounter_interval_days_q50", "quantile", 0.5),
        ("encounter_interval_days_q90", "quantile", 0.9),
    ):
        target = _find(targets, "age_regime=edge", name, statistic)
        assert (target.value, target.support_count, target.denominator) == (700, 1, None)
        assert target.quantile_level == level


def test_observation_targets_separate_availability_and_logical_associations(snapshot: Path) -> None:
    targets = _computed(snapshot)
    infancy = "age_regime=infancy"
    childhood = "age_regime=childhood"

    for name in ("weight_available", "height_available", "head_circ_available", "bmi_available"):
        target = _find(targets, infancy, name)
        assert target.family == "observation"
        assert (target.value, target.support_count, target.denominator) == (1, 9, 9)
        childhood_target = _find(targets, childhood, name)
        assert (
            childhood_target.value,
            childhood_target.support_count,
            childhood_target.denominator,
        ) == (5 / 9, 5, 9)

    for name in (
        "lab_encounter_association",
        "medication_encounter_association",
        "referral_encounter_association",
    ):
        target = _find(targets, "visit_window=all", name)
        assert target.family == "observation"
        assert (target.value, target.support_count, target.denominator) == (5 / 9, 5, 9)


def test_clean_physiology_emits_mean_sample_sd_and_approved_quantiles(snapshot: Path) -> None:
    targets = _computed(snapshot)
    stratum = "age_regime=infancy|recorded_sex=U"

    assert _find(targets, stratum, "weight_z_mean", "mean").value == pytest.approx(0.2)
    assert _find(targets, stratum, "weight_z_sd", "sd").value == pytest.approx(0)
    q10 = _find(targets, stratum, "weight_z_q10", "quantile")
    assert (q10.value, q10.support_count, q10.denominator, q10.quantile_level) == (
        pytest.approx(0.2), 4, None, 0.1,
    )
    assert _find(targets, stratum, "weight_z_q50", "quantile").quantile_level == 0.5
    assert _find(targets, stratum, "weight_z_q90", "quantile").quantile_level == 0.9
    assert _find(targets, stratum, "height_z_mean", "mean").support_count == 4
    assert _find(targets, stratum, "bmi_z_mean", "mean").value == pytest.approx(0.15)
    assert _find(targets, stratum, "height_velocity_mean", "mean").value == pytest.approx(0.08)
    assert _find(targets, stratum, "weight_velocity_mean", "mean").value == pytest.approx(0.12)


def test_physiology_excludes_outliers_and_biv_nulls(snapshot: Path) -> None:
    config = _config(snapshot)
    with duckdb.connect(":memory:") as connection:
        prepared = prepare_input(connection, config)
        connection.execute(
            "UPDATE calibration_stage_visits_augmented "
            "SET weight_z_score = '99', weight_outlier_flag = '1', "
            "height_z_score = '' WHERE patient_id = 'SYN-P-003' AND age_in_days = '100'"
        )
        targets = compute_raw_targets(connection, prepared, config)

    stratum = "age_regime=infancy|recorded_sex=U"
    weight = _find(targets, stratum, "weight_z_mean", "mean")
    height = _find(targets, stratum, "height_z_mean", "mean")
    assert (weight.value, weight.support_count) == (pytest.approx(0.2), 3)
    assert (height.value, height.support_count) == (pytest.approx(0.1), 3)


@pytest.mark.parametrize("flag_value", ["", "not-an-integer"])
@pytest.mark.parametrize(
    ("flag_column", "changed_columns", "target_expectations"),
    [
        (
            "weight_outlier_flag",
            ("weight_z_score", "weight_velocity", "bmi_z_score"),
            (("weight_z_mean", 0.2), ("weight_velocity_mean", 0.12), ("bmi_z_mean", 0.15)),
        ),
        (
            "height_outlier_flag",
            ("height_z_score", "height_velocity", "bmi_z_score"),
            (("height_z_mean", 0.1), ("height_velocity_mean", 0.08), ("bmi_z_mean", 0.15)),
        ),
    ],
)
def test_physiology_requires_explicit_clean_outlier_flags(
    snapshot: Path,
    flag_value: str,
    flag_column: str,
    changed_columns: tuple[str, ...],
    target_expectations: tuple[tuple[str, float], ...],
) -> None:
    config = _config(snapshot)
    assignments = ", ".join(f'"{column}" = \'99\'' for column in changed_columns)
    with duckdb.connect(":memory:") as connection:
        prepared = prepare_input(connection, config)
        connection.execute(
            f'UPDATE calibration_stage_visits_augmented SET {assignments}, '
            f'"{flag_column}" = ? WHERE patient_id = \'SYN-P-003\' AND age_in_days = \'100\'',
            [flag_value],
        )
        targets = compute_raw_targets(connection, prepared, config)

    stratum = "age_regime=infancy|recorded_sex=U"
    for target_name, expected_value in target_expectations:
        target = _find(targets, stratum, target_name, "mean")
        assert (target.value, target.support_count) == (pytest.approx(expected_value), 3)


def test_physiology_omits_registry_cells_with_fewer_than_two_contributors(
    snapshot: Path,
) -> None:
    config = _config(snapshot)
    with duckdb.connect(":memory:") as connection:
        prepared = prepare_input(connection, config)
        connection.execute(
            "UPDATE calibration_stage_visits_augmented SET weight_z_score = '' "
            "WHERE patient_id IN ('SYN-P-006', 'SYN-P-009', 'SYN-P-012') "
            "AND age_in_days = '100'"
        )
        targets = compute_raw_targets(connection, prepared, config)

    names = {
        target.target_name
        for target in targets
        if target.stratum_id == "age_regime=infancy|recorded_sex=U"
    }
    assert not names.intersection(
        {"weight_z_mean", "weight_z_sd", "weight_z_q10", "weight_z_q50", "weight_z_q90"}
    )
    assert "height_z_mean" in names


def test_age_windows_are_lower_inclusive_and_upper_exclusive(snapshot: Path) -> None:
    edge_window = (CalibrationAgeWindow("edge", 100, 800),)
    targets = _computed(snapshot, age_windows=edge_window)

    available = _find(targets, "age_regime=edge", "weight_available")
    assert (available.support_count, available.denominator) == (9, 9)
    assert _find(
        targets, "age_regime=edge|recorded_sex=U", "weight_z_mean", "mean"
    ).support_count == 4
    assert not any(
        target.stratum_id.startswith("age_regime=edge") and target.support_count > 9
        for target in targets
    )


def test_config_rejects_duplicate_age_window_ids(snapshot: Path) -> None:
    duplicate_ids = (
        CalibrationAgeWindow("same", 0, 730),
        CalibrationAgeWindow("same", 730, 3287),
    )

    with pytest.raises(ValueError, match="window_id values must be unique"):
        _config(snapshot, age_windows=duplicate_ids)


def test_compute_defensively_rejects_duplicate_registry_cells(snapshot: Path) -> None:
    config = _config(snapshot)
    object.__setattr__(
        config,
        "age_windows",
        (CalibrationAgeWindow("same", 0, 730), CalibrationAgeWindow("same", 730, 3287)),
    )
    with duckdb.connect(":memory:") as connection:
        prepared = prepare_input(connection, config)
        with pytest.raises(ValueError, match="duplicate cells"):
            compute_raw_targets(connection, prepared, config)


def test_unknown_encounter_category_fails_closed_without_echoing_value(snapshot: Path) -> None:
    config = _config(snapshot)
    with duckdb.connect(":memory:") as connection:
        prepared = prepare_input(connection, config)
        connection.execute(
            "UPDATE calibration_stage_visits SET encounter_type = 'SYN-P-SECRET' "
            "WHERE patient_id = 'SYN-P-003'"
        )
        with pytest.raises(ValueError, match="encounter_type contains an unapproved category") as error:
            compute_raw_targets(connection, prepared, config)
    assert "SYN-P-SECRET" not in str(error.value)


def test_targets_are_canonical_sorted_aggregate_only_and_safe(snapshot: Path) -> None:
    targets = _computed(snapshot)
    forbidden = {
        "patient", "visit", "row", "sequence", "truth", "candidate", "match", "resource",
        "membership_inference", "linkage", "privacy_attack", "attribute_inference",
        "attribute_disclosure", "composition", "differential_privacy", "model_inversion",
        "privacy_audit", "reidentification", "singling_out",
    }

    assert targets == tuple(
        sorted(targets, key=lambda target: (target.stratum_id, target.target_name, target.statistic))
    )
    for target in targets:
        assert target.stratum_id == "|".join(f"{key}={value}" for key, value in target.dimensions)
        assert not any(indicator in target.target_name.lower() for indicator in forbidden)
    payload = json.dumps([target.__dict__ for target in targets])
    assert "SYN-P-" not in payload
    assert "SYN-V-" not in payload

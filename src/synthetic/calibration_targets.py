"""Fixed aggregate target registry for governed calibration inputs."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

import duckdb

from synthetic.calibration_input import CalibrationInput

if TYPE_CHECKING:
    from synthetic.calibrate import CalibrationAgeWindow, CalibrationRunConfig

TARGET_REGISTRY_VERSION = "calibration-targets-v1"

SEX_CATEGORY_SLUGS = {"F": "f", "M": "m", "U": "u"}
ETHNICITY_CATEGORY_SLUGS = {
    "": "blank",
    "Not Hispanic or Latino": "not_hispanic_or_latino",
    "Hispanic or Latino": "hispanic_or_latino",
    "Choose not to Answer": "choose_not_to_answer",
    "Unknown": "unknown",
    "Unable to collect": "unable_to_collect",
    "Patient does not know": "does_not_know",
}
RACE_CATEGORY_SLUGS = {
    "": "blank",
    "American Indian or Alaska Native": "american_indian_or_alaska_native",
    "Another Race": "another",
    "Asian": "asian",
    "Black or African American": "black_or_african_american",
    "Choose not to answer": "choose_not_to_answer",
    "Middle Eastern or Northern African": "middle_eastern_or_northern_african",
    "Native Hawaiian or Other Pacific Islander": "native_hawaiian_or_pacific_islander",
    "Patient does not know": "does_not_know",
    "Unable to collect": "unable_to_collect",
    "Unknown": "unknown",
    "White": "white",
}
ENCOUNTER_CATEGORY_SLUGS = {
    "Office Visit": "office",
    "Well Visit (Conv.)": "well",
    "Sick": "sick",
    "Follow-Up": "follow_up",
    "Walk-In": "walk_in",
    "Consult": "consult",
    "Conversion Encounter": "conversion",
    "Newborn": "newborn",
    "Telemedicine": "telemedicine",
    "Telephone": "telephone",
    "Weight Check": "weight_check",
    "Clinical Support": "clinical_support",
    "Documentation": "documentation",
    "Immunization": "immunization",
    "New Patient": "new_registration",
    "Nutrition": "nutrition",
    "Medication Management": "medication_management",
    "Nurse Only": "nurse_only",
    "Abstract": "abstract",
    "Flu": "flu",
    "Lactation Consult": "lactation_consult",
    "Lab": "lab",
    "Lactation Encounter": "lactation",
    "Procedure visit": "procedure",
    "Pre-op/Pre-procedure Orders": "preprocedure_orders",
    "Erroneous Encounter": "erroneous",
    "Orders Only": "orders_only",
    "External Contact": "external_contact",
    "Patient Message": "portal_message",
    "Evaluation": "evaluation",
    "Lab Requisition": "lab_requisition",
    "Scanned Document": "scanned_document",
    "Letter (Out)": "outgoing_letter",
    "Refill": "refill",
    "History": "history",
    "Ophth Exam": "ophth_exam",
    "Hospital": "hospital",
    "Routine Prenatal": "routine_prenatal",
    "Transcribe Orders": "transcribe_orders",
    "Patient Care Review": "care_review",
    "Episode Changes": "episode_changes",
    "Erroneous Telephone Encounter": "erroneous_telephone",
    "ED": "ed",
    "OurPractice Advisory": "practice_advisory",
    "Treatment": "treatment",
}
RECORDED_FLAGS = {
    "healthy_flag": "healthy_flag",
    "chronic_dx_flag": "chronic_dx_flag",
    "growth_dx_flag": "stature_dx_flag",
    "ever_stunting_flag": "ever_stunting_flag",
    "ever_wasting_flag": "ever_wasting_flag",
    "ever_underweight_flag": "ever_underweight_flag",
    "ever_obesity_flag": "ever_obesity_flag",
}
DIAGNOSIS_AGE_SUMMARIES = {
    "diagnosis_age_years_mean": ("mean", None),
    "diagnosis_age_years_q50": ("quantile", 0.5),
    "diagnosis_age_years_q90": ("quantile", 0.9),
}
MEASUREMENT_AVAILABILITY = {
    "weight_oz": "weight_available",
    "height_in": "height_available",
    "head_circ_cm": "head_circ_available",
    "BMI": "bmi_available",
}
LOGICAL_LINK_RESOURCES = {
    "labs": "lab_encounter_association",
    "medications": "medication_encounter_association",
    "referrals": "referral_encounter_association",
}
PHYSIOLOGY_METRICS = {
    "height_z_score": ("height_z", "z_score", ("height_outlier_flag",)),
    "weight_z_score": ("weight_z", "z_score", ("weight_outlier_flag",)),
    "bmi_z_score": (
        "bmi_z",
        "z_score",
        ("weight_outlier_flag", "height_outlier_flag"),
    ),
    "height_velocity": ("height_velocity", "cm_per_year", ("height_outlier_flag",)),
    "weight_velocity": ("weight_velocity", "kg_per_year", ("weight_outlier_flag",)),
}

SEX_CATEGORY_SLUGS = MappingProxyType(SEX_CATEGORY_SLUGS)
ETHNICITY_CATEGORY_SLUGS = MappingProxyType(ETHNICITY_CATEGORY_SLUGS)
RACE_CATEGORY_SLUGS = MappingProxyType(RACE_CATEGORY_SLUGS)
ENCOUNTER_CATEGORY_SLUGS = MappingProxyType(ENCOUNTER_CATEGORY_SLUGS)
RECORDED_FLAGS = MappingProxyType(RECORDED_FLAGS)
DIAGNOSIS_AGE_SUMMARIES = MappingProxyType(DIAGNOSIS_AGE_SUMMARIES)
MEASUREMENT_AVAILABILITY = MappingProxyType(MEASUREMENT_AVAILABILITY)
LOGICAL_LINK_RESOURCES = MappingProxyType(LOGICAL_LINK_RESOURCES)
PHYSIOLOGY_METRICS = MappingProxyType(PHYSIOLOGY_METRICS)

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_TARGET_NAME_INDICATORS = (
    "patient",
    "visit",
    "identifier",
    "uuid",
    "latent",
    "sequence",
    "truth",
    "candidate",
    "match",
    "row",
    "resource",
    "attribute_disclosure",
    "attribute_inference",
    "composition",
    "differential_privacy",
    "linkage",
    "membership_inference",
    "model_inversion",
    "privacy_audit",
    "privacy_attack",
    "reidentification",
    "singling_out",
)
_FAMILIES = {"demographics", "observation", "physiology", "utilization", "recorded_outcome"}
_STATISTICS = {"count", "proportion", "mean", "sd", "quantile"}
_QUANTILES = (("q10", 0.1), ("q50", 0.5), ("q90", 0.9))


@dataclass(frozen=True)
class RawTarget:
    """A finite aggregate awaiting disclosure control."""

    stratum_id: str
    dimensions: tuple[tuple[str, str], ...]
    target_name: str
    family: str
    statistic: str
    unit: str
    value: int | float
    support_count: int
    denominator: int | None
    quantile_level: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.dimensions, tuple) or not self.dimensions:
            raise ValueError("dimensions must be a nonempty immutable tuple")
        if tuple(sorted(self.dimensions)) != self.dimensions:
            raise ValueError("dimensions must be canonical")
        expected_stratum = "|".join(f"{key}={value}" for key, value in self.dimensions)
        if self.stratum_id != expected_stratum:
            raise ValueError("stratum_id must use canonical sorted dimensions")
        if not isinstance(self.target_name, str) or _TOKEN_RE.fullmatch(self.target_name) is None:
            raise ValueError("target_name must be an ASCII token")
        if any(indicator in self.target_name.lower() for indicator in _TARGET_NAME_INDICATORS):
            raise ValueError("target_name must be aggregate-only")
        if self.family not in _FAMILIES:
            raise ValueError("family is not approved")
        if self.statistic not in _STATISTICS:
            raise ValueError("statistic is not approved")
        if not isinstance(self.unit, str) or _TOKEN_RE.fullmatch(self.unit) is None:
            raise ValueError("unit must be an ASCII token")
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise TypeError("value must be numeric")
        try:
            finite = math.isfinite(self.value)
        except OverflowError as exc:
            raise ValueError("value must be finite") from exc
        if not finite:
            raise ValueError("value must be finite")
        if (
            isinstance(self.support_count, bool)
            or not isinstance(self.support_count, int)
            or self.support_count < 0
        ):
            raise ValueError("support_count must be a nonnegative integer")
        if self.denominator is not None and (
            isinstance(self.denominator, bool)
            or not isinstance(self.denominator, int)
            or self.denominator < self.support_count
        ):
            raise ValueError("denominator must be at least support_count")
        if self.statistic == "count":
            if isinstance(self.value, bool) or not isinstance(self.value, int) or self.value < 0:
                raise ValueError("count values must be nonnegative integers")
            if self.denominator is not None:
                raise ValueError("count targets require a null denominator")
        elif self.statistic == "proportion":
            if self.denominator is None or not 0 <= self.value <= 1:
                raise ValueError("proportions require a denominator and value in 0..1")
        elif self.denominator is not None:
            raise ValueError("continuous summaries require a null denominator")
        if self.statistic == "quantile":
            if self.quantile_level not in {level for _, level in _QUANTILES}:
                raise ValueError("quantile_level is not approved")
        elif self.quantile_level is not None:
            raise ValueError("quantile_level is only valid for quantiles")


def _dimensions(**values: str) -> tuple[str, tuple[tuple[str, str], ...]]:
    dimensions = tuple(sorted(values.items()))
    return "|".join(f"{key}={value}" for key, value in dimensions), dimensions


def _target(
    dimensions: tuple[str, tuple[tuple[str, str], ...]],
    name: str,
    family: str,
    statistic: str,
    unit: str,
    value: float,
    support: int,
    denominator: int | None = None,
    quantile_level: float | None = None,
) -> RawTarget:
    stratum_id, pairs = dimensions
    return RawTarget(
        stratum_id,
        pairs,
        name,
        family,
        statistic,
        unit,
        value,
        support,
        denominator,
        quantile_level,
    )


def _validate_approved_values(connection: duckdb.DuckDBPyConnection) -> None:
    checks = (
        ("patients.sex", "calibration_stage_patients", "sex", SEX_CATEGORY_SLUGS, False),
        (
            "patients.ethnicity",
            "calibration_stage_patients",
            "ethnicity",
            ETHNICITY_CATEGORY_SLUGS,
            True,
        ),
        *(
            (
                f"patients.race_{index}",
                "calibration_stage_patients",
                f"race_{index}",
                RACE_CATEGORY_SLUGS,
                True,
            )
            for index in range(1, 9)
        ),
        (
            "visits.encounter_type",
            "calibration_stage_visits",
            "encounter_type",
            ENCOUNTER_CATEGORY_SLUGS,
            False,
        ),
    )
    for label, relation, column, registry, nullable in checks:
        allowed = tuple(registry)
        placeholders = ", ".join("?" for _ in allowed)
        null_clause = "" if nullable else f'"{column}" IS NULL OR '
        count = connection.execute(
            f'SELECT count(*) FROM "{relation}" WHERE {null_clause}coalesce("{column}", \'\') '
            f"NOT IN ({placeholders})",
            list(allowed),
        ).fetchone()[0]
        if count:
            raise ValueError(f"{label} contains an unapproved category")
    epic_count = connection.execute(
        "SELECT count(*) FROM calibration_stage_visits "
        "WHERE coalesce(orig_enc_source_Epic_yn, '') NOT IN ('', 'Y', 'N')"
    ).fetchone()[0]
    if epic_count:
        raise ValueError("visits.orig_enc_source_Epic_yn contains an unapproved category")
    for column in RECORDED_FLAGS:
        count = connection.execute(
            f'SELECT count(*) FROM calibration_stage_patients_augmented '
            f'WHERE try_cast("{column}" AS INTEGER) NOT IN (0, 1)'
        ).fetchone()[0]
        if count:
            raise ValueError(f"patients_augmented.{column} contains an unapproved flag")


def _patient_targets(connection: duckdb.DuckDBPyConnection) -> list[RawTarget]:
    rows = connection.execute(
        """
        WITH calibration_patients AS (
            SELECT source.*
            FROM calibration_stage_patients AS source
            JOIN patient_partitions AS partitions USING (patient_id)
            WHERE partitions.partition_label = 'calibration'
        )
        SELECT count(*) AS denominator,
               count(*) FILTER (WHERE sex = 'F') AS sex_f,
               count(*) FILTER (WHERE sex = 'M') AS sex_m,
               count(*) FILTER (WHERE sex = 'U') AS sex_u,
               count(*) FILTER (
                   WHERE (CASE WHEN race_1 = '' THEN 0 ELSE 1 END)
                       + (CASE WHEN race_2 = '' THEN 0 ELSE 1 END)
                       + (CASE WHEN race_3 = '' THEN 0 ELSE 1 END)
                       + (CASE WHEN race_4 = '' THEN 0 ELSE 1 END)
                       + (CASE WHEN race_5 = '' THEN 0 ELSE 1 END)
                       + (CASE WHEN race_6 = '' THEN 0 ELSE 1 END)
                       + (CASE WHEN race_7 = '' THEN 0 ELSE 1 END)
                       + (CASE WHEN race_8 = '' THEN 0 ELSE 1 END) > 1
               ) AS race_multiselect
        FROM calibration_patients
        """
    ).fetchone()
    denominator = rows[0]
    dimensions = _dimensions(outcome_layer="observed")
    targets = [
        _target(dimensions, f"sex_{slug}", "demographics", "proportion", "proportion", rows[index] / denominator, rows[index], denominator)
        for index, slug in enumerate(SEX_CATEGORY_SLUGS.values(), start=1)
    ]
    targets.append(
        _target(
            dimensions,
            "race_multiselect",
            "demographics",
            "proportion",
            "proportion",
            rows[4] / denominator,
            rows[4],
            denominator,
        )
    )
    for column, registry, prefix in (
        ("ethnicity", ETHNICITY_CATEGORY_SLUGS, "ethnicity"),
        ("race_1", RACE_CATEGORY_SLUGS, "race"),
    ):
        category_rows = connection.execute(
            f"""
            WITH calibration_patients AS (
                SELECT source.*
                FROM calibration_stage_patients AS source
                JOIN patient_partitions AS partitions USING (patient_id)
                WHERE partitions.partition_label = 'calibration'
            )
            SELECT coalesce("{column}", ''), count(*)
            FROM calibration_patients
            GROUP BY 1
            """
        ).fetchall()
        counts = dict(category_rows)
        for category, slug in registry.items():
            support = counts.get(category, 0)
            targets.append(
                _target(
                    dimensions,
                    f"{prefix}_{slug}",
                    "demographics",
                    "proportion",
                    "proportion",
                    support / denominator,
                    support,
                    denominator,
                )
            )
    flag_select = ", ".join(
        f'count(*) FILTER (WHERE try_cast(source."{column}" AS INTEGER) = 1)'
        for column in RECORDED_FLAGS
    )
    flag_row = connection.execute(
        f"""
        WITH calibration_people AS (
            SELECT source.*
            FROM calibration_stage_patients_augmented AS source
            JOIN patient_partitions AS partitions USING (patient_id)
            WHERE partitions.partition_label = 'calibration'
        )
        SELECT count(*), {flag_select}
        FROM calibration_people AS source
        """
    ).fetchone()
    flag_denominator = flag_row[0]
    for index, target_name in enumerate(RECORDED_FLAGS.values(), start=1):
        support = flag_row[index]
        targets.append(
            _target(
                dimensions,
                target_name,
                "recorded_outcome",
                "proportion",
                "proportion",
                support / flag_denominator,
                support,
                flag_denominator,
            )
        )
    diagnosis_age = connection.execute(
        """
        WITH diagnosis_ages AS (
            SELECT try_cast(source.dx_age_years AS DOUBLE) AS value
            FROM calibration_stage_patients_augmented AS source
            JOIN patient_partitions AS partitions USING (patient_id)
            WHERE partitions.partition_label = 'calibration'
              AND isfinite(try_cast(source.dx_age_years AS DOUBLE))
        )
        SELECT count(*), avg(value), quantile_cont(value, 0.5), quantile_cont(value, 0.9)
        FROM diagnosis_ages
        """
    ).fetchone()
    diagnosis_support = diagnosis_age[0]
    if diagnosis_support:
        for index, (target_name, (statistic, level)) in enumerate(
            DIAGNOSIS_AGE_SUMMARIES.items(), start=1
        ):
            targets.append(
                _target(
                    dimensions,
                    target_name,
                    "recorded_outcome",
                    statistic,
                    "year",
                    diagnosis_age[index],
                    diagnosis_support,
                    None,
                    level,
                )
            )
    return targets


def _utilization_targets(connection: duckdb.DuckDBPyConnection) -> list[RawTarget]:
    dimensions = _dimensions(visit_window="all")
    summary = connection.execute(
        """
        WITH calibration_people AS (
            SELECT try_cast(source.visits_count AS DOUBLE) AS encounter_count,
                   try_cast(source.visits_span_days AS DOUBLE) AS span_days
            FROM calibration_stage_patients_augmented AS source
            JOIN patient_partitions AS partitions USING (patient_id)
            WHERE partitions.partition_label = 'calibration'
        )
        SELECT count(*),
               avg(encounter_count), quantile_cont(encounter_count, 0.5),
               quantile_cont(encounter_count, 0.9), avg(span_days),
               quantile_cont(span_days, 0.5), quantile_cont(span_days, 0.9)
        FROM calibration_people
        """
    ).fetchone()
    support = summary[0]
    targets = [
        _target(dimensions, name, "utilization", statistic, unit, summary[index], support, None, level)
        for index, (name, statistic, unit, level) in enumerate(
            (
                ("encounters_per_person_mean", "mean", "count", None),
                ("encounters_per_person_q50", "quantile", "count", 0.5),
                ("encounters_per_person_q90", "quantile", "count", 0.9),
                ("observation_span_days_mean", "mean", "day", None),
                ("observation_span_days_q50", "quantile", "day", 0.5),
                ("observation_span_days_q90", "quantile", "day", 0.9),
            ),
            start=1,
        )
    ]
    category_rows = connection.execute(
        """
        WITH calibration_encounters AS (
            SELECT source.encounter_type, source.orig_enc_source_Epic_yn
            FROM calibration_stage_visits AS source
            JOIN patient_partitions AS partitions USING (patient_id)
            WHERE partitions.partition_label = 'calibration'
        )
        SELECT encounter_type, count(*)
        FROM calibration_encounters
        GROUP BY encounter_type
        """
    ).fetchall()
    category_counts = dict(category_rows)
    denominator = sum(category_counts.values())
    if denominator:
        for category, slug in ENCOUNTER_CATEGORY_SLUGS.items():
            category_support = category_counts.get(category, 0)
            targets.append(
                _target(
                    dimensions,
                    f"encounter_{slug}",
                    "utilization",
                    "proportion",
                    "proportion",
                    category_support / denominator,
                    category_support,
                    denominator,
                )
            )
        epic_support = connection.execute(
            """
            SELECT count(*)
            FROM calibration_stage_visits AS source
            JOIN patient_partitions AS partitions USING (patient_id)
            WHERE partitions.partition_label = 'calibration'
              AND source.orig_enc_source_Epic_yn = 'Y'
            """
        ).fetchone()[0]
        targets.append(
            _target(
                dimensions,
                "epic_origin",
                "utilization",
                "proportion",
                "proportion",
                epic_support / denominator,
                epic_support,
                denominator,
            )
        )
    for relation, target_name in LOGICAL_LINK_RESOURCES.items():
        link_row = connection.execute(
            f"""
            WITH calibration_links AS (
                SELECT source.visit_id
                FROM "calibration_stage_{relation}" AS source
                JOIN patient_partitions AS partitions USING (patient_id)
                WHERE partitions.partition_label = 'calibration'
            )
            SELECT count(*), count(*) FILTER (WHERE coalesce(visit_id, '') <> '')
            FROM calibration_links
            """
        ).fetchone()
        link_denominator, link_support = link_row
        if link_denominator:
            targets.append(
                _target(
                    dimensions,
                    target_name,
                    "observation",
                    "proportion",
                    "proportion",
                    link_support / link_denominator,
                    link_support,
                    link_denominator,
                )
            )
    return targets


def _age_window_targets(
    connection: duckdb.DuckDBPyConnection, window: CalibrationAgeWindow
) -> list[RawTarget]:
    dimensions = _dimensions(age_regime=window.window_id)
    availability_expressions = ", ".join(
        f'count(*) FILTER (WHERE isfinite(try_cast(source."{column}" AS DOUBLE)))'
        for column in MEASUREMENT_AVAILABILITY
    )
    row = connection.execute(
        f"""
        WITH calibration_encounters AS (
            SELECT source.*
            FROM calibration_stage_visits AS source
            JOIN patient_partitions AS partitions USING (patient_id)
            WHERE partitions.partition_label = 'calibration'
              AND try_cast(source.age_in_days AS BIGINT) >= ?
              AND try_cast(source.age_in_days AS BIGINT) < ?
        )
        SELECT count(*), {availability_expressions}
        FROM calibration_encounters AS source
        """,
        [window.lower_age_days, window.upper_age_days],
    ).fetchone()
    denominator = row[0]
    targets: list[RawTarget] = []
    if denominator:
        for index, name in enumerate(MEASUREMENT_AVAILABILITY.values(), start=1):
            support = row[index]
            targets.append(
                _target(
                    dimensions,
                    name,
                    "observation",
                    "proportion",
                    "proportion",
                    support / denominator,
                    support,
                    denominator,
                )
            )
    interval = connection.execute(
        """
        WITH calibration_encounters AS (
            SELECT source.patient_id, source.visit_id,
                   try_cast(source.age_in_days AS BIGINT) AS age_days
            FROM calibration_stage_visits AS source
            JOIN patient_partitions AS partitions USING (patient_id)
            WHERE partitions.partition_label = 'calibration'
        ), ordered AS (
            SELECT age_days,
                   lag(age_days) OVER (
                       PARTITION BY patient_id ORDER BY age_days, visit_id
                   ) AS previous_age_days
            FROM calibration_encounters
        ), intervals AS (
            SELECT age_days - previous_age_days AS interval_days
            FROM ordered
            WHERE age_days >= ? AND age_days < ? AND previous_age_days IS NOT NULL
        )
        SELECT count(*), avg(interval_days), quantile_cont(interval_days, 0.5),
               quantile_cont(interval_days, 0.9)
        FROM intervals
        """,
        [window.lower_age_days, window.upper_age_days],
    ).fetchone()
    support = interval[0]
    if support:
        targets.extend(
            [
                _target(dimensions, "encounter_interval_days_mean", "utilization", "mean", "day", interval[1], support),
                _target(dimensions, "encounter_interval_days_q50", "utilization", "quantile", "day", interval[2], support, None, 0.5),
                _target(dimensions, "encounter_interval_days_q90", "utilization", "quantile", "day", interval[3], support, None, 0.9),
            ]
        )
    return targets


def _physiology_targets(
    connection: duckdb.DuckDBPyConnection, window: CalibrationAgeWindow
) -> list[RawTarget]:
    clean_value_expressions: list[str] = []
    aggregate_expressions: list[str] = []
    for column, (_target_prefix, _unit, flag_columns) in PHYSIOLOGY_METRICS.items():
        clean_flags = " AND ".join(
            f'try_cast(source."{flag}" AS INTEGER) = 0' for flag in flag_columns
        )
        clean_value_expressions.append(
            f'CASE WHEN isfinite(try_cast(source."{column}" AS DOUBLE)) AND {clean_flags} '
            f'THEN try_cast(source."{column}" AS DOUBLE) END AS "{column}"'
        )
        aggregate_expressions.extend(
            (
                f'count("{column}")',
                f'avg("{column}")',
                f'stddev_samp("{column}")',
                f'quantile_cont("{column}", 0.1)',
                f'quantile_cont("{column}", 0.5)',
                f'quantile_cont("{column}", 0.9)',
            )
        )
    rows = connection.execute(
        f"""
        WITH clean_values AS (
            SELECT demographics.sex AS recorded_sex,
                   {", ".join(clean_value_expressions)}
            FROM calibration_stage_visits_augmented AS source
            JOIN patient_partitions AS partitions USING (patient_id)
            JOIN calibration_stage_patients AS demographics USING (patient_id)
            WHERE partitions.partition_label = 'calibration'
              AND try_cast(source.age_in_days AS BIGINT) >= ?
              AND try_cast(source.age_in_days AS BIGINT) < ?
        )
        SELECT recorded_sex, {", ".join(aggregate_expressions)}
        FROM clean_values
        GROUP BY recorded_sex
        """,
        [window.lower_age_days, window.upper_age_days],
    ).fetchall()
    rows_by_sex = {row[0]: row for row in rows}
    targets: list[RawTarget] = []
    for sex in SEX_CATEGORY_SLUGS:
        row = rows_by_sex.get(sex)
        if row is None:
            continue
        dimensions = _dimensions(age_regime=window.window_id, recorded_sex=sex)
        for metric_index, (_column, (target_prefix, unit, _flag_columns)) in enumerate(
            PHYSIOLOGY_METRICS.items()
        ):
            offset = 1 + (metric_index * 6)
            support = row[offset]
            if support < 2:
                continue
            targets.append(
                _target(
                    dimensions,
                    f"{target_prefix}_mean",
                    "physiology",
                    "mean",
                    unit,
                    row[offset + 1],
                    support,
                )
            )
            targets.append(
                _target(
                    dimensions,
                    f"{target_prefix}_sd",
                    "physiology",
                    "sd",
                    unit,
                    row[offset + 2],
                    support,
                )
            )
            for index, (suffix, level) in enumerate(_QUANTILES, start=3):
                targets.append(
                    _target(
                        dimensions,
                        f"{target_prefix}_{suffix}",
                        "physiology",
                        "quantile",
                        unit,
                        row[offset + index],
                        support,
                        None,
                        level,
                    )
                )
    return targets


def compute_raw_targets(
    connection: duckdb.DuckDBPyConnection,
    prepared: CalibrationInput,
    config: CalibrationRunConfig,
) -> tuple[RawTarget, ...]:
    """Compute fixed calibration-partition aggregates without returning identifiers."""
    from synthetic.calibrate import CalibrationRunConfig

    if not isinstance(connection, duckdb.DuckDBPyConnection):
        raise TypeError("connection must be a DuckDB connection")
    if not isinstance(prepared, CalibrationInput):
        raise TypeError("prepared must be a CalibrationInput")
    if not isinstance(config, CalibrationRunConfig):
        raise TypeError("config must be a CalibrationRunConfig")
    _validate_approved_values(connection)
    targets = [*_patient_targets(connection), *_utilization_targets(connection)]
    for window in config.age_windows:
        targets.extend(_age_window_targets(connection, window))
        targets.extend(_physiology_targets(connection, window))
    keys = [(target.stratum_id, target.target_name, target.statistic) for target in targets]
    if len(set(keys)) != len(keys):
        raise ValueError("raw target registry contains duplicate cells")
    return tuple(sorted(targets, key=lambda target: (target.stratum_id, target.target_name, target.statistic)))


__all__ = [
    "DIAGNOSIS_AGE_SUMMARIES",
    "ENCOUNTER_CATEGORY_SLUGS",
    "ETHNICITY_CATEGORY_SLUGS",
    "LOGICAL_LINK_RESOURCES",
    "MEASUREMENT_AVAILABILITY",
    "PHYSIOLOGY_METRICS",
    "RACE_CATEGORY_SLUGS",
    "RECORDED_FLAGS",
    "SEX_CATEGORY_SLUGS",
    "TARGET_REGISTRY_VERSION",
    "RawTarget",
    "compute_raw_targets",
]

#!/usr/bin/env python3
"""Build an aggregate-only clinical EDA report for the PPOC snapshot.

The source files are read in place and are never copied into the repository.
The script intentionally emits aggregate tables only; it never writes a
patient_id, visit_id, referral_id, or other row-level identifier.
"""

from __future__ import annotations

import math
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import duckdb
import pandas as pd


ROOT = Path(os.environ.get("PPOC_DATA_ROOT", "/Users/joon/w/p3-data/all")).expanduser().resolve()
REPORT = Path(__file__).resolve().parent.parent / "growth-chart-literacy-real-data-eda.md"
TMP = Path("/private/tmp/growth-chart-literacy-eda")


def choose(*names: str) -> Path:
    for name in names:
        path = ROOT / name
        if path.is_file():
            return path
    raise FileNotFoundError(f"None of these files exists under {ROOT}: {names}")


FILES = {
    "patients": choose("patients.csv"),
    "patients_augmented": choose("patients_augmented-20251209150512.csv", "patients_augmented.csv"),
    "visits": choose("visits.csv"),
    "visits_augmented": choose("visits_augmented-20251209150512.csv", "visits_augmented.csv"),
    "labs": choose("labs.csv"),
    "medications": choose("medications.csv"),
    "problem_list": choose("problem_list.csv"),
    "referrals": choose("referrals.csv"),
    "icd10": choose("icd10.csv"),
}

GROWTH_CODES = [
    ("E03.9", "dx_age_years_e03_9", "Hypothyroidism, unspecified"),
    ("E10", "dx_age_years_e10", "Type 1 diabetes mellitus"),
    ("E22.0", "dx_age_years_e22_0", "Acromegaly and pituitary gigantism"),
    ("E23.0", "dx_age_years_e23_0", "Hypopituitarism"),
    ("E23.6", "dx_age_years_e23_6", "Other pituitary-gland disorders"),
    ("E24", "dx_age_years_e24", "Cushing syndrome"),
    ("E30.0", "dx_age_years_e30_0", "Delayed puberty"),
    ("E30.1", "dx_age_years_e30_1", "Precocious puberty"),
    ("E34.3", "dx_age_years_e34_3", "Short stature due to endocrine disorder"),
    ("E34.4", "dx_age_years_e34_4", "Constitutional tall stature"),
    ("E72.11", "dx_age_years_e72_11", "Homocystinuria"),
    ("K50", "dx_age_years_k50", "Crohn disease"),
    ("K51", "dx_age_years_k51", "Ulcerative colitis"),
    ("K90.0", "dx_age_years_k90_0", "Celiac disease"),
    ("N18", "dx_age_years_n18", "Chronic kidney disease"),
    ("N25.0", "dx_age_years_n25_0", "Renal osteodystrophy"),
    ("P04.3", "dx_age_years_p04_3", "Newborn affected by maternal alcohol use"),
    ("P05", "dx_age_years_p05", "Slow fetal growth / fetal malnutrition"),
    ("P07", "dx_age_years_p07", "Short gestation / low birth weight"),
    ("P70", "dx_age_years_p70", "Transitory neonatal carbohydrate disorder"),
    ("P92.6", "dx_age_years_p92_6", "Failure to thrive in newborn"),
    ("Q77", "dx_age_years_q77", "Osteochondrodysplasia"),
    ("Q78.0", "dx_age_years_q78_0", "Osteogenesis imperfecta"),
    ("Q78.1", "dx_age_years_q78_1", "Polyostotic fibrous dysplasia"),
    ("Q87.1", "dx_age_years_q87_1", "Congenital syndrome with short stature"),
    ("Q87.2", "dx_age_years_q87_2", "Congenital syndrome involving limbs"),
    ("Q87.3", "dx_age_years_q87_3", "Congenital syndrome with early overgrowth"),
    ("Q87.4", "dx_age_years_q87_4", "Marfan syndrome"),
    ("Q90", "dx_age_years_q90", "Down syndrome"),
    ("Q96", "dx_age_years_q96", "Turner syndrome"),
    ("Q98.0", "dx_age_years_q98_0", "Klinefelter syndrome, 47 XXY"),
    ("Q98.4", "dx_age_years_q98_4", "Klinefelter syndrome, unspecified"),
    ("Q98.5", "dx_age_years_q98_5", "47 XYY syndrome"),
]

DIAG_COLS = [f"enc_diag_{i}" for i in range(1, 34)]


def sql_quote(path: Path) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def text_expr(column: str) -> str:
    return f"NULLIF(NULLIF(lower(trim(CAST({column} AS VARCHAR))), ''), 'nan')"


def numeric_expr(column: str) -> str:
    return f"TRY_CAST({text_expr(column)} AS DOUBLE)"


def age_band_expr(column: str = "age_in_days") -> str:
    return f"""CASE
        WHEN {column} < 2 * 365.25 THEN '0-<2 years'
        WHEN {column} < 5 * 365.25 THEN '2-<5 years'
        WHEN {column} < 10 * 365.25 THEN '5-<10 years'
        WHEN {column} < 15 * 365.25 THEN '10-<15 years'
        ELSE '15-18 years'
    END"""


def age_band_order(column: str = "age_in_days") -> str:
    return f"""CASE
        WHEN {column} < 2 * 365.25 THEN 1
        WHEN {column} < 5 * 365.25 THEN 2
        WHEN {column} < 10 * 365.25 THEN 3
        WHEN {column} < 15 * 365.25 THEN 4
        ELSE 5
    END"""


def is_missing(column: str) -> str:
    return f"({text_expr(column)} IS NULL)"


def code_count_expr() -> str:
    terms = [f"CASE WHEN {is_missing(col)} THEN 0 ELSE 1 END" for col in DIAG_COLS]
    return " + ".join(terms)


def sql_df(con: duckdb.DuckDBPyConnection, query: str) -> pd.DataFrame:
    return con.execute(query).fetchdf()


def sql_one(con: duckdb.DuckDBPyConnection, query: str) -> dict[str, Any]:
    frame = sql_df(con, query)
    if frame.empty:
        return {}
    return frame.iloc[0].to_dict()


def val(row: dict[str, Any], key: str, default: Any = "NA") -> Any:
    value = row.get(key, default)
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    return value


def fmt_int(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "NA"
    return f"{int(round(float(value))):,}"


def fmt_float(value: Any, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "NA"
    return f"{float(value):,.{digits}f}"


def fmt_pct(value: Any, digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "NA"
    return f"{float(value):.{digits}f}%"


def fmt_year(value: Any, digits: int = 2) -> str:
    return fmt_float(value, digits)


def fmt_days(value: Any, digits: int = 0) -> str:
    return fmt_float(value, digits)


def clean_cell(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "NA"
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text


def md_table(
    frame: pd.DataFrame,
    formatters: dict[str, Callable[[Any], str]] | None = None,
    empty: str = "No rows",
) -> str:
    if frame.empty:
        return empty
    formatters = formatters or {}
    columns = [str(c) for c in frame.columns]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for _, row in frame.iterrows():
        cells = []
        for column in columns:
            value = row[column]
            rendered = formatters.get(column, clean_cell)(value)
            cells.append(clean_cell(rendered))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def percent(numerator: Any, denominator: Any) -> float:
    if denominator in (None, 0) or (isinstance(denominator, float) and math.isnan(denominator)):
        return float("nan")
    return 100.0 * float(numerator) / float(denominator)


def add_pct(frame: pd.DataFrame, numerator: str, denominator: str, name: str = "pct") -> pd.DataFrame:
    frame = frame.copy()
    frame[name] = [percent(n, d) for n, d in zip(frame[numerator], frame[denominator])]
    return frame


def file_metadata(path: Path, rows: Any, grain: str) -> dict[str, Any]:
    stat = path.stat()
    return {
        "resource": path.name,
        "rows": rows,
        "size_mb": stat.st_size / 1_000_000,
        "modified": datetime.fromtimestamp(stat.st_mtime).astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
        "grain": grain,
    }


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(database=":memory:")
    con.execute("PRAGMA threads=4")
    con.execute("PRAGMA memory_limit='8GB'")
    con.execute(f"PRAGMA temp_directory={sql_quote(TMP)}")
    con.execute("PRAGMA enable_progress_bar=false")

    # Load only the columns needed for aggregate EDA. No source data is copied
    # to the repository, and identifiers are used only inside the connection.
    con.execute(
        f"""CREATE TEMP TABLE p AS
        SELECT * FROM read_csv_auto({sql_quote(FILES['patients_augmented'])},
                                    header=true, sample_size=100000)"""
    )
    visit_columns = [
        "patient_id", "visit_id", "sex", "ethnicity", "race_1", "age_in_days", "age_in_months",
        "age_in_years", "weight_oz", "weight_kg", "weight_outlier_flag", "weight_velocity",
        "weight_z_score", "weight_for_length_z_score", "weight_for_stature_z_score", "wasting_flag",
        "height_in", "height_cm", "height_outlier_flag", "height_velocity", "height_velocity_z_score",
        "height_velocity_percentile", "height_z_score", "height_percentile", "stunting_flag",
        "head_circ_cm", "head_circ_z_score", "head_circ_percentile", "bmi", "bmi_z_score",
        "bmi_percentile", "bmi_category", "underweight_flag", "obesity_flag", "encounter_type",
        "orig_enc_source_Epic_yn", *DIAG_COLS,
    ]
    con.execute(
        f"""CREATE TEMP TABLE v AS
        SELECT {', '.join(visit_columns)}
        FROM read_csv_auto({sql_quote(FILES['visits_augmented'])},
                           header=true, sample_size=100000)"""
    )
    con.execute(
        f"""CREATE TEMP TABLE r AS
        SELECT patient_id, visit_id, referral_id, referral_date_age_in_days,
               requested_specialty, referral_number_of_visits
        FROM read_csv_auto({sql_quote(FILES['referrals'])}, header=true, sample_size=100000)"""
    )
    con.execute(
        f"""CREATE TEMP TABLE pl AS
        SELECT patient_id, problem_list_id, noted_date_age_in_days,
               resolved_date_age_in_days, pl_diag
        FROM read_csv_auto({sql_quote(FILES['problem_list'])}, header=true, sample_size=100000)"""
    )
    con.execute(
        f"""CREATE TEMP TABLE icd AS
        SELECT upper(trim(CAST(code AS VARCHAR))) AS code, max(description) AS description
        FROM read_csv_auto({sql_quote(FILES['icd10'])}, header=true, sample_size=100000)
        GROUP BY 1"""
    )

    p_n = sql_one(con, "SELECT count(*) AS n_rows, count(DISTINCT patient_id) AS n_patients FROM p")
    v_n = sql_one(
        con,
        """SELECT count(*) AS n_rows, count(DISTINCT patient_id) AS n_patients,
                  count(DISTINCT visit_id) AS n_visits,
                  min(age_in_days) AS min_age_days, max(age_in_days) AS max_age_days
           FROM v""",
    )
    r_n = sql_one(
        con,
        """SELECT count(*) AS n_rows, count(DISTINCT patient_id) AS n_patients,
                  count(DISTINCT referral_id) AS n_referrals,
                  min(referral_date_age_in_days) AS min_age_days,
                  max(referral_date_age_in_days) AS max_age_days
           FROM r""",
    )
    pl_n = sql_one(
        con,
        """SELECT count(*) AS n_rows, count(DISTINCT patient_id) AS n_patients,
                  count(DISTINCT problem_list_id) AS n_problem_entries
           FROM pl""",
    )

    # The lab CSV contains a small number of malformed records that trigger a
    # DuckDB CSV-parser assertion when result_value is materialized. Keep a
    # projection-only source count for the inventory, and use an all-text,
    # ignore-errors reader for field-level aggregates. The difference is
    # reported so that missingness percentages are not presented as complete.
    labs_source_rows = sql_one(
        con,
        f"SELECT count(*) AS n_rows FROM read_csv_auto({sql_quote(FILES['labs'])}, header=true, sample_size=100000)",
    )["n_rows"]
    labs_reader = f"read_csv_auto({sql_quote(FILES['labs'])}, header=true, sample_size=100000, all_varchar=true, ignore_errors=true)"

    labs_overall_query = f"""
        SELECT grouping(lab_procedure_name) AS is_total,
               lab_procedure_name,
               count(*) AS n_rows,
               count(DISTINCT patient_id) AS n_patients,
               count(DISTINCT lab_order_id) AS n_orders,
               count(DISTINCT result_component_name) AS n_components,
               sum(CASE WHEN {text_expr('result_loinc_code')} IS NOT NULL THEN 1 ELSE 0 END) AS loinc_present,
               sum(CASE WHEN {text_expr('result_value')} IS NOT NULL THEN 1 ELSE 0 END) AS result_present,
               sum(CASE WHEN {text_expr('result_flag')} IS NOT NULL THEN 1 ELSE 0 END) AS flag_present,
               sum(CASE WHEN {text_expr('visit_id')} IS NOT NULL THEN 1 ELSE 0 END) AS visit_id_present
        FROM {labs_reader}
        GROUP BY GROUPING SETS ((), (lab_procedure_name))
    """
    labs_grouped = sql_df(con, labs_overall_query)
    labs_total = labs_grouped[labs_grouped["is_total"] == 1].iloc[0].to_dict()
    labs_top = labs_grouped[labs_grouped["is_total"] == 0].sort_values("n_rows", ascending=False).head(15)

    meds_grouped = sql_df(
        con,
        f"""
        SELECT grouping(med_simple_generic_name) AS is_name_total,
               grouping(med_record_type) AS is_type_total,
               med_simple_generic_name, med_record_type,
               count(*) AS n_rows, count(DISTINCT patient_id) AS n_patients,
               sum(CASE WHEN {text_expr('med_order_date_age_in_days')} IS NOT NULL THEN 1 ELSE 0 END) AS order_date_present,
               sum(CASE WHEN {text_expr('med_start_date_age_in_days')} IS NOT NULL THEN 1 ELSE 0 END) AS start_date_present,
               sum(CASE WHEN {text_expr('med_end_date_age_in_days')} IS NOT NULL THEN 1 ELSE 0 END) AS end_date_present
        FROM read_csv_auto({sql_quote(FILES['medications'])}, header=true, sample_size=100000)
        GROUP BY GROUPING SETS ((), (med_simple_generic_name), (med_record_type))
        """,
    )
    meds_total = meds_grouped[(meds_grouped["is_name_total"] == 1) & (meds_grouped["is_type_total"] == 1)].iloc[0].to_dict()
    meds_top = meds_grouped[(meds_grouped["is_name_total"] == 0) & (meds_grouped["is_type_total"] == 1)].sort_values("n_rows", ascending=False).head(15)
    meds_types = meds_grouped[(meds_grouped["is_name_total"] == 1) & (meds_grouped["is_type_total"] == 0)].sort_values("n_rows", ascending=False)

    pl_grouped = sql_df(
        con,
        f"""
        SELECT grouping(pl_diag) AS is_total, pl_diag,
               count(*) AS n_rows, count(DISTINCT patient_id) AS n_patients,
               sum(CASE WHEN {text_expr('resolved_date_age_in_days')} IS NOT NULL THEN 1 ELSE 0 END) AS resolved_present
        FROM pl
        GROUP BY GROUPING SETS ((), (pl_diag))
        """,
    )
    pl_total = pl_grouped[pl_grouped["is_total"] == 1].iloc[0].to_dict()
    pl_top = pl_grouped[pl_grouped["is_total"] == 0].sort_values("n_rows", ascending=False).head(15)

    patient_sex = sql_df(
        con,
        f"""SELECT COALESCE(NULLIF(trim(CAST(sex AS VARCHAR)), ''), '[blank]') AS category,
                  count(*) AS patients
           FROM p GROUP BY 1 ORDER BY patients DESC""",
    )
    patient_sex = add_pct(patient_sex, "patients", "patients", "pct")
    patient_sex["pct"] = 100.0 * patient_sex["patients"] / float(val(p_n, "n_rows"))

    ethnicity_case = f"""CASE
        WHEN {text_expr('ethnicity')} IS NULL
          OR lower(trim(CAST(ethnicity AS VARCHAR))) IN
             ('unknown', 'choose not to answer', 'unable to collect', 'patient does not know')
          THEN 'Missing / non-response'
        ELSE trim(CAST(ethnicity AS VARCHAR))
    END"""
    ethnicity = sql_df(con, f"SELECT {ethnicity_case} AS category, count(*) AS patients FROM p GROUP BY 1 ORDER BY patients DESC")
    ethnicity["pct"] = 100.0 * ethnicity["patients"] / float(val(p_n, "n_rows"))

    race_case = f"""CASE
        WHEN {text_expr('race_1')} IS NULL
          OR lower(trim(CAST(race_1 AS VARCHAR))) IN
             ('unknown', 'choose not to answer', 'unable to collect', 'patient does not know')
          THEN 'Missing / non-response'
        ELSE trim(CAST(race_1 AS VARCHAR))
    END"""
    race = sql_df(con, f"SELECT {race_case} AS category, count(*) AS patients FROM p GROUP BY 1 ORDER BY patients DESC")
    race["pct"] = 100.0 * race["patients"] / float(val(p_n, "n_rows"))

    multiple_race_expr = " + ".join(
        f"CASE WHEN {text_expr(f'race_{i}')} IS NOT NULL THEN 1 ELSE 0 END" for i in range(2, 9)
    )
    multiple_race = sql_one(
        con,
        f"""SELECT count(*) AS patients,
                  sum(CASE WHEN ({multiple_race_expr}) > 0 THEN 1 ELSE 0 END) AS multiple_race,
                  sum(CASE WHEN {text_expr('race_1')} IS NULL AND ({multiple_race_expr}) > 0 THEN 1 ELSE 0 END) AS race1_blank_with_later_value
           FROM p""",
    )

    patient_observation = sql_one(
        con,
        """SELECT count(*) AS patients,
                  median(visits_count) AS median_visits,
                  quantile_cont(visits_count, 0.25) AS visits_p25,
                  quantile_cont(visits_count, 0.75) AS visits_p75,
                  min(visits_count) AS visits_min, max(visits_count) AS visits_max,
                  median(visits_span_days) AS median_span_days,
                  quantile_cont(visits_span_days, 0.25) AS span_p25,
                  quantile_cont(visits_span_days, 0.75) AS span_p75,
                  median(min_visit_age_days) AS median_first_age_days,
                  median(max_visit_age_days) AS median_last_age_days,
                  max(max_visit_age_days) AS max_last_age_days
           FROM p""",
    )
    patient_entry = sql_df(
        con,
        f"""SELECT {age_band_expr('min_visit_age_days')} AS age_band,
                  count(*) AS patients,
                  median(visits_count) AS median_visits,
                  median(visits_span_days) / 365.25 AS median_span_years
           FROM p WHERE min_visit_age_days IS NOT NULL
           GROUP BY 1 ORDER BY MIN(min_visit_age_days)""",
    )

    p_flags = sql_df(
        con,
        """SELECT flag, patients
           FROM (
             SELECT 'growth_dx_flag' AS flag, sum(CASE WHEN growth_dx_flag = 1 THEN 1 ELSE 0 END) AS patients FROM p
             UNION ALL SELECT 'chronic_dx_flag', sum(CASE WHEN chronic_dx_flag = 1 THEN 1 ELSE 0 END) FROM p
             UNION ALL SELECT 'ever_stunting_flag', sum(CASE WHEN ever_stunting_flag = 1 THEN 1 ELSE 0 END) FROM p
             UNION ALL SELECT 'ever_wasting_flag', sum(CASE WHEN ever_wasting_flag = 1 THEN 1 ELSE 0 END) FROM p
             UNION ALL SELECT 'ever_underweight_flag', sum(CASE WHEN ever_underweight_flag = 1 THEN 1 ELSE 0 END) FROM p
             UNION ALL SELECT 'ever_obesity_flag', sum(CASE WHEN ever_obesity_flag = 1 THEN 1 ELSE 0 END) FROM p
             UNION ALL SELECT 'healthy_flag', sum(CASE WHEN healthy_flag = 1 THEN 1 ELSE 0 END) FROM p
           ) x""",
    )
    p_flags["pct"] = 100.0 * p_flags["patients"] / float(val(p_n, "n_rows"))
    p_flag_overlap = sql_df(
        con,
        """SELECT CASE
                  WHEN growth_dx_flag = 1 AND healthy_flag = 1 THEN 'both growth and healthy (inconsistent)'
                  WHEN growth_dx_flag = 1 THEN 'growth diagnosis flag only'
                  WHEN healthy_flag = 1 THEN 'healthy flag only'
                  ELSE 'neither'
                END AS group_label, count(*) AS patients
           FROM p GROUP BY 1 ORDER BY patients DESC""",
    )
    p_flag_overlap["pct"] = 100.0 * p_flag_overlap["patients"] / float(val(p_n, "n_rows"))

    visit_age = sql_df(
        con,
        f"""SELECT {age_band_expr()} AS age_band,
                  count(*) AS visits, count(DISTINCT patient_id) AS patients,
                  sum(CASE WHEN {text_expr('height_cm')} IS NOT NULL THEN 1 ELSE 0 END) AS height_present,
                  sum(CASE WHEN {text_expr('weight_kg')} IS NOT NULL THEN 1 ELSE 0 END) AS weight_present,
                  sum(CASE WHEN {text_expr('bmi')} IS NOT NULL THEN 1 ELSE 0 END) AS bmi_present,
                  sum(CASE WHEN {text_expr('head_circ_cm')} IS NOT NULL THEN 1 ELSE 0 END) AS head_circ_present,
                  sum(CASE WHEN {code_count_expr()} > 0 THEN 1 ELSE 0 END) AS any_diagnosis
           FROM v GROUP BY 1 ORDER BY MIN(age_in_days)""",
    )
    for col in ["height_present", "weight_present", "bmi_present", "head_circ_present", "any_diagnosis"]:
        visit_age[f"{col}_pct"] = 100.0 * visit_age[col] / visit_age["visits"]

    source_summary = sql_df(
        con,
        f"""SELECT COALESCE(NULLIF(trim(CAST(orig_enc_source_Epic_yn AS VARCHAR)), ''), '[blank]') AS source,
                  count(*) AS visits,
                  sum(CASE WHEN {text_expr('height_cm')} IS NOT NULL THEN 1 ELSE 0 END) AS height_present,
                  sum(CASE WHEN {text_expr('weight_kg')} IS NOT NULL THEN 1 ELSE 0 END) AS weight_present,
                  sum(CASE WHEN {code_count_expr()} > 0 THEN 1 ELSE 0 END) AS any_diagnosis,
                  sum(CASE WHEN {text_expr('bmi')} IS NOT NULL THEN 1 ELSE 0 END) AS bmi_present
           FROM v GROUP BY 1 ORDER BY visits DESC""",
    )
    for col in ["height_present", "weight_present", "any_diagnosis", "bmi_present"]:
        source_summary[f"{col}_pct"] = 100.0 * source_summary[col] / source_summary["visits"]

    encounter_types = sql_df(
        con,
        """SELECT COALESCE(NULLIF(trim(CAST(encounter_type AS VARCHAR)), ''), '[blank]') AS encounter_type,
                  count(*) AS visits, count(DISTINCT patient_id) AS patients
           FROM v GROUP BY 1 ORDER BY visits DESC LIMIT 15""",
    )
    encounter_types["pct_visits"] = 100.0 * encounter_types["visits"] / float(val(v_n, "n_rows"))

    diagnosis_completeness = sql_one(
        con,
        f"""SELECT count(*) AS visits,
                  sum(CASE WHEN {code_count_expr()} = 0 THEN 1 ELSE 0 END) AS no_diagnosis,
                  sum(CASE WHEN {code_count_expr()} >= 1 THEN 1 ELSE 0 END) AS one_or_more,
                  median({code_count_expr()}) AS median_code_slots,
                  quantile_cont({code_count_expr()}, 0.95) AS p95_code_slots,
                  max({code_count_expr()}) AS max_code_slots
           FROM v""",
    )

    channels = [
        ("weight_kg", "weight_kg", "kg"),
        ("height_cm", "height_cm", "cm"),
        ("bmi", "bmi", "kg/m^2"),
        ("head_circ_cm", "head_circ_cm", "cm"),
        ("weight_z_score", "weight_z_score", "z"),
        ("height_z_score", "height_z_score", "z"),
        ("bmi_z_score", "bmi_z_score", "z"),
        ("weight_for_length_z_score", "weight_for_length_z_score", "z"),
        ("weight_for_stature_z_score", "weight_for_stature_z_score", "z"),
        ("head_circ_z_score", "head_circ_z_score", "z"),
        ("height_velocity", "height_velocity", "cm/year"),
        ("weight_velocity", "weight_velocity", "kg/year"),
    ]
    channel_union = []
    for label, column, unit in channels:
        channel_union.append(
            f"""SELECT '{label}' AS channel, '{unit}' AS unit,
                       count({column}) AS n,
                       min({column}) AS minimum,
                       quantile_cont({column}, 0.001) AS p001,
                       quantile_cont({column}, 0.01) AS p01,
                       quantile_cont({column}, 0.05) AS p05,
                       median({column}) AS median,
                       quantile_cont({column}, 0.95) AS p95,
                       quantile_cont({column}, 0.99) AS p99,
                       quantile_cont({column}, 0.999) AS p999,
                       max({column}) AS maximum
                FROM v WHERE {column} IS NOT NULL AND isfinite(CAST({column} AS DOUBLE))"""
        )
    channel_summary = sql_df(con, " UNION ALL ".join(channel_union))

    data_quality = sql_one(
        con,
        f"""SELECT count(*) AS visits,
                  sum(CASE WHEN {text_expr('weight_oz')} IS NOT NULL AND {text_expr('weight_kg')} IS NULL THEN 1 ELSE 0 END) AS raw_weight_without_derived,
                  sum(CASE WHEN {text_expr('height_in')} IS NOT NULL AND {text_expr('height_cm')} IS NULL THEN 1 ELSE 0 END) AS raw_height_without_derived,
                  sum(CASE WHEN weight_z_score IS NOT NULL AND abs(weight_z_score) > 5 THEN 1 ELSE 0 END) AS weight_z_beyond_5,
                  sum(CASE WHEN height_z_score IS NOT NULL AND (height_z_score < -5 OR height_z_score > 5) THEN 1 ELSE 0 END) AS height_z_beyond_5,
                  sum(CASE WHEN bmi_z_score IS NOT NULL AND abs(bmi_z_score) > 5 THEN 1 ELSE 0 END) AS bmi_z_beyond_5,
                  sum(CASE WHEN weight_for_length_z_score IS NOT NULL AND abs(weight_for_length_z_score) > 5 THEN 1 ELSE 0 END) AS wfl_z_beyond_5,
                  sum(CASE WHEN weight_for_stature_z_score IS NOT NULL AND abs(weight_for_stature_z_score) > 5 THEN 1 ELSE 0 END) AS wfs_z_beyond_5,
                  sum(CASE WHEN head_circ_z_score IS NOT NULL AND abs(head_circ_z_score) > 5 THEN 1 ELSE 0 END) AS hc_z_beyond_5,
                  sum(CASE WHEN head_circ_cm IS NOT NULL AND (head_circ_cm < 25 OR head_circ_cm > 65) THEN 1 ELSE 0 END) AS hc_cm_outside_25_65,
                  sum(CASE WHEN bmi IS NOT NULL AND (bmi < 8 OR bmi > 60) THEN 1 ELSE 0 END) AS bmi_outside_8_60,
                  sum(CASE WHEN weight_outlier_flag = 1 THEN 1 ELSE 0 END) AS weight_outlier_flagged,
                  sum(CASE WHEN height_outlier_flag = 1 THEN 1 ELSE 0 END) AS height_outlier_flagged
           FROM v""",
    )
    bmi_consistency = sql_one(
        con,
        f"""WITH q AS (
             SELECT abs(bmi - weight_kg / pow(height_cm / 100.0, 2)) AS abs_diff
             FROM v
             WHERE age_in_days >= 2 * 365.25
               AND bmi IS NOT NULL AND weight_kg IS NOT NULL AND height_cm IS NOT NULL
               AND height_cm > 0 AND isfinite(bmi)
               AND isfinite(weight_kg) AND isfinite(height_cm)
           )
           SELECT count(*) AS n,
                  median(abs_diff) AS median_abs_diff,
                  quantile_cont(abs_diff, 0.95) AS p95_abs_diff,
                  sum(CASE WHEN abs_diff > 0.1 THEN 1 ELSE 0 END) AS diff_gt_0_1
           FROM q""",
    )
    flag_consistency = sql_one(
        con,
        """SELECT
           sum(CASE WHEN height_z_score IS NOT NULL AND
                         stunting_flag != CASE WHEN height_z_score < -2 THEN 1 ELSE 0 END THEN 1 ELSE 0 END) AS stunting_discordant,
           sum(CASE WHEN bmi_percentile IS NOT NULL AND
                         underweight_flag != CASE WHEN bmi_percentile < 5 THEN 1 ELSE 0 END THEN 1 ELSE 0 END) AS underweight_discordant,
           sum(CASE WHEN bmi_percentile IS NOT NULL AND
                         obesity_flag != CASE WHEN bmi_percentile >= 95 THEN 1 ELSE 0 END THEN 1 ELSE 0 END) AS obesity_discordant,
           sum(CASE WHEN (weight_for_length_z_score IS NOT NULL OR weight_for_stature_z_score IS NOT NULL) AND
                         wasting_flag != CASE WHEN coalesce(weight_for_length_z_score < -2, false)
                                                   OR coalesce(weight_for_stature_z_score < -2, false) THEN 1 ELSE 0 END THEN 1 ELSE 0 END) AS wasting_discordant
           FROM v""",
    )
    bmi_categories = sql_df(
        con,
        """SELECT COALESCE(NULLIF(trim(CAST(bmi_category AS VARCHAR)), ''), '[blank]') AS category,
                  count(*) AS visits, count(DISTINCT patient_id) AS patients
           FROM v WHERE age_in_days >= 2 * 365.25 AND bmi_percentile IS NOT NULL
           GROUP BY 1 ORDER BY visits DESC""",
    )
    bmi_categories["pct_visits"] = 100.0 * bmi_categories["visits"] / float(bmi_categories["visits"].sum())

    height_patient_all = sql_one(
        con,
        """WITH s AS (
             SELECT patient_id, count(*) FILTER (WHERE height_z_score IS NOT NULL) AS n_heights,
                    min(age_in_days) FILTER (WHERE height_z_score IS NOT NULL) AS first_height_age_days,
                    max(age_in_days) FILTER (WHERE height_z_score IS NOT NULL) AS last_height_age_days
             FROM v GROUP BY patient_id
           )
           SELECT count(*) AS patients,
                  sum(CASE WHEN n_heights >= 1 THEN 1 ELSE 0 END) AS with_height,
                  sum(CASE WHEN n_heights >= 3 THEN 1 ELSE 0 END) AS with_3_heights,
                  sum(CASE WHEN n_heights >= 5 THEN 1 ELSE 0 END) AS with_5_heights,
                  median(n_heights) AS median_heights,
                  quantile_cont(n_heights, 0.25) AS heights_p25,
                  quantile_cont(n_heights, 0.75) AS heights_p75,
                  median(last_height_age_days - first_height_age_days) AS median_height_span_days
           FROM s""",
    )
    height_patient_age2 = sql_one(
        con,
        """WITH s AS (
             SELECT patient_id, count(*) FILTER (WHERE age_in_days >= 2 * 365.25 AND height_z_score IS NOT NULL) AS n_heights,
                    min(age_in_days) FILTER (WHERE age_in_days >= 2 * 365.25 AND height_z_score IS NOT NULL) AS first_height_age_days,
                    max(age_in_days) FILTER (WHERE age_in_days >= 2 * 365.25 AND height_z_score IS NOT NULL) AS last_height_age_days
             FROM v GROUP BY patient_id
           )
           SELECT count(*) AS patients,
                  sum(CASE WHEN n_heights >= 1 THEN 1 ELSE 0 END) AS with_height,
                  sum(CASE WHEN n_heights >= 3 THEN 1 ELSE 0 END) AS with_3_heights,
                  sum(CASE WHEN n_heights >= 5 THEN 1 ELSE 0 END) AS with_5_heights,
                  median(n_heights) FILTER (WHERE n_heights >= 1) AS median_heights_with_any,
                  median(last_height_age_days - first_height_age_days) AS median_height_span_days
           FROM s""",
    )
    height_gaps = sql_one(
        con,
        """WITH ordered AS (
             SELECT patient_id, age_in_days,
                    lag(age_in_days) OVER (PARTITION BY patient_id ORDER BY age_in_days) AS previous_age
             FROM v WHERE age_in_days >= 2 * 365.25 AND height_z_score IS NOT NULL
           ), gaps AS (
             SELECT age_in_days - previous_age AS gap_days FROM ordered WHERE previous_age IS NOT NULL
           )
           SELECT count(*) AS height_pairs,
                  median(gap_days) AS median_gap_days,
                  quantile_cont(gap_days, 0.25) AS gap_p25,
                  quantile_cont(gap_days, 0.75) AS gap_p75,
                  quantile_cont(gap_days, 0.95) AS gap_p95,
                  sum(CASE WHEN gap_days > 730.5 THEN 1 ELSE 0 END) AS gaps_gt_2_years,
                  max(gap_days) AS max_gap_days
           FROM gaps""",
    )
    autocorrelation = sql_one(
        con,
        """WITH ordered AS (
             SELECT patient_id, age_in_days, height_z_score,
                    lag(height_z_score) OVER (PARTITION BY patient_id ORDER BY age_in_days) AS previous_height_z
             FROM v WHERE age_in_days >= 2 * 365.25 AND height_z_score IS NOT NULL
           )
           SELECT count(*) AS pairs, corr(height_z_score, previous_height_z) AS lag1_autocorrelation
           FROM ordered WHERE previous_height_z IS NOT NULL""",
    )
    variance_components = sql_one(
        con,
        """WITH per_patient AS (
             SELECT patient_id, avg(height_z_score) AS patient_mean,
                    stddev_samp(height_z_score) AS patient_sd
             FROM v WHERE age_in_days >= 2 * 365.25 AND height_z_score IS NOT NULL
             GROUP BY patient_id HAVING count(*) >= 5
           )
           SELECT count(*) AS patients,
                  stddev_samp(patient_mean) AS between_patient_sd,
                  median(patient_sd) AS median_within_patient_sd,
                  quantile_cont(patient_sd, 0.25) AS within_sd_p25,
                  quantile_cont(patient_sd, 0.75) AS within_sd_p75
           FROM per_patient""",
    )

    growth_profile = sql_df(
        con,
        f"""SELECT {age_band_expr()} AS age_band,
                  COALESCE(NULLIF(trim(CAST(sex AS VARCHAR)), ''), '[unknown]') AS sex,
                  count(*) AS visits,
                  count(height_z_score) AS height_n,
                  median(height_z_score) AS height_z_median,
                  quantile_cont(height_z_score, 0.25) AS height_z_p25,
                  quantile_cont(height_z_score, 0.75) AS height_z_p75,
                  100.0 * sum(CASE WHEN height_z_score < -2 THEN 1 ELSE 0 END) / count(height_z_score) AS height_z_lt_minus2_pct,
                  100.0 * sum(CASE WHEN height_z_score > 2 THEN 1 ELSE 0 END) / count(height_z_score) AS height_z_gt_plus2_pct,
                  count(bmi_percentile) AS bmi_n,
                  median(bmi_percentile) AS bmi_percentile_median,
                  100.0 * sum(CASE WHEN bmi_percentile < 5 THEN 1 ELSE 0 END) / count(bmi_percentile) AS bmi_lt5_pct,
                  100.0 * sum(CASE WHEN bmi_percentile >= 95 THEN 1 ELSE 0 END) / count(bmi_percentile) AS bmi_ge95_pct
           FROM v
           WHERE age_in_days >= 2 * 365.25
           GROUP BY 1, 2
           ORDER BY MIN(age_in_days), sex""",
    )
    patient_growth_age2 = sql_df(
        con,
        """WITH per_patient AS (
             SELECT patient_id,
                    max(CASE WHEN age_in_days >= 2 * 365.25 AND height_z_score IS NOT NULL THEN 1 ELSE 0 END) AS has_height,
                    max(CASE WHEN age_in_days >= 2 * 365.25 AND height_z_score < -2 THEN 1 ELSE 0 END) AS ever_stunting,
                    max(CASE WHEN age_in_days >= 2 * 365.25 AND (weight_for_length_z_score < -2 OR weight_for_stature_z_score < -2) THEN 1 ELSE 0 END) AS ever_wasting,
                    max(CASE WHEN age_in_days >= 2 * 365.25 AND bmi_percentile IS NOT NULL THEN 1 ELSE 0 END) AS has_bmi,
                    max(CASE WHEN age_in_days >= 2 * 365.25 AND bmi_percentile < 5 THEN 1 ELSE 0 END) AS ever_underweight,
                    max(CASE WHEN age_in_days >= 2 * 365.25 AND bmi_percentile >= 95 THEN 1 ELSE 0 END) AS ever_obesity,
                    any_value(COALESCE(NULLIF(trim(CAST(sex AS VARCHAR)), ''), '[unknown]')) AS sex
             FROM v GROUP BY patient_id
           )
           SELECT sex, count(*) AS patients,
                  sum(has_height) AS patients_with_height,
                  sum(ever_stunting) AS patients_ever_stunting,
                  sum(ever_wasting) AS patients_ever_wasting,
                  sum(has_bmi) AS patients_with_bmi,
                  sum(ever_underweight) AS patients_ever_underweight,
                  sum(ever_obesity) AS patients_ever_obesity
           FROM per_patient GROUP BY sex ORDER BY sex""",
    )

    growth_age = numeric_expr("dx_age_years")
    growth_age_summary = sql_one(
        con,
        f"""SELECT sum(CASE WHEN growth_dx_flag = 1 THEN 1 ELSE 0 END) AS growth_flag_patients,
                  sum(CASE WHEN growth_dx_flag = 1 AND {growth_age} IS NOT NULL THEN 1 ELSE 0 END) AS growth_flag_with_age,
                  median({growth_age}) FILTER (WHERE growth_dx_flag = 1 AND {growth_age} IS NOT NULL AND isfinite({growth_age})) AS median_dx_age_years,
                  sum(CASE WHEN growth_dx_flag = 1 AND {growth_age} BETWEEN 0 AND 1.0/12.0 THEN 1 ELSE 0 END) AS dx_in_first_month,
                  sum(CASE WHEN growth_dx_flag = 1 AND {growth_age} BETWEEN 0 AND 1 THEN 1 ELSE 0 END) AS dx_in_first_year,
                  sum(CASE WHEN growth_dx_flag = 1 AND {growth_age} < 0 THEN 1 ELSE 0 END) AS negative_dx_age
           FROM p""",
    )
    growth_code_union = []
    for code, field, description in GROWTH_CODES:
        expr = numeric_expr(field)
        growth_code_union.append(
            f"""SELECT '{code}' AS code, '{description.replace("'", "''")}' AS description,
                       count(*) FILTER (WHERE {expr} IS NOT NULL AND isfinite({expr})) AS patients,
                       median({expr}) FILTER (WHERE {expr} IS NOT NULL AND isfinite({expr})) AS median_age_years
                FROM p"""
        )
    growth_codes = sql_df(con, " UNION ALL ".join(growth_code_union))
    growth_codes["pct_growth_flag"] = 100.0 * growth_codes["patients"] / float(val(growth_age_summary, "growth_flag_patients"))
    growth_codes = growth_codes.sort_values("patients", ascending=False)

    top_primary_dx = sql_df(
        con,
        f"""WITH d AS (
             SELECT upper(trim(CAST(enc_diag_1 AS VARCHAR))) AS code,
                    count(*) AS visits, count(DISTINCT patient_id) AS patients
             FROM v WHERE {text_expr('enc_diag_1')} IS NOT NULL
             GROUP BY 1 ORDER BY visits DESC LIMIT 20
           )
           SELECT d.code, COALESCE(i.description, '[not in ICD-10 lookup]') AS description,
                  d.visits, d.patients
           FROM d LEFT JOIN icd i USING (code)
           ORDER BY d.visits DESC""",
    )
    top_problem_dx = sql_df(
        con,
        f"""WITH d AS (
             SELECT upper(trim(CAST(pl_diag AS VARCHAR))) AS code,
                    count(*) AS entries, count(DISTINCT patient_id) AS patients
             FROM pl WHERE {text_expr('pl_diag')} IS NOT NULL
             GROUP BY 1 ORDER BY entries DESC LIMIT 20
           )
           SELECT d.code, COALESCE(i.description, '[not in ICD-10 lookup]') AS description,
                  d.entries, d.patients
           FROM d LEFT JOIN icd i USING (code)
           ORDER BY d.entries DESC""",
    )

    referral_overall = sql_one(
        con,
        f"""SELECT count(*) AS referrals, count(DISTINCT patient_id) AS patients,
                  count(DISTINCT referral_id) AS unique_referral_ids,
                  sum(CASE WHEN {text_expr('requested_specialty')} IS NULL THEN 1 ELSE 0 END) AS specialty_missing,
                  sum(CASE WHEN {text_expr('visit_id')} IS NULL THEN 1 ELSE 0 END) AS visit_id_missing,
                  sum(CASE WHEN {text_expr('referral_number_of_visits')} IS NULL THEN 1 ELSE 0 END) AS visit_count_missing,
                  median(referral_date_age_in_days) / 365.25 AS median_referral_age_years,
                  quantile_cont(referral_date_age_in_days, 0.25) / 365.25 AS referral_age_p25_years,
                  quantile_cont(referral_date_age_in_days, 0.75) / 365.25 AS referral_age_p75_years
           FROM r""",
    )
    referral_specialties = sql_df(
        con,
        f"""SELECT COALESCE(NULLIF(trim(CAST(requested_specialty AS VARCHAR)), ''), '[blank]') AS specialty,
                  count(*) AS referrals, count(DISTINCT patient_id) AS patients,
                  median(referral_date_age_in_days) / 365.25 AS median_age_years
           FROM r GROUP BY 1 ORDER BY referrals DESC LIMIT 20""",
    )
    referral_specialties["pct_referrals"] = 100.0 * referral_specialties["referrals"] / float(val(referral_overall, "referrals"))
    referral_age = sql_df(
        con,
        f"""SELECT {age_band_expr('referral_date_age_in_days')} AS age_band,
                  count(*) AS referrals, count(DISTINCT patient_id) AS patients
           FROM r GROUP BY 1 ORDER BY MIN(referral_date_age_in_days)""",
    )
    referral_visits = sql_df(
        con,
        f"""SELECT COALESCE(CAST(referral_number_of_visits AS VARCHAR), '[missing]') AS recorded_visits,
                  count(*) AS referrals
           FROM r GROUP BY 1 ORDER BY CASE WHEN recorded_visits = '[missing]' THEN 999 ELSE try_cast(recorded_visits AS INTEGER) END""",
    )
    referral_focus = sql_df(
        con,
        f"""SELECT CASE
                    WHEN lower(CAST(requested_specialty AS VARCHAR)) LIKE '%endocrin%' THEN 'Endocrinology family'
                    WHEN lower(CAST(requested_specialty AS VARCHAR)) LIKE '%gastroenter%' THEN 'Gastroenterology family'
                    WHEN lower(CAST(requested_specialty AS VARCHAR)) LIKE '%nutrition%'
                      OR lower(CAST(requested_specialty AS VARCHAR)) LIKE '%dietitian%' THEN 'Nutrition family'
                    WHEN lower(CAST(requested_specialty AS VARCHAR)) LIKE '%nephrolog%' THEN 'Nephrology family'
                    WHEN lower(CAST(requested_specialty AS VARCHAR)) LIKE '%genetic%' THEN 'Genetics family'
                    ELSE 'Other / unspecified'
                  END AS specialty_family,
                  count(*) AS referrals, count(DISTINCT patient_id) AS patients,
                  median(referral_date_age_in_days) / 365.25 AS median_age_years
           FROM r GROUP BY 1 ORDER BY referrals DESC""",
    )
    referral_linkage = sql_one(
        con,
        f"""SELECT count(*) AS referrals,
                  sum(CASE WHEN {text_expr('patient_id')} IS NOT NULL AND patient_id IN (SELECT patient_id FROM p) THEN 1 ELSE 0 END) AS patient_id_resolves,
                  sum(CASE WHEN {text_expr('visit_id')} IS NOT NULL AND visit_id IN (SELECT visit_id FROM v) THEN 1 ELSE 0 END) AS visit_id_resolves
           FROM r""",
    )
    referred_patient_distribution = sql_one(
        con,
        """WITH s AS (SELECT patient_id, count(*) AS referrals FROM r GROUP BY patient_id)
           SELECT count(*) AS referred_patients, median(referrals) AS median_referrals_per_patient,
                  quantile_cont(referrals, 0.75) AS referrals_p75,
                  max(referrals) AS max_referrals_per_patient
           FROM s""",
    )

    labs_linkage = sql_one(
        con,
        f"""SELECT count(*) AS rows,
                  sum(CASE WHEN patient_id IN (SELECT patient_id FROM p) THEN 1 ELSE 0 END) AS patient_id_resolves
           FROM {labs_reader}""",
    )
    meds_linkage = sql_one(
        con,
        f"""SELECT count(*) AS rows,
                  sum(CASE WHEN patient_id IN (SELECT patient_id FROM p) THEN 1 ELSE 0 END) AS patient_id_resolves
           FROM read_csv_auto({sql_quote(FILES['medications'])}, header=true, sample_size=100000)""",
    )
    pl_linkage = sql_one(
        con,
        """SELECT count(*) AS rows,
                  sum(CASE WHEN patient_id IN (SELECT patient_id FROM p) THEN 1 ELSE 0 END) AS patient_id_resolves
           FROM pl""",
    )

    inventory = pd.DataFrame(
        [
            file_metadata(FILES["patients"], sql_one(con, f"SELECT count(*) AS n FROM read_csv_auto({sql_quote(FILES['patients'])}, header=true, sample_size=100000)")["n"], "patient"),
            file_metadata(FILES["patients_augmented"], p_n["n_rows"], "patient"),
            file_metadata(FILES["visits"], sql_one(con, f"SELECT count(*) AS n FROM read_csv_auto({sql_quote(FILES['visits'])}, header=true, sample_size=100000)")["n"], "visit"),
            file_metadata(FILES["visits_augmented"], v_n["n_rows"], "visit"),
            file_metadata(FILES["labs"], labs_source_rows, "result component"),
            file_metadata(FILES["medications"], meds_total["n_rows"], "medication record"),
            file_metadata(FILES["problem_list"], pl_total["n_rows"], "problem-list entry"),
            file_metadata(FILES["referrals"], r_n["n_rows"], "referral record"),
        ]
    )

    fmt_count_cols = {
        col: fmt_int
        for col in [
            "patients", "visits", "referrals", "rows", "entries", "n", "n_rows", "n_patients",
            "n_referrals", "n_orders", "n_components", "height_present", "weight_present",
            "bmi_present", "head_circ_present", "any_diagnosis", "one_or_more", "no_diagnosis",
            "height_n", "bmi_n", "with_height", "with_3_heights", "with_5_heights", "height_pairs",
            "gaps_gt_2_years", "multiple_race", "race1_blank_with_later_value", "growth_flag_patients",
            "growth_flag_with_age", "dx_in_first_month", "dx_in_first_year", "negative_dx_age",
            "specialty_missing", "visit_id_missing", "visit_count_missing", "unique_referral_ids",
            "patient_id_resolves", "visit_id_resolves", "referred_patients", "n_problem_entries",
        ]
    }
    fmt_pct_cols = {
        col: fmt_pct
        for col in [
            "pct", "pct_visits", "height_present_pct", "weight_present_pct", "bmi_present_pct",
            "head_circ_present_pct", "any_diagnosis_pct", "loinc_pct", "result_pct", "flag_pct",
            "pct_growth_flag", "pct_referrals", "height_z_lt_minus2_pct", "height_z_gt_plus2_pct",
            "bmi_lt5_pct", "bmi_ge95_pct",
        ]
    }

    # Build the report as a plain Markdown artifact. All clinical language is
    # framed as data description or research implication, never as patient care.
    report: list[str] = []
    report += [
        "# Real-data exploratory analysis for GrowthChartLiteracy",
        "",
        f"**Analysis date:** {datetime.now().strftime('%Y-%m-%d')}",
        f"**Source root:** `{ROOT}`",
        "**Scope:** aggregate-only descriptive analysis of the real, de-identified PPOC snapshot; no patient-level identifiers or row-level records are included in this report.",
        "",
        "## Executive summary",
        "",
        f"The snapshot contains **{fmt_int(p_n['n_rows'])} patients** and **{fmt_int(v_n['n_rows'])} augmented visits** spanning ages {fmt_year(float(v_n['min_age_days']) / 365.25, 2)}–{fmt_year(float(v_n['max_age_days']) / 365.25, 2)} years on the de-identified age clock. The data are longitudinal and clinically rich, but observation is uneven: encounter volume, anthropometric recording, diagnosis capture, referral capture, and the presence of a later follow-up visit all vary by age and source system.",
        "",
        f"For the GrowthChartLiteracy question, the strongest usable signal is the repeated height trajectory. Height is available at **{fmt_pct(percent(height_patient_all['with_height'], height_patient_all['patients']))} of patients** at least once, **{fmt_pct(percent(height_patient_all['with_3_heights'], height_patient_all['patients']))}** have at least three height-derived observations across all ages, and **{fmt_pct(percent(height_patient_age2['with_3_heights'], height_patient_age2['patients']))}** retain at least three at age 2 years or later. That supports longitudinal trajectory work, while the visit-level completeness table shows why the missingness must remain explicit rather than being treated as random.",
        "",
        f"The distributed anthropometric layer also contains clinically important quality hazards. In particular, the head-circumference channel extends beyond the review range of 25–65 cm in **{fmt_int(data_quality['hc_cm_outside_25_65'])} visits**, and head-circumference z-scores beyond ±5 occur in **{fmt_int(data_quality['hc_z_beyond_5'])} visits**. These are data-quality findings, not clinical diagnoses. Weight-for-length, weight-for-stature, BMI, and head-circumference z-scores should be screened before they are used to construct stimuli or outcomes.",
        "",
        f"The patient-level `growth_dx_flag` is present in **{fmt_int(growth_age_summary['growth_flag_patients'])} patients**; its median recorded age is **{fmt_year(growth_age_summary['median_dx_age_years'], 3)} years**, with **{fmt_pct(percent(growth_age_summary['dx_in_first_month'], growth_age_summary['growth_flag_with_age']))}** of age-observed flagged patients assigned a code in the first month. This supports the source project’s decision to treat diagnosis-code flags as descriptive rather than as a direct label of multi-year trajectory interpretation.",
        "",
        f"Referrals provide a useful action/care-pathway inventory—**{fmt_int(referral_overall['referrals'])} records from {fmt_int(referral_overall['patients'])} patients**—but this report does not estimate a referral/utilization prediction endpoint. That analysis is intentionally deferred in the GrowthChartLiteracy design; here referrals are described as recorded actions with positive-unlabeled and incomplete visit-linkage limitations.",
        "",
        "### Clinical reading of the summary",
        "",
        "A growth percentile, z-score, BMI category, or flag is a screening datum that must be interpreted in age, sex, measurement-quality, trajectory, and clinical-context frames. The report therefore emphasizes distributions, missingness, repeated-measure structure, and ascertainment rather than labeling individual children or recommending care.",
        "",
        "## 1. Data provenance and analytic frame",
        "",
        "The source project frames this dataset as a de-identified pediatric EHR panel from one US primary-care network. Calendar dates are absent; `age_in_days` is the only temporal axis. The augmented visit file contains CDC-LMS-derived growth metrics, velocities, flags, encounter metadata, and up to 33 encounter diagnosis fields. The source project’s plan is the clinical and methodological frame for this report: §Cohort and Data, §Preliminary Analysis, and the descriptions in `docs/data/` were read before analysis.",
        "",
        "The files below were read in place from the supplied data directory. The augmented files are treated as derived data products; the base files are retained in the inventory so row counts and file lineage can be checked.",
        "",
        md_table(inventory, {
            "rows": fmt_int,
            "size_mb": lambda x: fmt_float(x, 1),
        }),
        "",
        "### Linkage and grain",
        "",
        f"The augmented patient file has {fmt_int(p_n['n_rows'])} rows and {fmt_int(p_n['n_patients'])} distinct patient identifiers. The augmented visit file has {fmt_int(v_n['n_rows'])} rows, {fmt_int(v_n['n_patients'])} distinct patients, and {fmt_int(v_n['n_visits'])} distinct visit identifiers. The referral file has {fmt_int(r_n['n_rows'])} rows, {fmt_int(r_n['n_patients'])} referred patients, and {fmt_int(r_n['n_referrals'])} distinct referral identifiers. The problem list has {fmt_int(pl_n['n_rows'])} rows and {fmt_int(pl_n['n_patients'])} patients.",
        "",
        "The `patient_id` link resolves for essentially all rows in the patient-centered resources in this snapshot. Referral `visit_id` is a logical, incomplete link: the report measures that directly below. Labs, medications, and problem-list entries are treated as patient-linked resources; they are not assumed to be complete visit-level captures.",
        "",
        "## 2. Patient composition and observation",
        "",
        "### Sex, ethnicity, and race recording",
        "",
        "Sex is nearly complete. Ethnicity and race are presented with non-response categories collapsed, because blank, unknown, unable-to-collect, and patient-does-not-know responses are not clinically equivalent to a substantive category but are all missing for subgroup inference.",
        "",
        "**Recorded sex**",
        "",
        md_table(patient_sex[["category", "patients", "pct"]], {"patients": fmt_int, "pct": fmt_pct}),
        "",
        "**Ethnicity, with non-response grouped**",
        "",
        md_table(ethnicity[["category", "patients", "pct"]], {"patients": fmt_int, "pct": fmt_pct}),
        "",
        "**Primary race, with non-response grouped**",
        "",
        md_table(race[["category", "patients", "pct"]], {"patients": fmt_int, "pct": fmt_pct}),
        "",
        f"At least one later race field is populated for **{fmt_int(multiple_race['multiple_race'])} patients ({fmt_pct(percent(multiple_race['multiple_race'], multiple_race['patients']))})**. {fmt_int(multiple_race['race1_blank_with_later_value'])} patients have a blank primary race field but a later race field populated; this is a data-structure reason to avoid interpreting `race_1` as a complete multiracial representation without checking all race columns.",
        "",
        "### Visit history and age observation",
        "",
        f"Across patient rows, the median recorded visit count is **{fmt_int(patient_observation['median_visits'])}** (IQR {fmt_int(patient_observation['visits_p25'])}–{fmt_int(patient_observation['visits_p75'])}; range {fmt_int(patient_observation['visits_min'])}–{fmt_int(patient_observation['visits_max'])}). The median observed span is **{fmt_year(float(patient_observation['median_span_days']) / 365.25, 2)} years** (IQR {fmt_year(float(patient_observation['span_p25']) / 365.25, 2)}–{fmt_year(float(patient_observation['span_p75']) / 365.25, 2)}). The median first visit occurs at {fmt_year(float(patient_observation['median_first_age_days']) / 365.25, 2)} years and the median last visit at {fmt_year(float(patient_observation['median_last_age_days']) / 365.25, 2)} years.",
        "",
        md_table(patient_entry[["age_band", "patients", "median_visits", "median_span_years"]], {
            "patients": fmt_int, "median_visits": fmt_float, "median_span_years": fmt_year,
        }),
        "",
        "**Clinical implication.** This is a birth-entry-heavy but right-censored panel: entering near birth does not mean a child is observed through adolescence, and a missing later record is not evidence that a condition was absent. Age-stratified denominators and a minimum look-forward rule are essential for any action/outcome analysis.",
        "",
        "## 3. Visits, encounter context, and measurement availability",
        "",
        "### Visit-level completeness by age",
        "",
        "The denominators below are visits, not unique patients. Repeated measurements from high-utilization children therefore contribute more rows. BMI is structurally sparse below age 2 in the augmented pipeline, so its early missingness should not be interpreted as an isolated data-entry failure.",
        "",
        md_table(visit_age[["age_band", "visits", "patients", "height_present", "height_present_pct", "weight_present", "weight_present_pct", "bmi_present", "bmi_present_pct", "head_circ_present", "head_circ_present_pct", "any_diagnosis", "any_diagnosis_pct"]], {
            "visits": fmt_int, "patients": fmt_int, "height_present": fmt_int, "height_present_pct": fmt_pct,
            "weight_present": fmt_int, "weight_present_pct": fmt_pct, "bmi_present": fmt_int, "bmi_present_pct": fmt_pct,
            "head_circ_present": fmt_int, "head_circ_present_pct": fmt_pct, "any_diagnosis": fmt_int, "any_diagnosis_pct": fmt_pct,
        }),
        "",
        "### Encounter types",
        "",
        "Encounter type is a care-process signal, not a physiologic signal. The predominance of office and well-visit records is useful for understanding capture, but should not be used as a proxy for a child’s clinical state.",
        "",
        md_table(encounter_types[["encounter_type", "visits", "pct_visits", "patients"]], {"visits": fmt_int, "pct_visits": fmt_pct, "patients": fmt_int}),
        "",
        "### Epic versus converted-source recording",
        "",
        "The augmented source flag is evaluated as a completeness stratifier. A lower diagnosis or anthropometric capture rate in converted records would indicate ascertainment differences rather than a clinical difference between children.",
        "",
        md_table(source_summary[["source", "visits", "height_present_pct", "weight_present_pct", "bmi_present_pct", "any_diagnosis_pct"]], {
            "visits": fmt_int, "height_present_pct": fmt_pct, "weight_present_pct": fmt_pct,
            "bmi_present_pct": fmt_pct, "any_diagnosis_pct": fmt_pct,
        }),
        "",
        f"The visit diagnosis slots contain at least one code on **{fmt_pct(percent(diagnosis_completeness['one_or_more'], diagnosis_completeness['visits']))} of visits**; the median number of occupied slots is {fmt_float(diagnosis_completeness['median_code_slots'], 1)} and the 95th percentile is {fmt_float(diagnosis_completeness['p95_code_slots'], 1)}. Diagnosis completeness should be reported alongside encounter source because converted records may be less richly coded.",
        "",
        "## 4. Longitudinal anthropometric structure",
        "",
        "### Height trajectory supply",
        "",
        f"Across all ages, {fmt_int(height_patient_all['with_height'])} patients have at least one height-derived observation, {fmt_int(height_patient_all['with_3_heights'])} have at least three, and {fmt_int(height_patient_all['with_5_heights'])} have at least five. Restricting to age 2 years or later leaves {fmt_int(height_patient_age2['with_height'])} patients with at least one height, {fmt_int(height_patient_age2['with_3_heights'])} with at least three, and {fmt_int(height_patient_age2['with_5_heights'])} with at least five. Among patients with any age-2-or-later height, the median number of retained heights is {fmt_float(height_patient_age2['median_heights_with_any'], 1)}.",
        "",
        f"Among successive age-2-or-later height measurements, the median gap is **{fmt_year(float(height_gaps['median_gap_days']) / 365.25, 2)} years** (IQR {fmt_year(float(height_gaps['gap_p25']) / 365.25, 2)}–{fmt_year(float(height_gaps['gap_p75']) / 365.25, 2)}; 95th percentile {fmt_year(float(height_gaps['gap_p95']) / 365.25, 2)}). **{fmt_pct(percent(height_gaps['gaps_gt_2_years'], height_gaps['height_pairs']))}** of gaps exceed two years. This is clinically relevant censoring: a sparse trajectory may reflect follow-up, transfer, measurement choice, or data capture rather than stable physiology.",
        "",
        "### Within-child dependence",
        "",
        f"The pooled lag-1 autocorrelation of successive age-2-or-later height z-scores is **{fmt_float(autocorrelation['lag1_autocorrelation'], 3)}** across {fmt_int(autocorrelation['pairs'])} pairs. Among patients with at least five age-2-or-later height observations, the between-patient standard deviation of patient mean height z-score is {fmt_float(variance_components['between_patient_sd'], 3)}, while the median within-patient standard deviation is {fmt_float(variance_components['median_within_patient_sd'], 3)} (IQR {fmt_float(variance_components['within_sd_p25'], 3)}–{fmt_float(variance_components['within_sd_p75'], 3)}). These values support patient-level resampling and mixed/repeated-measures reasoning; treating visits as independent would overstate precision.",
        "",
        "### Age- and sex-stratified growth profile",
        "",
        "The following table is visit-level and descriptive. Height z-score summaries use nonmissing height z-scores; BMI percentile summaries use nonmissing BMI percentiles and are limited to age 2 years or later. The threshold shares are screening descriptors, not diagnoses.",
        "",
        md_table(growth_profile[["age_band", "sex", "visits", "height_n", "height_z_median", "height_z_p25", "height_z_p75", "height_z_lt_minus2_pct", "height_z_gt_plus2_pct", "bmi_n", "bmi_percentile_median", "bmi_lt5_pct", "bmi_ge95_pct"]], {
            "visits": fmt_int, "height_n": fmt_int, "height_z_median": lambda x: fmt_float(x, 2), "height_z_p25": lambda x: fmt_float(x, 2),
            "height_z_p75": lambda x: fmt_float(x, 2), "height_z_lt_minus2_pct": fmt_pct, "height_z_gt_plus2_pct": fmt_pct,
            "bmi_n": fmt_int, "bmi_percentile_median": lambda x: fmt_float(x, 1), "bmi_lt5_pct": fmt_pct, "bmi_ge95_pct": fmt_pct,
        }),
        "",
        "**Patient-level age-2-or-later ever-patterns**",
        "",
        md_table(patient_growth_age2[["sex", "patients", "patients_with_height", "patients_ever_stunting", "patients_ever_wasting", "patients_with_bmi", "patients_ever_underweight", "patients_ever_obesity"]], {c: fmt_int for c in patient_growth_age2.columns if c != "sex"}),
        "",
        "The patient-level table answers a different question from the visit-level table: whether a child ever had a recorded threshold crossing while observed. It remains subject to informative measurement, follow-up, and source capture. It should not be interpreted as population prevalence without a defined surveillance denominator.",
        "",
        "### Velocity measures",
        "",
        "The augmented velocity fields are calculated only when the pipeline finds a prior measurement and a sufficient age interval. Their distributions should be inspected for interval effects, implausible jumps, and the influence of sparse endpoints before being used as model inputs. The robust summaries are included in the channel table below; no velocity threshold is used here to label an individual child.",
        "",
        "## 5. Anthropometric distributions and data quality",
        "",
        "### Robust channel distributions",
        "",
        "Quantiles are shown because the maximum is highly sensitive to data-entry and transformation errors. Z-score fields are not assumed to be clinically valid solely because they are numeric.",
        "",
        md_table(channel_summary, {
            "n": fmt_int, "minimum": lambda x: fmt_float(x, 2), "p001": lambda x: fmt_float(x, 2), "p01": lambda x: fmt_float(x, 2),
            "p05": lambda x: fmt_float(x, 2), "median": lambda x: fmt_float(x, 2), "p95": lambda x: fmt_float(x, 2),
            "p99": lambda x: fmt_float(x, 2), "p999": lambda x: fmt_float(x, 2), "maximum": lambda x: fmt_float(x, 2),
        }),
        "",
        "### Review thresholds and transformation checks",
        "",
        f"Rows with a raw weight but no derived weight are {fmt_int(data_quality['raw_weight_without_derived'])}; rows with a raw height but no derived height are {fmt_int(data_quality['raw_height_without_derived'])}. Under the source project’s review thresholds, |weight z| > 5 occurs in {fmt_int(data_quality['weight_z_beyond_5'])} rows and |BMI z| > 5 in {fmt_int(data_quality['bmi_z_beyond_5'])} rows. The corresponding counts are {fmt_int(data_quality['wfl_z_beyond_5'])} for weight-for-length z, {fmt_int(data_quality['wfs_z_beyond_5'])} for weight-for-stature z, and {fmt_int(data_quality['hc_z_beyond_5'])} for head-circumference z. Head circumference outside 25–65 cm occurs in {fmt_int(data_quality['hc_cm_outside_25_65'])} rows; BMI outside 8–60 occurs in {fmt_int(data_quality['bmi_outside_8_60'])} rows. These are analysis-quality review rules from the source project, not universal bedside cutoffs.",
        "",
        f"For {fmt_int(bmi_consistency['n'])} age-2-or-later rows with distributed BMI, weight, and height, the median absolute difference between distributed BMI and recalculated BMI is {fmt_float(bmi_consistency['median_abs_diff'], 4)} kg/m²; the 95th percentile is {fmt_float(bmi_consistency['p95_abs_diff'], 4)}, and {fmt_pct(percent(bmi_consistency['diff_gt_0_1'], bmi_consistency['n']))} differ by more than 0.1 kg/m². Flag-definition discordance counts are: stunting {fmt_int(flag_consistency['stunting_discordant'])}, wasting {fmt_int(flag_consistency['wasting_discordant'])}, underweight {fmt_int(flag_consistency['underweight_discordant'])}, and obesity {fmt_int(flag_consistency['obesity_discordant'])}. A nonzero discordance count should be resolved before treating distributed flags as ground truth.",
        "",
        "### BMI categories in the age-2-or-later window",
        "",
        md_table(bmi_categories[["category", "visits", "patients", "pct_visits"]], {"visits": fmt_int, "patients": fmt_int, "pct_visits": fmt_pct}),
        "",
        "The category distribution is a description of recorded visits with a nonmissing BMI percentile. It is not a prevalence estimate: children with more visits contribute more observations, BMI is missing selectively, and the network’s patient mix and observation window are not a population-sampling frame.",
        "",
        "## 6. Diagnosis landscape",
        "",
        "### Patient-level flags",
        "",
        "These are source-derived flags, not adjudicated diagnoses. `healthy_flag` is especially restrictive because it requires multiple diagnosis and anthropometric conditions to remain absent across the observed record.",
        "",
        md_table(p_flags[["flag", "patients", "pct"]], {"patients": fmt_int, "pct": fmt_pct}),
        "",
        md_table(p_flag_overlap[["group_label", "patients", "pct"]], {"patients": fmt_int, "pct": fmt_pct}),
        "",
        f"The growth flag has {fmt_int(growth_age_summary['growth_flag_patients'])} patients; {fmt_int(growth_age_summary['growth_flag_with_age'])} have a parseable nonmissing diagnosis age. Negative diagnosis ages occur in {fmt_int(growth_age_summary['negative_dx_age'])} flagged patients. The first-month and first-year concentrations are {fmt_pct(percent(growth_age_summary['dx_in_first_month'], growth_age_summary['growth_flag_with_age']))} and {fmt_pct(percent(growth_age_summary['dx_in_first_year'], growth_age_summary['growth_flag_with_age']))}, respectively.",
        "",
        "### Growth-related code composition",
        "",
        "The table below uses patient-level derived code-age columns, which summarize whether a patient had any matching code in the source pipeline. It is sorted by patient count and is intentionally interpreted as coding composition, not trajectory truth. Counts below 10 are suppressed in the displayed table to reduce identifiability risk for rare conditions.",
        "",
    ]
    growth_codes_display = growth_codes.copy()
    growth_codes_display["patients_display"] = growth_codes_display["patients"].map(lambda x: "<10" if float(x) < 10 else fmt_int(x))
    growth_codes_display["median_age_display"] = growth_codes_display.apply(lambda row: "NA" if float(row["patients"]) < 10 else fmt_year(row["median_age_years"], 2), axis=1)
    report.append(md_table(growth_codes_display[["code", "description", "patients_display", "pct_growth_flag", "median_age_display"]], {
        "pct_growth_flag": fmt_pct,
    }))
    report += [
        "",
        "### First-listed encounter diagnoses",
        "",
        "This table is limited to `enc_diag_1`, the first-listed encounter diagnosis, and therefore does not represent complete diagnosis burden. It is included to show the clinical/coding case mix without expanding all 33 diagnosis slots into a row-level output.",
        "",
        md_table(top_primary_dx[["code", "description", "visits", "patients"]], {"visits": fmt_int, "patients": fmt_int}),
        "",
        "### Problem-list diagnoses",
        "",
        md_table(top_problem_dx[["code", "description", "entries", "patients"]], {"entries": fmt_int, "patients": fmt_int}),
        "",
        "Problem-list entries do not carry a complete visit-level link and may include active, historical, or resolved conditions. Their presence is useful for case-mix context, but absence is not evidence that a condition was never present.",
        "",
        "## 7. Specialty referrals and recorded care pathways",
        "",
        f"The referral file contains {fmt_int(referral_overall['referrals'])} records for {fmt_int(referral_overall['patients'])} patients. The median recorded referral age is {fmt_year(referral_overall['median_referral_age_years'], 2)} years (IQR {fmt_year(referral_overall['referral_age_p25_years'], 2)}–{fmt_year(referral_overall['referral_age_p75_years'], 2)}). Missingness is {fmt_pct(percent(referral_overall['specialty_missing'], referral_overall['referrals']))} for requested specialty, {fmt_pct(percent(referral_overall['visit_id_missing'], referral_overall['referrals']))} for visit ID, and {fmt_pct(percent(referral_overall['visit_count_missing'], referral_overall['referrals']))} for recorded referral visit count.",
        "",
        "### Most frequent requested specialties",
        "",
        md_table(referral_specialties[["specialty", "referrals", "pct_referrals", "patients", "median_age_years"]], {"referrals": fmt_int, "pct_referrals": fmt_pct, "patients": fmt_int, "median_age_years": fmt_year}),
        "",
        "### Referral age distribution",
        "",
        md_table(referral_age[["age_band", "referrals", "patients"]], {"referrals": fmt_int, "patients": fmt_int}),
        "",
        "### Growth-relevant specialty families",
        "",
        md_table(referral_focus[["specialty_family", "referrals", "patients", "median_age_years"]], {"referrals": fmt_int, "patients": fmt_int, "median_age_years": fmt_year}),
        "",
        "The family groupings are text-based descriptive groupings created for this report; they are not a validated specialty ontology. They are useful for locating potential growth-related action pathways, not for assigning clinical indication.",
        "",
        "### Referral record semantics and linkage",
        "",
        md_table(referral_visits, {"referrals": fmt_int}),
        "",
        f"Patient IDs resolve for {fmt_pct(percent(referral_linkage['patient_id_resolves'], referral_linkage['referrals']))} of referral rows. Only {fmt_pct(percent(referral_linkage['visit_id_resolves'], referral_linkage['referrals']))} of referral rows have a nonblank visit ID that resolves to an augmented visit in this snapshot. The median number of referral rows per referred patient is {fmt_float(referred_patient_distribution['median_referrals_per_patient'], 1)} (75th percentile {fmt_float(referred_patient_distribution['referrals_p75'], 1)}; maximum {fmt_int(referred_patient_distribution['max_referrals_per_patient'])}). The recorded count values 1 or 6 should not be assumed to mean completed specialty visits without a data dictionary for that field.",
        "",
        "Per the GrowthChartLiteracy plan, referrals are inventoried here but no referral-versus-utilization model, AUROC, calibration curve, or endpoint claim is estimated. The action label is subject to positive-unlabeled interpretation: no recorded referral may mean no action, action outside the network, incomplete capture, or insufficient look-forward.",
        "",
        "## 8. Labs, medications, and problem-list context",
        "",
        "These resources provide case-mix and care-process context but are not substituted for the growth trajectory. The report summarizes counts and completeness without printing laboratory results, medication dates, or patient-linked records.",
        "",
        f"**Labs:** the projection-only source count is {fmt_int(labs_source_rows)} rows; {fmt_int(labs_total['n_rows'])} rows were parser-readable for field-level aggregates ({fmt_int(float(labs_source_rows) - float(labs_total['n_rows']))} rows excluded after the CSV parser encountered malformed records). The readable rows cover {fmt_int(labs_total['n_patients'])} patients, {fmt_int(labs_total['n_orders'])} orders, and {fmt_int(labs_total['n_components'])} result components. LOINC is present on {fmt_pct(percent(labs_total['loinc_present'], labs_total['n_rows']))} of readable rows, a result value on {fmt_pct(percent(labs_total['result_present'], labs_total['n_rows']))}, and a result flag on {fmt_pct(percent(labs_total['flag_present'], labs_total['n_rows']))}. Patient IDs resolve to the augmented patient file on {fmt_pct(percent(labs_linkage['patient_id_resolves'], labs_linkage['rows']))} of readable lab rows.",
        "",
        md_table(labs_top[["lab_procedure_name", "n_rows", "n_patients"]].rename(columns={"lab_procedure_name": "lab_procedure"}), {"n_rows": fmt_int, "n_patients": fmt_int}),
        "",
        f"**Medications:** {fmt_int(meds_total['n_rows'])} records for {fmt_int(meds_total['n_patients'])} patients. The order date is present on {fmt_pct(percent(meds_total['order_date_present'], meds_total['n_rows']))} of records, start date on {fmt_pct(percent(meds_total['start_date_present'], meds_total['n_rows']))}, and end date on {fmt_pct(percent(meds_total['end_date_present'], meds_total['n_rows']))}. Patient IDs resolve on {fmt_pct(percent(meds_linkage['patient_id_resolves'], meds_linkage['rows']))} of medication rows.",
        "",
        md_table(meds_top[["med_simple_generic_name", "n_rows", "n_patients"]].rename(columns={"med_simple_generic_name": "generic_name"}), {"n_rows": fmt_int, "n_patients": fmt_int}),
        "",
        "**Medication record type:**",
        "",
        md_table(meds_types[["med_record_type", "n_rows", "n_patients"]].rename(columns={"med_record_type": "record_type"}), {"n_rows": fmt_int, "n_patients": fmt_int}),
        "",
        f"**Problem list:** {fmt_int(pl_total['n_rows'])} entries for {fmt_int(pl_total['n_patients'])} patients, with {fmt_pct(percent(pl_total['resolved_present'], pl_total['n_rows']))} having a populated resolved-age field. Patient IDs resolve on {fmt_pct(percent(pl_linkage['patient_id_resolves'], pl_linkage['rows']))} of rows.",
        "",
        md_table(top_problem_dx[["code", "description", "entries", "patients"]], {"entries": fmt_int, "patients": fmt_int}),
        "",
        "## 9. Research and clinical implications for GrowthChartLiteracy",
        "",
        "### What the data support",
        "",
        "- A longitudinal, repeated-measures growth representation: age-2-or-later height observations are available for a large majority of patients, with enough repeated points for patient-level trajectories in a substantial analytic frame.",
        "- Counterfactual stimulus construction calibrated to real schedule structure: the observed height gaps, within-child variation, between-child variation, and autocorrelation provide empirical targets for synthetic trajectories.",
        "- Explicit utilization controls: visit count, encounter type, observation span, measurement density, and source-system provenance are visible care-process variables that can be profiled and balanced without treating them as physiology.",
        "- A secondary recorded-action layer: specialty referral records can describe an observed care pathway, provided the index date, look-forward, missing linkage, and positive-unlabeled status are fixed before modeling.",
        "",
        "### What the data do not support without additional governance or validation",
        "",
        "- A claim that an ICD-10-derived growth flag is a clinician-adjudicated trajectory label. Its timing and composition are strongly affected by neonatal and billing capture.",
        "- A claim that a missing referral is a negative clinical outcome. Referral capture is incomplete at the visit level and absence of a referral is not absence of concern.",
        "- Population prevalence estimates from raw visit-level threshold shares. The observation process is utilization-dependent and repeated visits overweight children with longer or denser records.",
        "- Clinical recommendations for any individual child. The report is aggregate EDA, not a diagnostic or treatment tool.",
        "- Fair subgroup comparisons without missingness-aware denominators. Ethnicity and race non-response are substantial, and measurement and referral capture may vary by source and utilization.",
        "",
        "### Recommended analytic guardrails",
        "",
        "1. Use age 2 years or later as the primary growth-trajectory frame if the intended reference is CDC-based and the project wants to avoid mixing infant and post-infancy interpretation.",
        "2. Define trajectory eligibility using measurement availability, not only visit count; report the number of height-bearing observations, span, and gaps.",
        "3. Resample and model at the patient or trajectory level, not the visit level, when estimating uncertainty.",
        "4. Treat missingness as potentially informative. Show missingness by age band, sex, race/ethnicity recording, encounter source, and utilization band before interpreting any subgroup contrast.",
        "5. Recompute or validate distributed anthropometric flags after applying an explicit, source-documented plausibility pipeline. Exclude head-circumference z-score from trajectory serialization until its transform is repaired or independently validated.",
        "6. Keep diagnosis, referral, and utilization labels separate. A diagnosis code is a recorded code; a referral is a recorded action; neither is an adjudicated physiologic truth.",
        "7. Pre-specify the referral index and look-forward before estimating action-related performance, and report the result as record-based rather than as a diagnosis of the child.",
        "",
        "## 10. Methods and reproducibility",
        "",
        "The analysis used DuckDB 1.5.5 through the repository’s `uv` environment. The script materializes only selected columns needed for aggregate queries, uses age in days as the time axis, and does not export identifiers. Quantiles use DuckDB `quantile_cont`; repeated-measure summaries use patient-level grouping and age-ordered window functions. The ICD-10 lookup is normalized to one description per code before joins to prevent lookup duplication from multiplying diagnosis rows. Visit-level tables are explicitly labeled as visit-level; patient-level ever-patterns are grouped by patient.",
        "",
        "The report was generated by:",
        "",
        "```sh",
        "PPOC_DATA_ROOT=/Users/joon/w/p3-data/all uv run python reports/eda/build_growth_chart_literacy_eda.py",
        "```",
        "",
        "The report is descriptive and exploratory. It does not constitute a registered endpoint analysis, a clinical validation study, a diagnostic device evaluation, or evidence of clinical benefit. The source data remain outside the repository; only this aggregate report and its analysis script are written locally.",
        "",
        "## Source framing",
        "",
        "- `/Users/joon/src/tries/growth-chart-literacy/growth-chart-literacy.md`, §Cohort and Data and §Preliminary Analysis",
        "- `/Users/joon/src/tries/growth-chart-literacy/docs/data/data_description.md` and the resource-specific descriptions under `docs/data/`",
        "- `/Users/joon/src/tries/growth-chart-literacy/review-2026-08-30-queries.sql` and `scripts/anthropometric_profile.sql`, used as prior analysis context and re-checked against the supplied real-data directory",
        "",
        "## Clinical interpretation references",
        "",
        "These references anchor the report’s interpretive guardrails; they do not turn aggregate EDA into clinical validation or patient-specific advice.",
        "",
        "- [CDC Growth Charts](https://www.cdc.gov/growthcharts/): growth charts are percentile curves used to track growth and are not intended to be the sole diagnostic instrument.",
        "- [CDC: What Growth Charts Are Recommended?](https://www.cdc.gov/growth-chart-training/hcp/overview/recommended.html): WHO Child Growth Standards are recommended from birth to 2 years and CDC Growth Charts from age 2 years onward in the US context.",
        "- [CDC Child and Teen BMI Categories](https://www.cdc.gov/bmi/child-teen-calculator/bmi-categories.html): BMI categories for children and teens use sex-specific BMI-for-age percentiles; this report therefore treats BMI as age-2-or-later and descriptive.",
        "- [WHO Child Growth Standards](https://www.who.int/tools/child-growth-standards/standards): documentation, indicators, and implementation resources for the WHO standards.",
        "",
    ]

    REPORT.write_text("\n".join(report), encoding="utf-8")
    print(f"wrote {REPORT}")
    print(f"patients={p_n['n_rows']} visits={v_n['n_rows']} referrals={r_n['n_rows']} report_bytes={REPORT.stat().st_size}")


if __name__ == "__main__":
    main()

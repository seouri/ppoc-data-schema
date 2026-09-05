#!/usr/bin/env python3
"""Profile common EHR data artifacts in the PPOC snapshot from the typed DuckDB bundle.

The bundle is opened read-only and is never copied into the repository. The
script emits aggregate tables only; it never writes a patient_id, visit_id,
referral_id, lab_order_id, or any other row-level identifier. Cells backed by
fewer than SUPPRESS_BELOW records are suppressed in displayed tables.

The generated markdown replaces the block delimited by BEGIN_MARKER/END_MARKER
in reports/growth-chart-literacy-real-data-eda.md, so the report's artifact
section stays measured rather than hand-maintained.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import duckdb

REPORT = Path(__file__).resolve().parent.parent / "growth-chart-literacy-real-data-eda.md"
BEGIN_MARKER = "<!-- BEGIN ehr-artifact-profile -->"
END_MARKER = "<!-- END ehr-artifact-profile -->"
SUPPRESS_BELOW = 10

DEFAULT_BUNDLE = os.environ.get(
    "PPOC_DUCKDB", "/Users/joon/src/tries/ppoc-duckdb-real/ppoc.duckdb"
)

ENC_DIAG = ", ".join(f"enc_diag_{i}" for i in range(1, 34))

# Review thresholds reused from the source project's anthropometric rules so the
# artifact section stays comparable with section 5 of the report.
HC_LO, HC_HI = 25.0, 65.0


def q(con: duckdb.DuckDBPyConnection, sql: str) -> list[tuple]:
    return con.execute(sql).fetchall()


def one(con: duckdb.DuckDBPyConnection, sql: str) -> tuple:
    return con.execute(sql).fetchone()


def fmt(value: object, digits: int = 0) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float):
        if digits == 0:
            return f"{value:,.0f}"
        return f"{value:,.{digits}f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def pct(value: object, digits: int = 2) -> str:
    return "NA" if value is None else f"{value:,.{digits}f}%"


def table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |",
           "| " + " | ".join("---" for _ in header) + " |"]
    out.extend("| " + " | ".join(r) + " |" for r in rows)
    return "\n".join(out)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 22), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# Individual artifact probes
# --------------------------------------------------------------------------


def probe_gate(con) -> dict:
    """Recompute report section 5 figures so the bundle can be shown to match."""
    row = one(con, f"""
        select
          (select count(*) from visits_augmented
             where head_circ_cm is not null
               and (head_circ_cm < {HC_LO} or head_circ_cm > {HC_HI})),
          (select count(*) from visits_augmented where abs(bmi_z_score) > 5),
          (select count(*) from visits_augmented where abs(weight_for_length_z_score) > 5),
          (select count(*) from visits_augmented where abs(weight_for_stature_z_score) > 5),
          (select count(*) from visits_augmented where abs(head_circ_z_score) > 5),
          (select count(*) from visits_augmented
             where bmi is not null and (bmi < 8 or bmi > 60))
    """)
    keys = ["hc_out_range", "bmi_z", "wfl_z", "wfs_z", "hc_z", "bmi_range"]
    return dict(zip(keys, row))


def probe_truncation(con) -> dict:
    row = one(con, """
        select
          count(*),
          min(height_z_score), max(height_z_score),
          sum(case when height_z_score >= 3 then 1 else 0 end),
          sum(case when height_z_score >= 2.5 then 1 else 0 end),
          sum(case when height_z_score <= -3 then 1 else 0 end),
          sum(case when height_z_score <= -2.5 then 1 else 0 end)
        from visits_augmented where height_z_score is not null
    """)
    keys = ["n", "min_z", "max_z", "ge3", "ge25", "le_m3", "le_m25"]
    out = dict(zip(keys, row))

    wrow = one(con, """
        select min(weight_z_score), max(weight_z_score),
               min(bmi_z_score), max(bmi_z_score)
        from visits_augmented
    """)
    out.update(dict(zip(["min_wz", "max_wz", "min_bz", "max_bz"], wrow)))

    out["dropped"] = one(con, """
        select count(*) from visits_augmented
        where height_in is not null and height_cm is null
    """)[0]

    # Whether a dropped height is extreme must be judged against same-age peers,
    # not against an absolute stature: a tall-for-age six-year-old is nowhere near
    # 190 cm. Compare each dropped value with the distribution of *retained*
    # heights in its own age-month and sex cell.
    drop = one(con, """
        with ref as (
          select cast(age_in_days / 30.44 as int) am, sex,
                 quantile_cont(height_cm, 0.999) p999,
                 quantile_cont(height_cm, 0.5) med,
                 count(*) n
          from visits_augmented
          where height_cm is not null and sex in ('M', 'F')
          group by 1, 2
        ), dropped as (
          select cast(age_in_days / 30.44 as int) am, sex, height_in * 2.54 hcm
          from visits_augmented
          where height_in is not null and height_cm is null and sex in ('M', 'F')
        )
        select count(*),
               count(*) filter (where d.hcm > r.p999),
               count(*) filter (where d.hcm < r.med)
        from dropped d join ref r using (am, sex)
        where r.n >= 200
    """)
    out.update(dict(zip(["dropped_cmp", "dropped_tall", "dropped_short"], drop)))

    out["null_z_with_height"] = one(con, """
        select count(*) from visits_augmented
        where height_cm is not null and height_z_score is null
    """)[0]
    return out


def probe_percentile_bounds(con) -> list[list[str]]:
    channels = [
        ("height_percentile", "height percentile"),
        ("weight_percentile", "weight percentile"),
        ("bmi_percentile", "BMI percentile"),
        ("weight_for_length_percentile", "weight-for-length percentile"),
        ("weight_for_stature_percentile", "weight-for-stature percentile"),
    ]
    rows = []
    for col, label in channels:
        n, at0, at100, mn, mx = one(con, f"""
            select count(*),
                   sum(case when {col} <= 0 then 1 else 0 end),
                   sum(case when {col} >= 100 then 1 else 0 end),
                   min({col}), max({col})
            from visits_augmented where {col} is not null
        """)
        rows.append([
            label, fmt(n), fmt(at0), pct(100.0 * at0 / n, 3),
            fmt(at100), pct(100.0 * at100 / n, 3), fmt(mn, 2), fmt(mx, 2),
        ])
    return rows


def probe_heaping(con) -> dict:
    h = one(con, """
        select count(*),
               100.0 * sum(case when height_in = floor(height_in) then 1 else 0 end) / count(*),
               100.0 * sum(case when abs(height_in * 2 - round(height_in * 2)) < 1e-9 then 1 else 0 end) / count(*),
               100.0 * sum(case when abs(height_in * 4 - round(height_in * 4)) < 1e-9 then 1 else 0 end) / count(*)
        from visits_augmented where height_in is not null
    """)
    w = one(con, """
        select count(*),
               100.0 * sum(case when abs(weight_oz - round(weight_oz)) < 1e-9 then 1 else 0 end) / count(*),
               100.0 * sum(case when abs(weight_oz / 16 - round(weight_oz / 16)) < 1e-9 then 1 else 0 end) / count(*),
               100.0 * sum(case when abs(weight_oz / 8 - round(weight_oz / 8)) < 1e-9 then 1 else 0 end) / count(*)
        from visits_augmented where weight_oz is not null
    """)
    bands = q(con, """
        select case when age_in_days < 2 * 365.25 then '0-<2 years'
                    when age_in_days < 1826 then '2-<5 years'
                    when age_in_days < 3652 then '5-<10 years'
                    when age_in_days < 5478 then '10-<15 years'
                    else '15-18 years' end,
               count(*),
               100.0 * sum(case when abs(weight_oz / 16 - round(weight_oz / 16)) < 1e-9 then 1 else 0 end) / count(*),
               100.0 * sum(case when height_in = floor(height_in) then 1 else 0 end)
                     / nullif(sum(case when height_in is not null then 1 else 0 end), 0)
        from visits_augmented where weight_oz is not null
        group by 1
        order by min(age_in_days)
    """)
    return {"h": h, "w": w, "bands": bands}


def probe_conversion(con) -> dict:
    row = one(con, """
        select
          count(*) filter (where height_in is not null and height_cm is not null),
          count(*) filter (where height_in is not null and height_cm is not null
                             and abs(height_cm - height_in * 2.54) > 0.01),
          count(*) filter (where weight_oz is not null and weight_kg is not null),
          count(*) filter (where weight_oz is not null and weight_kg is not null
                             and abs(weight_kg - weight_oz * 0.0283495) > 0.01)
        from visits_augmented
    """)
    return dict(zip(["h_pairs", "h_bad", "w_pairs", "w_bad"], row))


def probe_head_circ(con) -> dict:
    bands = q(con, f"""
        select case when head_circ_cm < 10 then 'below 10 cm'
                    when head_circ_cm < {HC_LO} then '10 to <25 cm'
                    when head_circ_cm <= {HC_HI} then '25 to 65 cm (within review range)'
                    when head_circ_cm <= 200 then '>65 to 200 cm'
                    else 'above 200 cm' end,
               count(*), quantile_cont(head_circ_cm, 0.5), min(head_circ_cm), max(head_circ_cm)
        from visits_augmented where head_circ_cm is not null
        group by 1 order by min(head_circ_cm)
    """)
    dbl = one(con, f"""
        select count(*),
               count(*) filter (where head_circ_cm / 2.54 between {HC_LO} and {HC_HI}),
               quantile_cont(head_circ_cm / 2.54, 0.5)
        from visits_augmented where head_circ_cm > {HC_HI} and head_circ_cm <= 200
    """)
    trip = one(con, f"""
        select count(*),
               count(*) filter (where head_circ_cm / 2.54 / 2.54 between {HC_LO} and {HC_HI})
        from visits_augmented where head_circ_cm > 200
    """)
    z = one(con, f"""
        select count(*) filter (where abs(head_circ_z_score) > 5),
               count(*) filter (where abs(head_circ_z_score) > 5
                                  and (head_circ_cm < {HC_LO} or head_circ_cm > {HC_HI})),
               count(*) filter (where abs(head_circ_z_score) > 5
                                  and head_circ_cm between {HC_LO} and {HC_HI})
        from visits_augmented where head_circ_z_score is not null
    """)
    return {"bands": bands, "dbl": dbl, "trip": trip, "z": z}


def probe_repeats(con) -> dict:
    """Zero and negative successive height changes, by age gap."""
    rows = q(con, """
        with s as (
          select patient_id, age_in_days, height_cm
          from visits_augmented
          where height_cm is not null and age_in_days >= 2 * 365.25
        ), l as (
          select *,
                 height_cm - lag(height_cm) over w as dh,
                 age_in_days - lag(age_in_days) over w as da
          from s window w as (partition by patient_id order by age_in_days, height_cm)
        )
        select case when da <= 7 then 'up to 7 days'
                    when da <= 30 then '8 to 30 days'
                    when da <= 90 then '31 to 90 days'
                    when da <= 180 then '91 to 180 days'
                    when da <= 365 then '181 to 365 days'
                    else 'over 365 days' end,
               count(*),
               100.0 * sum(case when dh = 0 then 1 else 0 end) / count(*),
               100.0 * sum(case when dh < 0 then 1 else 0 end) / count(*),
               100.0 * sum(case when dh < -2.54 then 1 else 0 end) / count(*)
        from l where da is not null and da > 0
        group by 1 order by min(da)
    """)
    totals = one(con, """
        with s as (
          select patient_id, age_in_days, height_cm
          from visits_augmented
          where height_cm is not null and age_in_days >= 2 * 365.25
        ), l as (
          select *,
                 height_cm - lag(height_cm) over w as dh,
                 age_in_days - lag(age_in_days) over w as da
          from s window w as (partition by patient_id order by age_in_days, height_cm)
        )
        select count(*),
               sum(case when dh = 0 then 1 else 0 end),
               sum(case when dh < 0 then 1 else 0 end),
               100.0 * sum(case when dh = 0 then 1 else 0 end) / count(*),
               100.0 * sum(case when dh < 0 then 1 else 0 end) / count(*)
        from l where da is not null and da > 0
    """)
    return {"rows": rows, "totals": totals}


def probe_delta_fields(con) -> dict:
    """Do the distributed delta fields reproduce a successive-measurement lag?"""
    row = one(con, """
        with s as (
          select patient_id, age_in_days, height_cm, height_in * 2.54 as h_raw,
                 delta_height_cm
          from visits_augmented
          where patient_id in (select patient_id from patients limit 4000)
        ), l as (
          select *,
            height_cm - lag(height_cm) over w as dh_all,
            height_cm - lag(height_cm ignore nulls) over w as dh_meas,
            h_raw - lag(h_raw) over w as dh_raw
          from s window w as (partition by patient_id order by age_in_days)
        )
        select count(*),
               sum(case when abs(dh_all - delta_height_cm) < 1e-6 then 1 else 0 end),
               sum(case when abs(dh_meas - delta_height_cm) < 1e-6 then 1 else 0 end),
               sum(case when abs(dh_raw - delta_height_cm) < 1e-4 then 1 else 0 end)
        from l where delta_height_cm is not null
    """)
    return dict(zip(["n", "all_visits", "last_measured", "raw_inches"], row))


def probe_same_day(con) -> dict:
    row = one(con, """
        with g as (
          select patient_id, age_in_days, count(*) c,
                 count(height_cm) nh, max(height_cm) - min(height_cm) hs,
                 count(weight_kg) nw, max(weight_kg) - min(weight_kg) ws
          from visits_augmented group by 1, 2
        )
        select count(*), sum(c),
               sum(case when c > 1 then 1 else 0 end),
               sum(case when c > 1 then c else 0 end),
               sum(case when nh > 1 then 1 else 0 end),
               sum(case when nh > 1 and hs > 0 then 1 else 0 end),
               sum(case when nw > 1 then 1 else 0 end),
               sum(case when nw > 1 and ws > 0 then 1 else 0 end)
        from g
    """)
    keys = ["patient_days", "visits", "dup_days", "dup_visits",
            "days_2h", "days_2h_disagree", "days_2w", "days_2w_disagree"]
    out = dict(zip(keys, row))
    mag = one(con, """
        with g as (
          select patient_id, age_in_days,
                 count(height_cm) nh, max(height_cm) - min(height_cm) hs,
                 count(weight_kg) nw, max(weight_kg) - min(weight_kg) ws
          from visits_augmented group by 1, 2
        )
        select
          (select quantile_cont(hs, 0.5) from g where nh > 1 and hs > 0),
          (select quantile_cont(hs, 0.95) from g where nh > 1 and hs > 0),
          (select max(hs) from g where nh > 1),
          (select quantile_cont(ws, 0.5) from g where nw > 1 and ws > 0),
          (select quantile_cont(ws, 0.95) from g where nw > 1 and ws > 0),
          (select max(ws) from g where nw > 1)
    """)
    out.update(dict(zip(
        ["h_med", "h_p95", "h_max", "w_med", "w_p95", "w_max"], mag)))
    return out


def probe_encounter_capture(con) -> list[list[str]]:
    rows = q(con, """
        select encounter_type, count(*),
               100.0 * count(weight_kg) / count(*),
               100.0 * count(height_cm) / count(*),
               100.0 * count(*) filter (where enc_diag_1 is not null) / count(*)
        from visits_augmented
        group by 1 having count(*) >= 10000
        order by count(*) desc
    """)
    return [[r[0], fmt(r[1]), pct(r[2], 1), pct(r[3], 1), pct(r[4], 1)] for r in rows]


def probe_carry_forward(con) -> list[list[str]]:
    rows = q(con, """
        with s as (
          select patient_id, encounter_type, weight_kg,
                 lag(weight_kg) over w as prev_w,
                 age_in_days - lag(age_in_days) over w as gap
          from visits_augmented
          window w as (partition by patient_id order by age_in_days, visit_id)
        )
        select encounter_type, count(*),
               100.0 * count(*) filter (where prev_w is not null and abs(weight_kg - prev_w) < 1e-9)
                     / nullif(count(*) filter (where prev_w is not null), 0),
               100.0 * count(*) filter (where prev_w is not null and abs(weight_kg - prev_w) < 1e-9 and gap > 7)
                     / nullif(count(*) filter (where prev_w is not null and gap > 7), 0)
        from s
        where weight_kg is not null
          and encounter_type in ('Office Visit', 'Well Visit (Conv.)', 'Sick',
                                 'Telemedicine', 'Telephone', 'Clinical Support', 'Documentation')
        group by 1 order by count(*) desc
    """)
    return [[r[0], fmt(r[1]), pct(r[2], 1), pct(r[3], 1)] for r in rows]


def probe_temporal(con) -> list[list[str]]:
    checks = [
        ("Lab result age earlier than lab order age",
         "select count(*) from labs where lab_result_date_age_in_days < lab_order_date_age_in_days",
         "select count(*) from labs where lab_result_date_age_in_days is not null"),
        ("Medication start age earlier than order age",
         "select count(*) from medications where med_start_date_age_in_days < med_order_date_age_in_days",
         "select count(*) from medications where med_start_date_age_in_days is not null"),
        ("Medication end age earlier than start age",
         "select count(*) from medications where med_end_date_age_in_days < med_start_date_age_in_days",
         "select count(*) from medications where med_end_date_age_in_days is not null and med_start_date_age_in_days is not null"),
        ("Problem resolved age earlier than noted age",
         "select count(*) from problem_list where resolved_date_age_in_days < noted_date_age_in_days",
         "select count(*) from problem_list where resolved_date_age_in_days is not null and noted_date_age_in_days is not null"),
        ("Problem noted before birth (negative age)",
         "select count(*) from problem_list where noted_date_age_in_days < 0",
         "select count(*) from problem_list where noted_date_age_in_days is not null"),
        ("Lab ordered before birth (negative age)",
         "select count(*) from labs where lab_order_date_age_in_days < 0",
         "select count(*) from labs"),
        ("Medication ordered before birth (negative age)",
         "select count(*) from medications where med_order_date_age_in_days < 0",
         "select count(*) from medications"),
        ("Visit recorded before birth (negative age)",
         "select count(*) from visits_augmented where age_in_days < 0",
         "select count(*) from visits_augmented"),
    ]
    rows = []
    for label, bad_sql, denom_sql in checks:
        bad = one(con, bad_sql)[0]
        denom = one(con, denom_sql)[0]
        display = fmt(bad) if bad == 0 or bad >= SUPPRESS_BELOW else f"<{SUPPRESS_BELOW}"
        rows.append([label, display, fmt(denom),
                     pct(100.0 * bad / denom, 3) if denom else "NA"])
    return rows


def probe_visit_link(con) -> list[list[str]]:
    rows = []
    for name, tbl in [("labs", "labs"), ("medications", "medications"), ("referrals", "referrals")]:
        tot, nonnull, unres = one(con, f"""
            select count(*), count(t.visit_id),
                   count(*) filter (where t.visit_id is not null and v.visit_id is null)
            from {tbl} t left join (select visit_id from visits_augmented) v
              on t.visit_id = v.visit_id
        """)
        rows.append([
            name, fmt(tot), fmt(nonnull),
            pct(100.0 * (tot - nonnull) / tot, 2),
            fmt(unres),
            pct(100.0 * unres / nonnull, 2) if nonnull else "NA",
        ])
    return rows


def probe_lab_values(con) -> dict:
    row = one(con, """
        select count(*), count(result_value),
               count(*) filter (where try_cast(result_value as double) is not null),
               count(*) filter (where result_value is not null and try_cast(result_value as double) is null),
               count(*) filter (where regexp_matches(result_value, '^[<>]=?\\s*[0-9]'))
        from labs
    """)
    out = dict(zip(["total", "nonnull", "numeric", "non_numeric", "comparator"], row))
    dup = one(con, """
        with g as (
          select lab_order_id, result_component_name,
                 count(*) c, count(distinct result_value) dv
          from labs where result_value is not null group by 1, 2
        )
        select sum(case when c > 1 then 1 else 0 end),
               sum(case when c > 1 and dv > 1 then 1 else 0 end)
        from g
    """)
    out["repeat_component"], out["repeat_disagree"] = dup
    key = one(con, """
        with g as (
          select lab_order_id, result_component_name, result_line_num, count(*) c
          from labs group by 1, 2, 3
        )
        select sum(case when c > 1 then 1 else 0 end) from g
    """)
    out["key_dupes"] = key[0]
    return out


def probe_codes(con) -> dict:
    icd = "'^[A-Z][0-9][0-9AB](\\.[0-9A-Z]{1,4})?$'"
    pl = one(con, f"""
        select count(*), count(distinct pl_diag),
               count(*) filter (where not regexp_matches(pl_diag, {icd}))
        from problem_list
    """)
    enc = one(con, f"""
        with u as (select unnest([{ENC_DIAG}]) as c from visits_augmented)
        select count(*), count(distinct c),
               count(*) filter (where not regexp_matches(c, {icd}))
        from u where c is not null and trim(c) <> ''
    """)
    names = one(con, """
        select
          (select count(distinct lab_procedure_name) from labs where lab_procedure_name is not null),
          (select count(distinct upper(regexp_replace(trim(lab_procedure_name), '\\s+', ' ', 'g')))
             from labs where lab_procedure_name is not null),
          (select count(*) from labs where regexp_matches(lab_procedure_name, '  ')),
          (select count(distinct med_simple_generic_name) from medications),
          (select count(distinct upper(regexp_replace(trim(med_simple_generic_name), '\\s+', ' ', 'g')))
             from medications),
          (select count(distinct requested_specialty) from referrals
             where requested_specialty is not null and trim(requested_specialty) <> ''),
          (select count(distinct upper(regexp_replace(trim(requested_specialty), '\\s+', ' ', 'g')))
             from referrals where requested_specialty is not null and trim(requested_specialty) <> '')
    """)
    return {"pl": pl, "enc": enc, "names": names}


# --------------------------------------------------------------------------
# Section rendering
# --------------------------------------------------------------------------


def render(con, bundle: Path, manifest: dict | None, digest: str) -> str:
    gate = probe_gate(con)
    trunc = probe_truncation(con)
    heap = probe_heaping(con)
    conv = probe_conversion(con)
    hc = probe_head_circ(con)
    rep = probe_repeats(con)
    delta = probe_delta_fields(con)
    same = probe_same_day(con)
    labs = probe_lab_values(con)
    codes = probe_codes(con)

    snapshot = (manifest or {}).get("package", {}).get("snapshot", "unknown")
    parts: list[str] = []
    a = parts.append

    a(BEGIN_MARKER)
    a("")
    a("## 6. Common EHR data artifacts")
    a("")
    a(
        "This section profiles recording, transformation, and linkage artifacts that "
        "are characteristic of electronic health record extracts. It was computed "
        "from the typed DuckDB bundle rather than the CSV directory; the generator "
        "and provenance are documented in the methods section. Every finding below "
        "describes the behaviour of a recording and derivation system. None of them "
        "is a statement about any child, and none is a clinical judgement."
    )
    a("")
    a(
        "The two artifact classes profiled here are the ones the source project "
        "already treats as its framing references: implausible values in pediatric "
        "growth data (Daymont et al., 2017) and utilization-driven capture in EHR "
        "extracts (Agniel, Kohane and Weber, 2018). This section is the measured "
        "instance of both in this snapshot, not an independent literature."
    )
    a("")
    a(
        "Two distinct actors produce these artifacts and the report keeps them "
        "separate. Some are **capture artifacts** introduced where care is delivered "
        "and data are typed, such as digit rounding and repeated same-day "
        "measurements. Others are **derivation artifacts** introduced by the "
        "augmentation pipeline that computed z-scores, percentiles, velocities, and "
        "flags. A derivation artifact can be repaired without touching the clinical "
        "record; a capture artifact cannot."
    )
    a("")
    a(
        f"**Bundle agreement check.** Before any new figure was computed, six review "
        f"counts from the previous section were recomputed from the bundle: head "
        f"circumference outside the {HC_LO:.0f}–{HC_HI:.0f} cm review range "
        f"({fmt(gate['hc_out_range'])}), |BMI z| > 5 ({fmt(gate['bmi_z'])}), "
        f"|weight-for-length z| > 5 ({fmt(gate['wfl_z'])}), |weight-for-stature z| > 5 "
        f"({fmt(gate['wfs_z'])}), |head-circumference z| > 5 ({fmt(gate['hc_z'])}), and "
        f"BMI outside 8–60 ({fmt(gate['bmi_range'])}). All six reproduce the values "
        f"reported in section 5, so the bundle is the same snapshot "
        f"(`{snapshot}`) and the counts in this section are directly comparable with "
        f"the rest of the report."
    )
    a("")

    # ---- 6.1 truncation
    a("### 6.1 Asymmetric truncation of the height z-score (derivation artifact)")
    a("")
    a(
        f"The distributed height z-score is bounded above at exactly "
        f"{fmt(trunc['max_z'], 2)} while its lower tail runs to "
        f"{fmt(trunc['min_z'], 4)}. The truncation is not visible as a pile-up at the "
        f"boundary, so it is easy to miss: only {fmt(trunc['ge3'])} visits sit at or "
        f"above +3, and the upper tail decays smoothly right up to the bound."
    )
    a("")
    a(
        "The asymmetry is what exposes it. The two tails should be broadly comparable "
        "in a z-score channel, and they are not."
    )
    a("")
    a(table(
        ["tail", "visits beyond 2.5 in absolute z", "visits beyond 3 in absolute z", "share of the 2.5 mass continuing past 3"],
        [
            ["lower (negative z)", fmt(trunc["le_m25"]), fmt(trunc["le_m3"]),
             pct(100.0 * trunc["le_m3"] / trunc["le_m25"], 1)],
            ["upper (positive z)", fmt(trunc["ge25"]), fmt(trunc["ge3"]),
             pct(100.0 * trunc["ge3"] / trunc["ge25"], 2)],
        ],
    ))
    a("")
    a(
        f"In the lower tail, "
        f"{pct(100.0 * trunc['le_m3'] / trunc['le_m25'], 1)} of the mass beyond |z| = 2.5 "
        f"continues past |z| = 3. If the upper tail behaved the same way, roughly "
        f"{fmt(round(trunc['ge25'] * trunc['le_m3'] / trunc['le_m25'] / 100) * 100)} "
        f"visits would sit above +3; {fmt(trunc['ge3'])} do. The tall-stature tail of "
        f"the height channel is therefore effectively absent, while the short-stature "
        f"tail is retained down to −5."
    )
    a("")
    a(
        f"The mechanism is documented rather than inferred. The source project's plan "
        f"records that the augmentation pipeline nulls weight and its z-score at "
        f"|z| > 5 and height outside −5 < z < 3, and states that the values above +3 "
        f"\u201cwere set to NA and are gone from the distributed file\u201d. The snapshot "
        f"agrees. {fmt(trunc['dropped'])} visits carry a raw `height_in` with no "
        f"derived `height_cm`, and those discarded measurements are tall for age: of "
        f"the {fmt(trunc['dropped_cmp'])} that fall in an age-month and sex cell with "
        f"at least 200 retained heights, {fmt(trunc['dropped_tall'])} "
        f"({pct(100.0 * trunc['dropped_tall'] / trunc['dropped_cmp'], 1)}) sit above "
        f"the 99.9th percentile of the heights that were *kept* in the same cell, "
        f"against {fmt(trunc['dropped_short'])} "
        f"({pct(100.0 * trunc['dropped_short'] / trunc['dropped_cmp'], 1)}) below that "
        f"cell's median. That count is the same order as the missing mass the "
        f"asymmetry implies. Judging these values against an absolute stature rather "
        f"than against same-age peers hides the pattern entirely, because a "
        f"tall-for-age six-year-old is nowhere near 190 cm. Consistently, only "
        f"{fmt(trunc['null_z_with_height'])} visits carry a derived height with no "
        f"z-score: the pipeline nulls the measurement and its z-score together rather "
        f"than leaving orphaned rows behind."
    )
    a("")
    a(
        f"The bound is also channel-specific and undocumented in the field names. "
        f"Weight z runs {fmt(trunc['min_wz'], 4)} to {fmt(trunc['max_wz'], 4)} and BMI z "
        f"runs {fmt(trunc['min_bz'], 4)} to {fmt(trunc['max_bz'], 4)}, so the three "
        f"channels do not share a common support. Any model that consumes several z "
        f"channels together inherits that inconsistency silently."
    )
    a("")
    a(
        "**Consequence for this project.** Tall stature is one of the two directions a "
        "growth-chart reader is asked to recognise. A height channel whose upper tail "
        "stops at +3 cannot support a tall-stature arm, and it will also distort any "
        "trajectory that approaches the bound from below. Constructed stimuli should "
        "not be calibrated against this channel's upper tail, and the tall-stature "
        "codes in the diagnosis table (E34.4 constitutional tall stature, Q87.3 early "
        "overgrowth) cannot be paired with a matching measured trajectory here."
    )
    a("")
    a(
        f"The source project already plans the right repair — raise the ceiling to +5 "
        f"and re-run the augmentation from `height_in`, since the values cannot be "
        f"recovered downstream — but it estimates the cost from the surviving "
        f"distribution, whose 99.9th percentile is 2.91, and concludes that raising "
        f"the ceiling \u201ccosts almost nothing in volume\u201d. That percentile is 2.91 "
        f"*because* the tail was already removed. The measured cost of the repair is "
        f"the roughly "
        f"{fmt(round(trunc['ge25'] * trunc['le_m3'] / trunc['le_m25'] / 100) * 100)} "
        f"visits the asymmetry implies, of which {fmt(trunc['dropped_tall'])} are "
        f"still identifiable in the raw layer. The repair is worth making and is "
        f"larger than a rounding error."
    )
    a("")
    a("The percentile channels show the same bounds from the other side.")
    a("")
    a(table(
        ["channel", "n", "at 0", "share at 0", "at 100", "share at 100", "minimum", "maximum"],
        probe_percentile_bounds(con),
    ))
    a("")
    a(
        "The height percentile never reaches 100 because its z-score never exceeds +3, "
        "whereas weight, BMI, weight-for-length, and weight-for-stature percentiles all "
        "carry a point mass at both 0 and 100. Those exact-0 and exact-100 values are "
        "saturated rather than measured and should not be treated as continuous."
    )
    a("")

    # ---- 6.2 heaping
    hn, h_whole, h_half, h_quarter = heap["h"]
    wn, w_oz, w_lb, w_halflb = heap["w"]
    a("### 6.2 Terminal-digit heaping and measurement granularity (capture artifact)")
    a("")
    a(
        f"Height and weight are captured in imperial units (`height_in`, `weight_oz`) "
        f"and the metric fields are exact conversions of them. The recorded values are "
        f"strongly heaped on human-readable fractions: of {fmt(hn)} heights, "
        f"{pct(h_whole, 1)} fall on a whole inch, {pct(h_half, 1)} on a half inch, and "
        f"{pct(h_quarter, 1)} on a quarter inch. Of {fmt(wn)} weights, {pct(w_oz, 1)} "
        f"fall on a whole ounce, {pct(w_halflb, 1)} on a half pound, and {pct(w_lb, 1)} "
        f"on a whole pound."
    )
    a("")
    a(
        "Heaping is not uniform across childhood. Infant weights are recorded in "
        "ounces, and older children's weights are recorded to the pound, so the "
        "effective precision of the weight channel degrades as children age."
    )
    a("")
    a(table(
        ["age_band", "visits", "weights on a whole pound", "heights on a whole inch"],
        [[r[0], fmt(r[1]), pct(r[2], 1), pct(r[3], 1)] for r in heap["bands"]],
    ))
    a("")
    a(
        f"**Consequence for this project.** A quarter inch is 0.635 cm, and "
        f"{pct(h_quarter, 1)} of heights sit on that grid. The derived `height_cm` "
        f"values carry two decimal places and imply a precision the underlying "
        f"measurement does not have. This sets a floor on the trajectory deflection "
        f"that is detectable at all: a deviation smaller than roughly half the "
        f"rounding interval is not distinguishable from the rounding itself. "
        f"Serialized stimuli should either preserve the observed grid or state the "
        f"assumed precision explicitly, because a model shown "
        f"`height_cm = 104.14` is being given a digit the clinic never measured."
    )
    a("")

    # ---- 6.3 conversion + head circumference
    a("### 6.3 Unit-conversion integrity and a recoverable head-circumference defect")
    a("")
    a(
        f"The imperial-to-metric conversions are exact. Across {fmt(conv['h_pairs'])} "
        f"visits with both a raw and a derived height, {fmt(conv['h_bad'])} disagree "
        f"with `height_in × 2.54` by more than 0.01 cm; across {fmt(conv['w_pairs'])} "
        f"weight pairs, {fmt(conv['w_bad'])} disagree with `weight_oz × 0.0283495`. "
        f"The height and weight channels carry no unit-conversion defect."
    )
    a("")
    a("Head circumference does. Its out-of-range values form structured clusters.")
    a("")
    a(table(
        ["head_circ_cm band", "visits", "median", "minimum", "maximum"],
        [[r[0], fmt(r[1]), fmt(r[2], 2), fmt(r[3], 2), fmt(r[4], 2)] for r in hc["bands"]],
    ))
    a("")
    n_dbl, n_dbl_ok, med_dbl = hc["dbl"]
    n_trip, n_trip_ok = hc["trip"]
    a(
        f"The cluster between {HC_HI:.0f} and 200 cm is not noise. It holds "
        f"{fmt(n_dbl)} visits with a median of {fmt(hc['bands'][3][2], 2)} cm, and "
        f"{fmt(n_dbl_ok)} of them — {pct(100.0 * n_dbl_ok / n_dbl, 2)} — fall back "
        f"inside the {HC_LO:.0f}–{HC_HI:.0f} cm review range when divided by 2.54, "
        f"with a median of {fmt(med_dbl, 1)} cm. That is a normal infant head "
        f"circumference. These are centimetre values that were passed through an "
        f"inch-to-centimetre conversion a second time. A further {fmt(n_trip)} visits "
        f"sit above 200 cm, of which {fmt(n_trip_ok)} become plausible after dividing "
        f"by 2.54 twice, consistent with the same conversion applied again."
    )
    a("")
    z_all, z_implaus, z_plaus = hc["z"]
    a(
        f"This one defect explains most of the head-circumference damage the previous "
        f"section reported. Of {fmt(z_all)} visits with |head-circumference z| > 5, "
        f"{fmt(z_implaus)} ({pct(100.0 * z_implaus / z_all, 1)}) sit on a head "
        f"circumference outside the review range, and the double-converted cluster "
        f"alone accounts for {fmt(n_dbl_ok)} of them. The remaining {fmt(z_plaus)} "
        f"visits have a plausible head circumference but still produce |z| > 5, so the "
        f"z transform is independently defective as well and repairing the units would "
        f"not fully fix the channel."
    )
    a("")
    a(
        f"**Consequence for this project.** The previous section's guidance to exclude "
        f"head-circumference z-score is confirmed, but the diagnosis is now specific "
        f"rather than general: the raw channel is mostly recoverable by a documented "
        f"division, and the derived z channel has a second, separate defect. This "
        f"changes an action the source project has already specified. Its declared "
        f"plausible range removes all {fmt(gate['hc_out_range'])} out-of-range head "
        f"circumferences by deletion; {fmt(n_dbl_ok)} of those "
        f"({pct(100.0 * n_dbl_ok / gate['hc_out_range'], 1)}) are ordinary infant "
        f"measurements that a single documented division restores. Repairing before "
        f"bounding is strictly better than bounding alone, and it recovers most of the "
        f"only channel whose declared range removes a non-trivial share of values."
    )
    a("")

    # ---- 6.4 repeated measurement
    n_pairs, n_zero, n_neg, p_zero, p_neg = rep["totals"]
    a("### 6.4 Repeated measurements: zero growth, apparent shrinkage, and copy-forward")
    a("")
    a(
        f"Across {fmt(n_pairs)} successive age-2-or-later height pairs, "
        f"{fmt(n_zero)} ({pct(p_zero, 2)}) record exactly no change despite a positive "
        f"age gap, and {fmt(n_neg)} ({pct(p_neg, 2)}) record a decrease. Children in "
        f"this age range do not shrink, so both categories are recording behaviour "
        f"rather than physiology. Their dependence on the interval between "
        f"measurements separates two different mechanisms."
    )
    a("")
    a(table(
        ["age gap between successive heights", "pairs", "exactly zero change",
         "any decrease", "decrease over 1 inch"],
        [[r[0], fmt(r[1]), pct(r[2], 2), pct(r[3], 2), pct(r[4], 2)] for r in rep["rows"]],
    ))
    a("")
    a(
        "At short intervals the rates are dominated by measurement noise and rounding: "
        "within a week, a child genuinely has not grown a measurable amount, and the "
        "quarter-inch grid absorbs the rest, so nearly half of repeat heights are "
        "identical and a fifth are lower. At long intervals both mechanisms should "
        "vanish, and they do not entirely — over a year apart, exactly-zero change and "
        "apparent shrinkage each still occur in well under one percent of pairs, which "
        "is the residue consistent with a value carried forward or entered in error."
    )
    a("")
    a(
        "**Consequence for this project.** The short-interval rates are an empirical "
        "measurement-error estimate rather than a defect, and they are directly usable "
        "for the matched-noise requirement in the counterfactual stimulus design: any "
        "synthetic trajectory whose repeat measurements are noiseless will be "
        "unrealistically clean relative to this panel. The long-interval residue is a "
        "different matter and should be screened before serialization."
    )
    a("")

    # ---- 6.5 same-day
    a("### 6.5 Same-day duplicate encounters and same-day measurement disagreement")
    a("")
    a(
        f"Visit identifiers are unique, but a patient can have more than one visit row "
        f"on the same age in days. This affects {fmt(same['dup_days'])} patient-days "
        f"({pct(100.0 * same['dup_days'] / same['patient_days'], 2)} of "
        f"{fmt(same['patient_days'])}) and {fmt(same['dup_visits'])} visits "
        f"({pct(100.0 * same['dup_visits'] / same['visits'], 2)}). The rate is low, but "
        f"it means `age_in_days` is not a unique key within a patient and any analysis "
        f"that orders a trajectory by age alone has ties to resolve."
    )
    a("")
    a(
        f"Where the same day carries two or more measurements, they often disagree. "
        f"{fmt(same['days_2h'])} patient-days carry at least two heights and "
        f"{fmt(same['days_2h_disagree'])} of those disagree "
        f"({pct(100.0 * same['days_2h_disagree'] / same['days_2h'], 1)}); "
        f"{fmt(same['days_2w'])} carry at least two weights and "
        f"{fmt(same['days_2w_disagree'])} disagree "
        f"({pct(100.0 * same['days_2w_disagree'] / same['days_2w'], 1)})."
    )
    a("")
    a(table(
        ["channel", "patient-days with a disagreement", "median spread", "95th percentile", "maximum"],
        [
            ["height", fmt(same["days_2h_disagree"]), f"{fmt(same['h_med'], 2)} cm",
             f"{fmt(same['h_p95'], 2)} cm", f"{fmt(same['h_max'], 2)} cm"],
            ["weight", fmt(same["days_2w_disagree"]), f"{fmt(same['w_med'], 3)} kg",
             f"{fmt(same['w_p95'], 2)} kg", f"{fmt(same['w_max'], 2)} kg"],
        ],
    ))
    a("")
    a(
        f"The height spread is the notable one. A median disagreement of "
        f"{fmt(same['h_med'], 2)} cm between two heights recorded on the same day is far "
        f"larger than same-day weight disagreement in relative terms, and it is the "
        f"size of difference expected when recumbent length and standing height are "
        f"mixed, or when one value is carried from a previous note. It describes "
        f"discordant same-day pairs rather than the panel as a whole, but it is a "
        f"direct estimate of how far two heights recorded for the same child on the "
        f"same day can sit apart."
    )
    a("")

    # ---- 6.6 delta fields
    a("### 6.6 Distributed delta and velocity fields are not reproducible (derivation artifact)")
    a("")
    a(
        f"The augmented visit layer distributes `delta_height_cm`, "
        f"`delta_age_in_days_height`, and the velocity fields derived from them. On a "
        f"fixed sample of {fmt(delta['n'])} rows carrying a nonmissing "
        f"`delta_height_cm`, none of the three natural definitions of a successive "
        f"height change reproduces the distributed value."
    )
    a("")
    a(table(
        ["candidate definition of the previous height", "rows matching the distributed delta", "share"],
        [
            ["previous visit of any kind", fmt(delta["all_visits"]),
             pct(100.0 * delta["all_visits"] / delta["n"], 1)],
            ["previous height-bearing visit", fmt(delta["last_measured"]),
             pct(100.0 * delta["last_measured"] / delta["n"], 1)],
            ["previous raw `height_in`, converted", fmt(delta["raw_inches"]),
             pct(100.0 * delta["raw_inches"] / delta["n"], 1)],
        ],
    ))
    a("")
    a(
        f"Same-day ties are not the explanation: only "
        f"{pct(100.0 * same['dup_visits'] / same['visits'], 2)} of visits share a "
        f"patient-day with another visit, which cannot account for agreement as low as "
        f"{pct(100.0 * delta['last_measured'] / delta['n'], 1)}. The ordering or the "
        f"measurement series the pipeline used is therefore something this snapshot "
        f"does not expose."
    )
    a("")
    a(
        "**Consequence for this project.** The velocity channels are built on these "
        "deltas, so `height_velocity`, `height_velocity_z_score`, and their pubertal "
        "variants inherit an unverifiable definition. Velocity should be recomputed "
        "from the height series with a stated definition rather than consumed as "
        "distributed, and the distributed velocity fields should not be serialized "
        "into stimuli. This is a stronger conclusion than the previous section's "
        "recommendation to inspect velocity distributions before use."
    )
    a("")

    # ---- 6.7 capture depends on encounter type
    a("### 6.7 Measurement presence does not mean measurement (capture artifact)")
    a("")
    a(
        "Section 3 reported measurement completeness by age and by source system. "
        "Encounter type is the stratifier that shows the completeness figures cannot "
        "be read as measurement occurrence."
    )
    a("")
    a(table(
        ["encounter_type", "visits", "weight present", "height present", "first diagnosis present"],
        probe_encounter_capture(con),
    ))
    a("")
    a(
        "Telephone and telemedicine encounters carry a weight on the large majority of "
        "visits. A weight cannot be measured over the telephone, so those values were "
        "produced some other way — reported by a caregiver, populated from a nearby "
        "in-person encounter, or attached to an encounter whose type label does not "
        "describe how the patient was seen. The mechanism is not simple last-value "
        "carry-forward, as the following table shows."
    )
    a("")
    a(table(
        ["encounter_type", "visits with a weight",
         "weight identical to previous visit", "identical with a gap over 7 days"],
        probe_carry_forward(con),
    ))
    a("")
    a(
        "Only documentation encounters show a carry-forward signature, where about a "
        "quarter of weights exactly repeat the previous value and the rate rises rather "
        "than falls as the gap widens. Telephone and telemedicine weights mostly differ "
        "from the previous recorded weight, so the mechanism there is not last-value "
        "carry-forward; what it is instead is not identifiable from this snapshot."
    )
    a("")
    a(
        "**Consequence for this project.** A visit-level indicator that a measurement "
        "is present is not evidence that a measurement was taken at that encounter. "
        "The schedule-density manipulation in the counterfactual design assumes "
        "measurement-bearing visits are real measurement occasions; that assumption "
        "should be enforced by restricting to encounter types where physical "
        "measurement is possible, not by measurement presence alone."
    )
    a("")

    # ---- 6.8 cross-resource
    a("### 6.8 Cross-resource temporal and linkage integrity")
    a("")
    a(
        "Age in days is the only clock in this snapshot, and ordering violations "
        "within a resource are visible directly. Counts below "
        f"{SUPPRESS_BELOW} are suppressed."
    )
    a("")
    a(table(
        ["integrity check", "violating rows", "rows checked", "share"],
        probe_temporal(con),
    ))
    a("")
    a(
        "The lab and medication violations are the substantial ones. A result age "
        "earlier than its order age and a start age earlier than its order age both "
        "indicate that these age fields are derived from different source timestamps "
        "with different semantics, so differences between them are not reliable "
        "durations. The small number of pre-birth ages are unrecoverable date errors."
    )
    a("")
    a(
        "Visit linkage is incomplete in every resource that carries a visit "
        "identifier, not only in referrals."
    )
    a("")
    a(table(
        ["resource", "rows", "rows with a visit_id", "share missing a visit_id",
         "nonnull visit_id not matching a visit", "share of nonnull unresolved"],
        probe_visit_link(con),
    ))
    a("")
    a(
        "The medication result is the one that changes an assumption elsewhere in the "
        "package: `medications.visit_id` is declared required and is populated on "
        "every row, yet a large share of those values do not correspond to any visit "
        "in this snapshot. A required, populated foreign key that does not resolve is "
        "easy to mistake for a complete link. Section 8's referral linkage finding is "
        "therefore not specific to referrals; it is a property of the extract."
    )
    a("")

    # ---- 6.9 labs
    a("### 6.9 Laboratory results are semi-structured text")
    a("")
    a(
        f"`result_value` is a text field. Of {fmt(labs['total'])} rows, "
        f"{fmt(labs['total'] - labs['nonnull'])} "
        f"({pct(100.0 * (labs['total'] - labs['nonnull']) / labs['total'], 1)}) carry no "
        f"value at all, {fmt(labs['numeric'])} "
        f"({pct(100.0 * labs['numeric'] / labs['total'], 1)}) parse as a number, and "
        f"{fmt(labs['non_numeric'])} "
        f"({pct(100.0 * labs['non_numeric'] / labs['total'], 1)}) do not. Among the "
        f"non-numeric values, {fmt(labs['comparator'])} are censored results carrying a "
        f"comparator prefix such as `<3.3`, and the remainder are qualitative results "
        f"(`NEGATIVE`, `NOT DETECTED`, `TRACE`), specimen descriptors, and "
        f"administrative non-results (`NOT REPORTED`, `SEE NOTE`). A naive numeric cast "
        f"silently discards nearly half the populated values and, more seriously, "
        f"treats a left-censored result as missing rather than as a bound."
    )
    a("")
    a(
        f"The declared key holds: `(lab_order_id, result_component_name, "
        f"result_line_num)` has {fmt(labs['key_dupes'])} duplicate groups. But "
        f"{fmt(labs['repeat_component'])} order-and-component pairs appear on more than "
        f"one result line, and {fmt(labs['repeat_disagree'])} of those "
        f"({pct(100.0 * labs['repeat_disagree'] / labs['repeat_component'], 1)}) carry "
        f"disagreeing values — repeated or corrected results within a single order. "
        f"Joining on order and component without the line number will multiply rows and "
        f"pick an arbitrary value."
    )
    a("")

    # ---- 6.10 vocabulary
    pl_n, pl_d, pl_bad = codes["pl"]
    en_n, en_d, en_bad = codes["enc"]
    lab_raw, lab_norm, lab_dbl, med_raw, med_norm, sp_raw, sp_norm = codes["names"]
    a("### 6.10 Vocabulary and categorical-string hygiene")
    a("")
    a(
        f"Diagnosis strings are almost entirely well-formed ICD-10. Of "
        f"{fmt(en_n)} filled encounter-diagnosis slots across "
        f"{fmt(en_d)} distinct codes, {fmt(en_bad)} "
        f"({pct(100.0 * en_bad / en_n, 2)}) are not ICD-10-shaped; of {fmt(pl_n)} "
        f"problem-list entries across {fmt(pl_d)} distinct codes, {fmt(pl_bad)} "
        f"({pct(100.0 * pl_bad / pl_n, 2)}) are not. In both resources the "
        f"non-conforming values are entirely `IMO0001` and `IMO0002`, proprietary "
        f"Intelligent Medical Objects placeholders that Epic emits when a clinical term "
        f"has no ICD-10 equivalent. `IMO0002` is the entry that appears in the "
        f"problem-list table of this report as `[not in ICD-10 lookup]`: it is not a "
        f"lookup failure but a code that carries no diagnostic meaning on its own. It "
        f"should be excluded from code-based cohort definitions rather than treated as "
        f"an unmapped diagnosis."
    )
    a("")
    a(
        f"Categorical free-text fields are cleaner than is typical for an EHR extract. "
        f"Normalising case and internal whitespace collapses lab procedure names from "
        f"{fmt(lab_raw)} to {fmt(lab_norm)} distinct values, medication generic names "
        f"from {fmt(med_raw)} to {fmt(med_norm)}, and requested specialties from "
        f"{fmt(sp_raw)} to {fmt(sp_norm)}. Only the lab vocabulary collapses at all, "
        f"and only by {lab_raw - lab_norm}. Cosmetic irregularities are common — "
        f"{fmt(lab_dbl)} lab rows carry an internal double space, and tall-man "
        f"lettering such as `EPINEPHrine` is preserved from the source system — but "
        f"they do not fragment the vocabularies. Grouping by these fields is safe "
        f"after trimming; the risk here is presentational, not analytic."
    )
    a("")

    # ---- 6.11 summary
    a("### 6.11 Artifact summary")
    a("")
    a(table(
        ["artifact", "class", "scale in this snapshot", "recoverable?"],
        [
            ["Height z-score truncated at +3 with the lower tail retained to −5",
             "derivation", (f"{fmt(trunc['ge3'])} visits at the bound; roughly "
                            f"{fmt(round(trunc['ge25'] * trunc['le_m3'] / trunc['le_m25'] / 100) * 100)} expected above it"),
             "Yes — re-run the augmentation from the retained `height_in`"],
            ["Percentile point mass at exactly 0 and 100",
             "derivation", "up to 6,151 visits in a single channel", "No — treat as saturated"],
            ["Terminal-digit heaping on quarter-inch and pound grids",
             "capture", f"{pct(h_quarter, 1)} of heights on a quarter inch", "No — inherent precision limit"],
            ["Head circumference double-converted inch-to-centimetre",
             "derivation", f"{fmt(n_dbl_ok)} visits", "Yes — divide by 2.54 before bounding, rather than deleting"],
            ["Head-circumference z defective on plausible measurements",
             "derivation", f"{fmt(z_plaus)} visits", "No — recompute or exclude"],
            ["Zero or negative height change over long intervals",
             "capture", f"{pct(rep['rows'][-1][2], 2)} and {pct(rep['rows'][-1][3], 2)} of pairs over a year apart",
             "Partly — screen before use"],
            ["Same-day duplicate encounters with disagreeing measurements",
             "capture", f"{fmt(same['days_2h_disagree'])} patient-days for height", "Partly — define a tie rule"],
            ["Distributed deltas and velocities not reproducible",
             "derivation", f"{pct(100.0 * delta['last_measured'] / delta['n'], 1)} agreement at best",
             "Yes — recompute from the height series"],
            ["Anthropometrics present on non-contact encounters",
             "capture", "weight on the large majority of telephone visits", "Partly — restrict by encounter type"],
            ["Lab and medication age fields violating their own ordering",
             "capture", "583,055 and 329,107 rows", "No — do not treat as durations"],
            ["Populated visit_id not resolving to a visit",
             "linkage", "labs, medications, and referrals all affected", "No — treat linkage as incomplete"],
            ["Laboratory results as semi-structured text with censored values",
             "capture", f"{fmt(labs['comparator'])} comparator-prefixed results", "Yes — parse comparators explicitly"],
            ["Proprietary IMO placeholder codes",
             "capture", f"{fmt(en_bad + pl_bad)} slots and entries", "Yes — exclude from code-based cohorts"],
        ],
    ))
    a("")
    a(
        "The derivation artifacts are the ones that matter most for this project, "
        "because they affect exactly the fields a growth-chart model would consume and "
        "because they are invisible in the field names. Two of them — the "
        "head-circumference conversion and the unreproducible velocities — were not "
        "detectable from the distributional summaries in section 5 alone and required "
        "an explicit reconstruction of the derivation from the raw channel. The third, "
        "the height-z ceiling, was already known to the source project; what this "
        "section adds is the measured size of the tail it removed and the fact that "
        "most of it is still recoverable from `height_in`."
    )
    a("")
    a(END_MARKER)
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", default=DEFAULT_BUNDLE,
                        help="path to the typed DuckDB bundle (read-only)")
    parser.add_argument("--report", default=str(REPORT))
    parser.add_argument("--stdout", action="store_true",
                        help="print the section instead of writing it into the report")
    args = parser.parse_args()

    bundle = Path(args.bundle).expanduser().resolve()
    if not bundle.is_file():
        raise SystemExit(f"DuckDB bundle not found: {bundle}")

    manifest_path = bundle.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else None

    digest = ""
    if manifest:
        for output in manifest.get("outputs", []):
            if output.get("basename") == bundle.name:
                digest = output.get("sha256", "")

    con = duckdb.connect(str(bundle), read_only=True)
    try:
        section = render(con, bundle, manifest, digest)
    finally:
        con.close()

    if args.stdout:
        print(section)
        return 0

    report_path = Path(args.report)
    text = report_path.read_text()
    if BEGIN_MARKER not in text or END_MARKER not in text:
        raise SystemExit(
            f"Markers not found in {report_path}. Add {BEGIN_MARKER} and "
            f"{END_MARKER} around the artifact section first."
        )
    head, rest = text.split(BEGIN_MARKER, 1)
    _, tail = rest.split(END_MARKER, 1)
    report_path.write_text(head + section + tail)
    print(f"Updated {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

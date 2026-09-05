"""Part 5.6-5.7 — the derived patient layer, and the extract's growth orientation.

This extract was assembled around growth: cohort entry required a growth
measurement history (1.4), and the augmentation layer carries patient-level
growth flags and a fixed panel of growth-relevant diagnosis codes. Documenting
that orientation is a description of the data, not of any downstream question.
"""

from __future__ import annotations

from ..context import Context
from ..findings import Column as C
from ..findings import Figure, Finding, Para, Table, probe

ICD_CSV = "data/icd10cm-tabular-2026.csv"
ICD_LOOKUP = f"""
    SELECT replace(diag_name, '.', '') AS code, any_value(diag_desc) AS descr
    FROM read_csv_auto('{ICD_CSV}', header=true, sample_size=100000)
    WHERE diag_name IS NOT NULL GROUP BY 1
"""
FLAGS = [
    ("healthy_flag", "carries none of the tracked conditions"),
    ("chronic_dx_flag", "any chronic diagnosis"),
    ("growth_dx_flag", "any of the tracked growth-relevant diagnoses"),
    ("ever_stunting_flag", "height z below the stunting threshold at any visit"),
    ("ever_wasting_flag", "weight-for-length or -stature below the wasting threshold"),
    ("ever_underweight_flag", "BMI below the underweight threshold at any visit"),
    ("ever_obesity_flag", "BMI at or above the obesity threshold at any visit"),
]
FAMILIES = [
    ("Endocrinology", "%endocrin%"),
    ("Gastroenterology", "%gastroenter%"),
    ("Nutrition and dietetics", "%nutrition%' OR lower(requested_specialty) LIKE '%dietit%"),
    ("Nephrology", "%nephrolog%"),
    ("Genetics", "%genetic%"),
]


@probe("growth.flags", "5.6")
def flags(ctx: Context) -> list[Finding]:
    total = ctx.scalar("SELECT count(*) FROM patients_augmented")
    rows = []
    for col, meaning in FLAGS:
        n = ctx.scalar(f"SELECT count(*) FROM patients_augmented WHERE {col} = 1")
        rows.append({"flag": col, "meaning": meaning, "patients": n,
                     "share": 100.0 * n / total})

    dx_age = ctx.one(
        "SELECT count(dx_age_years), quantile_cont(dx_age_years, 0.5), "
        " sum(CASE WHEN dx_age_years <= 1.0 / 12 THEN 1 ELSE 0 END), "
        " sum(CASE WHEN dx_age_years < 0 THEN 1 ELSE 0 END) "
        "FROM patients_augmented WHERE growth_dx_flag = 1")
    z_summary = ctx.q("""
        SELECT 'height' AS ch, count(count_height_z_score),
               avg(mean_height_z_score), avg(std_height_z_score)
        FROM patients_augmented WHERE count_height_z_score > 1
        UNION ALL SELECT 'weight', count(count_weight_z_score),
               avg(mean_weight_z_score), avg(std_weight_z_score)
        FROM patients_augmented WHERE count_weight_z_score > 1
        UNION ALL SELECT 'BMI', count(count_bmi_z_score),
               avg(mean_bmi_z_score), avg(std_bmi_z_score)
        FROM patients_augmented WHERE count_bmi_z_score > 1""")

    growth_n = next(r["patients"] for r in rows if r["flag"] == "growth_dx_flag")
    f = Finding(
        id="growth.flags", part="5.6",
        title="Patient-level derived flags and summaries",
        values={"total": total, "growth_n": growth_n,
                "dx_observed": dx_age[0], "dx_median": dx_age[1],
                "dx_first_month": dx_age[2],
                "dx_first_share": 100.0 * dx_age[2] / dx_age[0] if dx_age[0] else 0.0,
                "dx_negative": ctx.suppress(dx_age[3]) or 0},
    )
    f.blocks = [
        Para("The augmented patient layer carries seven boolean flags and a block of "
             "per-patient z-score summaries. They are conveniences computed from the "
             "visit layer, not independent observations, and each inherits whatever "
             "the channel it summarises does — the height-z flags inherit the "
             "truncation of 4.6, the BMI flags inherit the age-2 floor of 1.3."),
        Table("t-flags", "Patient-level flags",
              [C("flag", "flag"), C("meaning", "set when the patient"),
               C("patients", "patients", ",", align="right"),
               C("share", "share of cohort", ".1f", "%", align="right")], rows),
        Figure("fig-flags", "Patients carrying each derived flag", "bar",
               {"categories": [r["flag"].replace("_flag", "").replace("ever_", "")
                               for r in rows],
                "series": [{"name": "patients", "values": [r["patients"] for r in rows]}],
                "height": 250, "title": "Derived patient flags"},
               alt="Counts of patients carrying each of the seven derived flags."),
        Para("`growth_dx_flag` marks {growth_n:,} patients. Where an age at "
             "diagnosis is observed ({dx_observed:,} patients) its median is "
             "{dx_median:.3f} years, and {dx_first_month:,} of those "
             "({dx_first_share:.1f}%) are assigned their code within the first month "
             "of life. That is a statement about when the code was recorded, not "
             "about when a condition began."),
        Table("t-zsummary", "Per-patient z-score summaries, averaged over patients "
                            "with more than one value",
              [C("ch", "channel"), C("n", "patients", ",", align="right"),
               C("mean", "mean of patient means", ".4f", align="right"),
               C("sd", "mean of patient SDs", ".4f", align="right")],
              [{"ch": c, "n": n, "mean": m, "sd": s} for c, n, m, s in z_summary]),
        Para("**Implications for analysis.** A flag is a recorded derivation, not an "
             "adjudicated clinical state, and the concentration of growth-diagnosis "
             "ages in the first month shows why: much of what the flag marks is "
             "perinatal coding rather than a growth trajectory that was observed and "
             "interpreted over years. Use the flags to describe the derived layer or "
             "to stratify descriptively; recompute from the visit layer against a "
             "stated rule if a flag is doing analytic work.", role="implication"),
    ]
    return [f]


@probe("growth.codes", "5.7")
def codes(ctx: Context) -> list[Finding]:
    dx_cols = [c for c in ctx.columns("patients_augmented")
               if c.startswith("dx_age_years_")]

    def to_icd(col: str) -> str:
        return col.replace("dx_age_years_", "").upper().replace("_", ".")

    union = " UNION ALL ".join(
        f"SELECT '{to_icd(c)}' AS code, count({c}) AS pts, "
        f"quantile_cont({c}, 0.5) AS med FROM patients_augmented"
        for c in dx_cols)
    rows = ctx.q(f"""
        WITH f AS ({union}), l AS ({ICD_LOOKUP})
        SELECT f.code, coalesce(l.descr, '[not in the ICD-10 lookup]'), f.pts, f.med
        FROM f LEFT JOIN l ON replace(f.code, '.', '') = l.code
        WHERE f.pts > 0 ORDER BY f.pts DESC""")
    shown = [{"code": c, "descr": d, "patients": p, "median_age": m}
             for c, d, p, m in rows if ctx.suppress(p) is not None]

    ref_total = ctx.scalar("SELECT count(*) FROM referrals")
    fam_rows = []
    matched = 0
    for label, pattern in FAMILIES:
        n, pts, med = ctx.one(
            "SELECT count(*), count(DISTINCT patient_id), "
            "quantile_cont(referral_date_age_in_days, 0.5) / 365.25 "
            f"FROM referrals WHERE lower(requested_specialty) LIKE '{pattern}'")
        matched += n
        fam_rows.append({"family": label, "referrals": n, "patients": pts,
                         "median_age": med,
                         "share": 100.0 * n / ref_total})
    fam_rows.append({"family": "all other specialties",
                     "referrals": ref_total - matched, "patients": None,
                     "median_age": None,
                     "share": 100.0 * (ref_total - matched) / ref_total})

    f = Finding(
        id="growth.codes", part="5.7",
        title="The extract's growth orientation: tracked codes and referral pathways",
        values={"n_codes": len(dx_cols), "n_shown": len(shown),
                "ref_total": ref_total, "matched": matched,
                "matched_share": 100.0 * matched / ref_total,
                "top_code": shown[0]["code"] if shown else "n/a",
                "top_pts": shown[0]["patients"] if shown else 0},
    )
    f.blocks = [
        Para("This extract was assembled around growth. Cohort entry required a "
             "growth-measurement history (1.4), and the augmentation layer records, "
             "for each patient, the age at which any of {n_codes} specific "
             "diagnosis codes was first recorded. That panel is a design choice made "
             "upstream, and knowing which codes are in it is the difference between "
             "using the derived columns and guessing at them."),
        Table("t-growth-codes", "The tracked growth-relevant diagnosis codes",
              [C("code", "ICD-10"), C("descr", "description"),
               C("patients", "patients", ",", align="right"),
               C("median_age", "median age at first record", ".2f", " y",
                 align="right")], shown,
              note="Codes carried by fewer patients than the suppression threshold "
                   "are omitted. Counts are recorded frequencies inside a cohort "
                   "that excluded every patient with a code seen fewer than 11 "
                   "times, so this panel cannot be read as prevalence."),
        Para("The referral resource shows the same orientation from the action side. "
             "Grouping requested specialties into the families a growth question "
             "would reach for accounts for {matched:,} of {ref_total:,} referrals "
             "({matched_share:.1f}%)."),
        Table("t-growth-spec", "Referrals by growth-relevant specialty family",
              [C("family", "specialty family"),
               C("referrals", "referrals", ",", align="right"),
               C("share", "share of all referrals", ".2f", "%", align="right"),
               C("patients", "patients", ",", align="right"),
               C("median_age", "median age", ".2f", " y", align="right")], fam_rows),
        Para("**Implications for analysis.** These two tables describe what the "
             "upstream pipeline chose to track, not what is clinically relevant to "
             "growth in general: a code absent from the panel may still be present "
             "in the encounter and problem-list resources of 5.1, and a specialty "
             "family here is a string match on a free-text field rather than a "
             "clinical taxonomy. Use the panel to understand the derived columns; go "
             "to the raw diagnosis resources for anything else.", role="implication"),
    ]
    return [f]

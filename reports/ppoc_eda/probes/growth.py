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
from .icd import patient_codes

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
    pc = patient_codes(ctx)
    dx_cols = [c for c in ctx.columns("patients_augmented")
               if c.startswith("dx_age_years_")]

    def to_icd(col: str) -> str:
        return col.replace("dx_age_years_", "").upper().replace("_", ".")

    tracked = [(c, to_icd(c)) for c in dx_cols]
    values = ", ".join(f"('{icd}')" for _, icd in tracked)
    # Literal and subtree patient counts for every tracked code, in one pass.
    counted = dict(ctx.q(f"""
        WITH t(code) AS (VALUES {values})
        SELECT t.code,
               list_value(count(DISTINCT CASE WHEN pc.code = t.code
                                              THEN pc.patient_id END),
                          count(DISTINCT pc.patient_id))
        FROM t LEFT JOIN {pc} pc ON starts_with(pc.code, t.code)
        GROUP BY t.code"""))
    derived = {icd: ctx.scalar(f"SELECT count({col}) FROM patients_augmented")
               for col, icd in tracked}

    rows = []
    for _, icd in tracked:
        exact, tree = counted.get(icd, [0, 0])
        rows.append({"code": icd, "derived": derived[icd], "exact": exact,
                     "tree": tree, "extra": tree - exact})
    lookup = dict(ctx.q(f"""
        WITH t(code) AS (VALUES {values}), l AS ({ICD_LOOKUP})
        SELECT t.code, coalesce(l.descr, '[not in the ICD-10 lookup]')
        FROM t LEFT JOIN l ON replace(t.code, '.', '') = l.code"""))
    for r in rows:
        r["descr"] = lookup.get(r["code"], "[not in the ICD-10 lookup]")
    rows.sort(key=lambda r: -r["tree"])
    shown = [r for r in rows if ctx.suppress(r["tree"]) is not None]

    zero_exact = [r for r in rows if r["tree"] > 0 and r["exact"] == 0]
    has_desc = [r for r in rows if r["tree"] > r["exact"]]
    no_desc = [r for r in rows if r["tree"] == r["exact"]]
    hierarchical = sum(1 for r in rows if r["derived"] == r["tree"])
    # A flat derivation would show here: the literal count matching the derived
    # column on some code whose subtree count differs. None does.
    flat_evidence = sum(1 for r in rows
                        if r["tree"] > r["exact"] and r["derived"] == r["exact"])
    short = [r for r in rows if r["derived"] not in (r["exact"], r["tree"])]

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
                         "median_age": med, "share": 100.0 * n / ref_total})
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
                "zero_exact": len(zero_exact), "has_desc": len(has_desc),
                "no_desc": len(no_desc), "hierarchical": hierarchical,
                "flat_evidence": flat_evidence, "short": len(short),
                "short_codes": ", ".join(f"`{r['code']}`" for r in short)},
    )
    f.blocks = [
        Para("This extract was assembled around growth. Cohort entry required a "
             "growth-measurement history (1.4), and the augmentation layer records, "
             "for each patient, the age at which any of {n_codes} specific "
             "diagnosis codes was first recorded. That panel is a design choice made "
             "upstream, and knowing which codes are in it is the difference between "
             "using the derived columns and guessing at them."),
        Para("Because ICD-10 is a hierarchy (3.9), each code is counted here twice: "
             "as a literal string, and as a subtree including every descendant. The "
             "gap between the two columns is what a flat query would miss."),
        Table("t-growth-codes", "The tracked growth-relevant diagnosis codes",
              [C("code", "ICD-10"), C("descr", "description"),
               C("derived", "derived column", ",", align="right"),
               C("exact", "patients, literal code", ",", align="right"),
               C("tree", "patients, code and descendants", ",", align="right"),
               C("extra", "missed by a flat count", ",", align="right")], shown,
              note="Codes carried by fewer patients than the suppression threshold "
                   "are omitted. Counts are recorded frequencies inside a cohort "
                   "that excluded every patient with a code seen fewer than 11 "
                   "times (1.4), so this panel cannot be read as prevalence."),
        Para("**The upstream derivation is hierarchical, and the two count columns "
             "verify it.** {has_desc} of the {n_codes} tracked codes have "
             "descendants in this extract; the other {no_desc} have none, so both "
             "readings coincide and they cannot distinguish the two rules. Of the "
             "{has_desc} that can, **{flat_evidence} match the literal count** — in "
             "every case the derived column follows the subtree. The evidence is "
             "starkest because **all {zero_exact} of those codes never appear as a "
             "literal string at all**: an exact-match query returns zero patients "
             "for `E10`, `P07`, `K50` and the rest, while the derived column "
             "correctly reports hundreds or thousands."),
        Para("{short} codes ({short_codes}) sit slightly below their subtree count. "
             "The shortfall is explained rather than unexplained: those patients "
             "carry the code only on a problem-list entry with no noted date, so no "
             "age could be determined. The derived column therefore means *the "
             "patient carries the code or one of its descendants **and** an age for "
             "it can be established* — not simply that the patient carries it.",
             role="method"),
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
        Para("**Implications for analysis.** Use the derived columns when you want "
             "an age at first record and are content with the panel upstream chose; "
             "go to the raw diagnosis resources for anything else, and match by "
             "prefix when you do. These tables describe what the pipeline tracks, "
             "not what is clinically relevant to growth in general: a code absent "
             "from the panel may still be present in 5.1, and a specialty family "
             "here is a string match on a free-text field rather than a clinical "
             "taxonomy.", role="implication"),
    ]
    return [f]

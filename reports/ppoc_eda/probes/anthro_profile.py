"""Part 4.9-4.11 — growth profile, within-child dependence, and BMI."""

from __future__ import annotations

from ..context import Context
from ..findings import Column as C
from ..findings import Figure, Finding, Para, Table, probe

BANDS = [(0, 2, "0-2"), (2, 5, "2-5"), (5, 10, "5-10"),
         (10, 15, "10-15"), (15, 19, "15-18")]
CATEGORIES = ["underweight", "normal", "overweight", "obese"]


@probe("anthro.profile", "4.9")
def profile(ctx: Context) -> list[Finding]:
    rows = []
    for lo, hi, label in BANDS:
        for sex in ("F", "M"):
            w = (f"age_in_years >= {lo} AND age_in_years < {hi} AND sex = '{sex}'")
            r = ctx.one(f"""
                SELECT count(*), count(DISTINCT patient_id),
                       avg(height_cm), avg(height_z_score), stddev_samp(height_z_score),
                       avg(weight_z_score), avg(bmi_z_score)
                FROM visits_augmented WHERE {w}""")
            rows.append({
                "band": label, "sex": sex, "visits": r[0], "patients": r[1],
                "height_cm": r[2], "height_z": r[3], "height_z_sd": r[4],
                "weight_z": r[5], "bmi_z": r[6],
            })
    fz = [round(r["height_z"], 3) for r in rows if r["sex"] == "F"]
    mz = [round(r["height_z"], 3) for r in rows if r["sex"] == "M"]

    f = Finding(
        id="anthro.profile", part="4.9",
        title="Age- and sex-stratified growth profile",
        values={"n_bands": len(BANDS),
                "worst_z": min(r["height_z"] for r in rows),
                "best_z": max(r["height_z"] for r in rows)},
    )
    f.blocks = [
        Para("A reference table for anyone who needs to know what ordinary looks "
             "like in this extract before deciding what is unusual. Mean z-scores "
             "run from {worst_z:.2f} to {best_z:.2f} across the age and sex cells, "
             "so the cohort sits close to the reference population on average even "
             "though it is not a sample of one."),
        Table("t-profile", "Measurements and derived z-scores by age band and sex",
              [C("band", "age band (years)"), C("sex", "sex"),
               C("visits", "visits", ",", align="right"),
               C("patients", "patients", ",", align="right"),
               C("height_cm", "mean height", ".1f", " cm", align="right"),
               C("height_z", "mean height z", ".3f", align="right"),
               C("height_z_sd", "height z SD", ".3f", align="right"),
               C("weight_z", "mean weight z", ".3f", align="right"),
               C("bmi_z", "mean BMI z", ".3f", align="right")], rows),
        Figure("fig-profile", "Mean height z-score by age band and sex", "line",
               {"x": [b for _, _, b in BANDS],
                "series": [{"name": "female", "values": fz},
                           {"name": "male", "values": mz}],
                "height": 280, "title": "Mean height z by age and sex"},
               alt="Mean height z-score across five age bands for each sex."),
        Para("**Implications for analysis.** Read the height-z column against 4.6 "
             "before using it: its upper tail is truncated at +3, so every mean here "
             "is pulled very slightly downward relative to an untruncated reference, "
             "and the effect grows in the bands where tall children are most "
             "numerous. The SD column is the more useful one for scaling, and it is "
             "close to 1 by construction of the z transform rather than as a "
             "finding.", role="implication"),
    ]
    return [f]


@probe("anthro.dependence", "4.10")
def dependence(ctx: Context) -> list[Finding]:
    n_pat, between, within = ctx.one("""
        WITH per AS (
            SELECT patient_id, avg(height_z_score) AS m,
                   stddev_samp(height_z_score) AS s, count(*) AS n
            FROM visits_augmented
            WHERE height_z_score IS NOT NULL AND age_in_years >= 2
            GROUP BY 1 HAVING count(*) >= 2)
        SELECT count(*), stddev_samp(m), sqrt(avg(s * s)) FROM per""")
    pairs, rho = ctx.one("""
        WITH s AS (
            SELECT patient_id, age_in_days, min(height_z_score) AS z
            FROM visits_augmented
            WHERE height_z_score IS NOT NULL AND age_in_years >= 2
            GROUP BY 1, 2 HAVING count(DISTINCT height_z_score) = 1),
        l AS (SELECT z, lag(z) OVER w AS pz FROM s
              WINDOW w AS (PARTITION BY patient_id ORDER BY age_in_days))
        SELECT count(*), corr(z, pz) FROM l WHERE pz IS NOT NULL""")
    icc = between ** 2 / (between ** 2 + within ** 2)

    f = Finding(
        id="anthro.dependence", part="4.10",
        title="Within-child dependence in the height channel",
        values={"n_pat": n_pat, "between": between, "within": within,
                "icc": icc, "pairs": pairs, "rho": rho,
                "eff": 1.0 / icc},
    )
    f.blocks = [
        Para("Repeated measurements of one child are not independent observations, "
             "and the size of that dependence decides how much information a visit "
             "count actually carries. Measured on the height z-score at age 2 or "
             "later, across {n_pat:,} patients with at least two values."),
        Table("t-dependence", "Variance components and serial correlation",
              [C("quantity", "quantity"), C("value", "value", ".4f", align="right"),
               C("meaning", "what it says")],
              [{"quantity": "between-child SD of patient means", "value": between,
                "meaning": "how far children sit from one another"},
               {"quantity": "within-child SD about a patient's own mean",
                "value": within, "meaning": "how much one child's channel moves"},
               {"quantity": "implied intraclass correlation", "value": icc,
                "meaning": "share of variance that is between children"},
               {"quantity": "lag-1 autocorrelation", "value": rho,
                "meaning": f"correlation of successive values, {pairs:,} pairs"}]),
        Para("A child's height z-score is strongly self-similar: successive values "
             "correlate at {rho:.3f}, and {icc:.1%} of the total variance is "
             "between children rather than within them. The design-effect "
             "consequence is blunt: in the limit of many measurements a child "
             "contributes about {eff:.1f} independent observations, not one per "
             "visit, however many visits are recorded."),
        Para("**Implications for analysis.** Resample and model at the patient "
             "level, not the visit level: a visit-level standard error on any "
             "quantity aggregated across this panel will be far too small. And "
             "treat these as sample statistics rather than the parameters of a "
             "process that would generate them — a patient's mean carries residual "
             "variation as well as the child's own level, so the between-child SD of "
             "patient means overstates the underlying channel SD, while the sample "
             "SD within a positively autocorrelated series understates its marginal "
             "SD. Calibrate a generative model against these by simulation rather "
             "than by setting its parameters equal to them.", role="method"),
    ]
    return [f]


@probe("anthro.bmi", "4.11")
def bmi(ctx: Context) -> list[Finding]:
    n, med, p95, off = ctx.one("""
        WITH q AS (
            SELECT abs(bmi - weight_kg / pow(height_cm / 100.0, 2)) AS d
            FROM visits_augmented
            WHERE bmi IS NOT NULL AND weight_kg IS NOT NULL
              AND height_cm IS NOT NULL AND height_cm > 0)
        SELECT count(*), quantile_cont(d, 0.5), quantile_cont(d, 0.95),
               sum(CASE WHEN d > 0.1 THEN 1 ELSE 0 END) FROM q""")

    total = ctx.scalar("SELECT count(*) FROM visits_augmented "
                       "WHERE bmi_category IS NOT NULL")
    cats = []
    for name in CATEGORIES:
        v, p = ctx.one("SELECT count(*), count(DISTINCT patient_id) "
                       f"FROM visits_augmented WHERE bmi_category = '{name}'")
        cats.append({"category": name, "visits": v, "patients": p,
                     "share": 100.0 * v / total})
    flag_rows = []
    for col, label in (("underweight_flag", "underweight"),
                       ("obesity_flag", "obesity")):
        n_flag = ctx.scalar(f"SELECT count(*) FROM visits_augmented WHERE {col} = 1")
        flag_rows.append({"flag": col, "label": label, "visits": n_flag})

    f = Finding(
        id="anthro.bmi", part="4.11",
        title="BMI: recomputation and recorded categories",
        values={"n": n, "med": med, "p95": p95, "off": off,
                "off_share": 100.0 * off / n, "total": total,
                "obese_share": next(c["share"] for c in cats if c["category"] == "obese"),
                "over_share": next(c["share"] for c in cats
                                   if c["category"] == "overweight")},
    )
    f.blocks = [
        Para("BMI is the one derived channel that can be checked against its own "
             "inputs. Across {n:,} visits carrying a BMI together with both a weight "
             "and a height, recomputing weight in kilograms over height in metres "
             "squared gives a median absolute difference of {med:.1e} and a 95th "
             "percentile of {p95:.1e} — floating-point noise, nothing more. "
             "{off:,} visits differ by more than 0.1. The channel is internally "
             "consistent, so a BMI here "
             "disagreeing with your own calculation means you used a different "
             "height or weight, not that the field is wrong."),
        Table("t-bmi-cat", "Recorded BMI categories",
              [C("category", "category"), C("visits", "visits", ",", align="right"),
               C("share", "share of categorised visits", ".1f", "%", align="right"),
               C("patients", "distinct patients", ",", align="right")], cats),
        Figure("fig-bmi-cat", "Distribution of recorded BMI categories", "bar",
               {"categories": [c["category"] for c in cats],
                "series": [{"name": "visits", "values": [c["visits"] for c in cats]}],
                "height": 240, "title": "BMI categories"},
               alt="Category counts across underweight, normal, overweight and obese."),
        Para("The category is present only where a BMI percentile is, which 1.3 and "
             "3.4 show means age 2 or later. Of {total:,} categorised visits, "
             "{over_share:.1f}% are overweight and {obese_share:.1f}% obese."),
        Para("**Implications for analysis.** This is a distribution over recorded "
             "visits, not a prevalence: children with more visits contribute more "
             "rows, BMI is missing selectively by age and encounter type, and 1.4 "
             "shows the cohort is not a population sample. Aggregate to the patient "
             "before quoting any proportion, state the age window, and prefer the "
             "continuous percentile to the category where the analysis allows it, "
             "since the cut points discard most of the information.",
             role="implication"),
    ]
    return [f]

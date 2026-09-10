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
                "best_z": max(r["height_z"] for r in rows),
                "worst_wz": min(r["weight_z"] for r in rows),
                "best_wz": max(r["weight_z"] for r in rows)},
    )
    f.blocks = [
        Para("A reference table for anyone who needs to know what ordinary looks "
             "like in this extract before deciding what is unusual. Mean height "
             "z-scores run from {worst_z:.2f} to {best_z:.2f} across the age and sex "
             "cells and mean weight z-scores from {worst_wz:.2f} to {best_wz:.2f}, "
             "so the cohort sits close to the reference population on average — a "
             "little heavier for its age than it is tall, and further from the "
             "reference on weight than on height — even though it is not a sample of "
             "one."),
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
    # One population for every row of the table. The variance components used to
    # be measured over rows while the autocorrelation was measured over
    # deduplicated patient-days, so the four numbers described two panels; the
    # difference was immaterial (ICC 0.8214 against 0.8220) but the caption said
    # otherwise. Days, as 4.1, 4.4 and 4.5 also count them.
    ctx.con.execute("""
        CREATE OR REPLACE TEMP VIEW _hz AS
        SELECT patient_id, age_in_days, min(height_z_score) AS z
        FROM visits_augmented
        WHERE height_z_score IS NOT NULL AND age_in_years >= 2
        GROUP BY 1, 2 HAVING count(DISTINCT height_z_score) = 1""")
    n_pat, n_val, between, within, within_pooled = ctx.one("""
        WITH per AS (
            SELECT patient_id, avg(z) AS m, stddev_samp(z) AS s, count(*) AS n
            FROM _hz GROUP BY 1 HAVING count(*) >= 2)
        SELECT count(*), sum(n), stddev_samp(m), sqrt(avg(s * s)),
               sqrt(sum(s * s * (n - 1)) / sum(n - 1))
        FROM per""")
    pairs, rho = ctx.one("""
        WITH l AS (SELECT z, lag(z) OVER w AS pz FROM _hz
                   WINDOW w AS (PARTITION BY patient_id ORDER BY age_in_days))
        SELECT count(*), corr(z, pz) FROM l WHERE pz IS NOT NULL""")
    icc = between ** 2 / (between ** 2 + within ** 2)
    icc_pooled = between ** 2 / (between ** 2 + within_pooled ** 2)

    f = Finding(
        id="anthro.dependence", part="4.10",
        title="Within-child dependence in the height channel",
        values={"n_pat": n_pat, "n_val": n_val,
                "between": between, "within": within,
                "within_pooled": within_pooled,
                "icc": icc, "icc_pooled": icc_pooled,
                "pairs": pairs, "rho": rho,
                "eff": 1.0 / icc, "eff_pooled": 1.0 / icc_pooled},
    )
    f.blocks = [
        Para("Repeated measurements of one child are not independent observations, "
             "and the size of that dependence decides how much information a visit "
             "count actually carries. Measured on the height z-score at age 2 or "
             "later — the boundary 5.8 justifies from the reference standard, and "
             "the one 4.5 and 4.9 also use — across {n_pat:,} patients carrying "
             "{n_val:,} values between them, one per patient-day, with at least two "
             "each."),
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
                "meaning": f"correlation of successive values, {pairs:,} pairs"}],
              note="Every row is measured on the same {n_val:,} values. The "
                   "within-child SD is the root mean square of the per-patient SDs, "
                   "which weights a child with two values like a child with forty; "
                   "pooling by degrees of freedom instead gives {within_pooled:.4f} "
                   "and an intraclass correlation of {icc_pooled:.4f}."),
        Para("A child's height z-score is strongly self-similar: successive values "
             "correlate at {rho:.3f}, and {icc:.1%} of the total variance is "
             "between children rather than within them. The design-effect "
             "consequence is blunt: where the dependence is a persistent difference "
             "between children, a child contributes about {eff:.1f} independent "
             "observations in the limit of many measurements, not one per visit, "
             "however many visits are recorded. The two weightings above bracket "
             "that at {eff_pooled:.2f} to {eff:.2f}, so the figure is not sensitive "
             "to the choice."),
        Para("**Which dependence, though.** {eff:.1f} is the limit for a persistent "
             "between-child level; it is not what the lag-1 correlation alone would "
             "imply. A purely serial process with no between-child component keeps "
             "accumulating information as a series lengthens, however high its "
             "lag-1 correlation, so the two rows of this table are not two "
             "measurements of the same thing and the limit follows from the "
             "variance split rather than from {rho:.3f}.", role="method"),
        Para("**Implications for analysis.** Resample and model at the patient "
             "level, not the visit level: a visit-level standard error on any "
             "quantity aggregated across this panel will be far too small. And "
             "treat these as sample statistics rather than the parameters of a "
             "process that would generate them — a patient's mean carries residual "
             "variation as well as the child's own level, so the between-child SD of "
             "patient means overstates the underlying channel SD, while the sample "
             "SD within a positively autocorrelated series understates its marginal "
             "SD. Both biases raise the intraclass correlation, so they lower "
             "{eff:.1f}: read it as a floor on what a child contributes rather than "
             "an estimate of it. Calibrate a generative model against these by "
             "simulation rather than by setting its parameters equal to them.",
             role="method"),
    ]
    return [f]


@probe("anthro.bmi", "4.11")
def bmi(ctx: Context) -> list[Finding]:
    # The maximum is the quantity; the threshold count is kept as a guard, since a
    # nonzero one would mean the sentence reporting the maximum is wrong.
    n, med, worst, off = ctx.one("""
        WITH q AS (
            SELECT abs(bmi - weight_kg / pow(height_cm / 100.0, 2)) AS d
            FROM visits_augmented
            WHERE bmi IS NOT NULL AND weight_kg IS NOT NULL
              AND height_cm IS NOT NULL AND height_cm > 0)
        SELECT count(*), quantile_cont(d, 0.5), max(d),
               count(*) FILTER (WHERE d > 0.1) FROM q""")
    if off:
        raise ValueError(f"{off:,} visits recompute a BMI more than 0.1 from the "
                         f"distributed one; the channel is not self-consistent")

    total, pat_any, no_cat = ctx.one("""
        SELECT count(*) FILTER (WHERE bmi_category IS NOT NULL),
               count(DISTINCT patient_id) FILTER (WHERE bmi_category IS NOT NULL),
               count(*) FILTER (WHERE bmi IS NOT NULL AND bmi_category IS NULL)
        FROM visits_augmented""")

    # The category is a coarsening of the percentile, so it is checkable the same
    # way `bmi` itself is. The boundaries are read off the data rather than
    # assumed, and then the rule is applied back to every row.
    cats = []
    for name in CATEGORIES:
        v, p, lo, hi = ctx.one(
            "SELECT count(*), count(DISTINCT patient_id), min(bmi_percentile), "
            f"max(bmi_percentile) FROM visits_augmented WHERE bmi_category = '{name}'")
        cats.append({"category": name, "visits": v, "patients": p,
                     "share": 100.0 * v / total,
                     "band": f"{lo:.2f} to {hi:.2f}"})
    edges = [c["category"] for c in cats]
    rule = (f"CASE WHEN bmi_percentile < 5 THEN '{edges[0]}' "
            f"WHEN bmi_percentile < 85 THEN '{edges[1]}' "
            f"WHEN bmi_percentile < 95 THEN '{edges[2]}' ELSE '{edges[3]}' END")
    cat_bad = ctx.scalar(
        f"SELECT count(*) FROM visits_augmented WHERE bmi_category IS NOT NULL "
        f"AND bmi_category <> {rule}")
    if cat_bad:
        raise ValueError(
            f"the percentile cut points reproduce the category on all but "
            f"{cat_bad:,} rows; the prose claims they reproduce it exactly")

    f = Finding(
        id="anthro.bmi", part="4.11",
        title="BMI: recomputation and recorded categories",
        values={"n": n, "med": med, "worst": worst, "total": total,
                "pat_any": pat_any, "no_cat": no_cat,
                "pat_sum": sum(c["patients"] for c in cats),
                "obese_share": next(c["share"] for c in cats if c["category"] == "obese"),
                "over_share": next(c["share"] for c in cats
                                   if c["category"] == "overweight")},
    )
    f.blocks = [
        Para("BMI is the one derived channel that can be checked against its own "
             "inputs, and both halves of it check out. Across {n:,} visits carrying "
             "a BMI together with both a weight and a height, recomputing weight in "
             "kilograms over height in metres squared differs from the distributed "
             "value by a median of {med:.1e} and never by more than {worst:.1e} — "
             "floating-point noise, nothing more. The channel is internally "
             "consistent, so a BMI here disagreeing with your own calculation means "
             "you used a different height or weight, not that the field is wrong."),
        Para("The recorded category is the other half, and it is a coarsening of "
             "`bmi_percentile` rather than an independent judgement. Its boundaries "
             "are not documented in the extract, so they are read off the data "
             "below and then applied back to it: cutting the percentile at 5, 85 "
             "and 95 reproduces the distributed category on every one of the "
             "{total:,} categorised rows. The cut points are the conventional "
             "pediatric ones, and they are now checked rather than assumed."),
        Table("t-bmi-cat", "Recorded BMI categories",
              [C("category", "category"), C("band", "bmi_percentile"),
               C("visits", "visits", ",", align="right"),
               C("share", "share of categorised visits", ".1f", "%", align="right"),
               C("patients", "patients ever in it", ",", align="right")], cats,
              note="The last column does not partition the cohort: a child's "
                   "category moves across childhood, so a patient is counted in "
                   "every category they ever record. The four values sum to "
                   "{pat_sum:,} over the {pat_any:,} patients who carry any "
                   "category at all."),
        Figure("fig-bmi-cat", "Distribution of recorded BMI categories", "bar",
               {"categories": [c["category"] for c in cats],
                "series": [{"name": "visits", "values": [c["visits"] for c in cats]}],
                "height": 240, "title": "Recorded BMI category"},
               alt="Most categorised visits are normal; overweight and obese are "
                   "each about an eighth."),
        Para("The category is present only where a BMI percentile is, which 1.3 and "
             "3.4 show means age 2 or later — {no_cat:,} visits carry a BMI with "
             "neither, which is why this table's total is {total:,} against the "
             "{n:,} above."),
        Para("**Implications for analysis.** This is a distribution over recorded "
             "visits, not a prevalence: children with more visits contribute more "
             "rows, BMI is missing selectively by age and encounter type, and 1.4 "
             "shows the cohort is not a population sample. Aggregate to the patient "
             "before quoting any proportion, and note that the patient column here "
             "cannot be aggregated that way — it counts children ever in a "
             "category, so a proportion needs a category at a stated age or over a "
             "stated window, which is a choice this report does not make for you. "
             "State the age window, and prefer the continuous percentile to the "
             "category where the analysis allows it: the cut points above are the "
             "whole of what the category knows, so it discards everything between "
             "them.", role="implication"),
    ]
    return [f]

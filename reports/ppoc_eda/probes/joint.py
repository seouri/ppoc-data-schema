"""Part 5.8 — joint distributions across resources.

The extract was assembled to support identifying abnormal growth patterns early
(1.4). Whether that is learnable from it is not a property of any one resource:
it depends on how the label, the measurement history, and the care-process
record line up against each other. These are the cross-resource joints that
decide it, and each one constrains a model built on this data.
"""

from __future__ import annotations

from ..context import Context
from ..findings import Artifact, Figure, Finding, Para, Table, probe
from ..findings import Column as C

BEFORE_BANDS = [(0, 0, "0"), (1, 1, "1"), (2, 2, "2"), (3, 4, "3-4"),
                (5, 9, "5-9"), (10, 1 << 30, "10 or more")]
AGE_BANDS = [(0, 2, "0-2"), (2, 5, "2-5"), (5, 10, "5-10"),
             (10, 15, "10-15"), (15, 19, "15-18")]
CO_FLAGS = [("ever_stunting_flag", "height below the stunting threshold"),
            ("ever_wasting_flag", "weight-for-length or -stature below wasting"),
            ("ever_underweight_flag", "BMI below the underweight threshold"),
            ("ever_obesity_flag", "BMI at or above the obesity threshold"),
            ("chronic_dx_flag", "any chronic diagnosis"),
            ("healthy_flag", "carries none of the tracked conditions")]


@probe("joint.label", "5.8")
def label(ctx: Context) -> list[Finding]:
    ctx.con.execute("""
        CREATE TEMP TABLE _prehist AS
        WITH flagged AS (
            SELECT patient_id, dx_age_years FROM patients_augmented
            WHERE growth_dx_flag = 1 AND dx_age_years IS NOT NULL)
        SELECT f.patient_id, f.dx_age_years,
               count(v.height_cm) AS n_before
        FROM flagged f
        LEFT JOIN visits_augmented v
          ON v.patient_id = f.patient_id
         AND v.height_cm IS NOT NULL
         AND v.age_in_years < f.dx_age_years
        GROUP BY 1, 2
    """)
    total = ctx.scalar("SELECT count(*) FROM _prehist")
    before_rows, cats, vals = [], [], []
    for lo, hi, lab in BEFORE_BANDS:
        n = ctx.scalar(f"SELECT count(*) FROM _prehist WHERE n_before BETWEEN {lo} AND {hi}")
        before_rows.append({"band": lab, "patients": n, "share": 100.0 * n / total})
        cats.append(lab)
        vals.append(round(100.0 * n / total, 2))
    zero = before_rows[0]["patients"]
    zero_or_one = zero + before_rows[1]["patients"]
    # A trajectory needs at least two points to have a direction.
    with_traj = total - zero_or_one

    dx_infant = ctx.scalar(
        "SELECT 100.0 * sum(CASE WHEN dx_age_years < 1 THEN 1 ELSE 0 END) "
        "/ count(*) FROM _prehist")
    dx_med = ctx.scalar("SELECT quantile_cont(dx_age_years, 0.5) FROM _prehist")

    util = ctx.q("""
        SELECT growth_dx_flag, count(*),
               quantile_cont(visits_count, 0.5), avg(visits_count),
               quantile_cont(visits_count_pre_dx, 0.5), avg(visits_count_pre_dx)
        FROM patients_augmented GROUP BY 1 ORDER BY 1""")
    util_rows = [{"group": "no growth diagnosis" if f == 0 else "growth diagnosis",
                  "patients": n, "med_life": ml, "mean_life": al,
                  "med_pre": mp, "mean_pre": ap}
                 for f, n, ml, al, mp, ap in util]

    f = Finding(
        id="joint.label", part="5.8",
        title="Label, trajectory, and utilization do not line up",
        values={
            "total": total, "zero": zero, "zero_share": 100.0 * zero / total,
            "zero_or_one": zero_or_one,
            "zero_or_one_share": 100.0 * zero_or_one / total,
            "with_traj": with_traj,
            "with_traj_share": 100.0 * with_traj / total,
            "dx_infant": dx_infant, "dx_med": dx_med,
            "life_flag": util_rows[1]["mean_life"], "life_no": util_rows[0]["mean_life"],
            "pre_flag": util_rows[1]["mean_pre"], "pre_no": util_rows[0]["mean_pre"],
            "pre_med_flag": util_rows[1]["med_pre"], "pre_med_no": util_rows[0]["med_pre"],
        },
        artifact=Artifact(
            name="Diagnosis label precedes the growth trajectory it would be "
                 "predicted from",
            kind="selection",
            scale="{zero_share:.0f}% of labelled patients have no height "
                  "recorded before their diagnosis",
            recoverable="No — use a different label or a different index date",
        ),
    )
    f.blocks = [
        Para("A model that identifies abnormal growth early needs three things to "
             "line up: a label, a measurement history that precedes it, and a "
             "care-process record that does not simply give the answer away. In "
             "this extract none of the three lines up with the others, and the "
             "mismatches are large enough to decide a study design."),
        Para("**The label mostly arrives before the trajectory does.** Of "
             "{total:,} patients carrying a growth diagnosis with a recorded age, "
             "{dx_infant:.1f}% receive it before their first birthday, at a median "
             "age of {dx_med:.3f} years. 5.7 shows why: the tracked panel is "
             "dominated by perinatal codes recorded within days of birth."),
        Figure("fig-pre-heights",
               "Height observations recorded before the growth diagnosis",
               "bar",
               {"categories": cats,
                "series": [{"name": "share of labelled patients", "values": vals}],
                "suffix": "%", "height": 260,
                "title": "Prior heights at the time of diagnosis"},
               alt="Half of labelled patients have no height before their diagnosis."),
        Table("t-pre-heights", "Heights available before the diagnosis",
              [C("band", "heights recorded first"),
               C("patients", "patients", ",", align="right"),
               C("share", "share", ".1f", "%", align="right")], before_rows),
        Para("**{zero:,} of those patients ({zero_share:.1f}%) have no height "
             "recorded at all before their diagnosis, and {zero_or_one_share:.1f}% "
             "have at most one.** There is no trajectory to detect anything from: "
             "for most of the labelled population the code is not an outcome a "
             "growth curve could have anticipated, it is a fact recorded at or "
             "near birth. Any evaluation that scores prediction of this label "
             "across the whole labelled set is measuring something else."),
        Table("t-util", "Visit counts, lifetime and before the diagnosis",
              [C("group", "group"), C("patients", "patients", ",", align="right"),
               C("med_life", "median lifetime visits", ",.0f", align="right"),
               C("mean_life", "mean lifetime", ",.2f", align="right"),
               C("med_pre", "median before diagnosis", ",.0f", align="right"),
               C("mean_pre", "mean before diagnosis", ",.2f", align="right")],
              util_rows,
              note="Patients with no growth diagnosis have no index date, so their "
                   "before-diagnosis count is their lifetime count. That is exactly "
                   "the asymmetry the note below describes."),
        Para("**Utilization separates the groups, but only because the index date "
             "does.** Over a lifetime the two groups are barely distinguishable — "
             "{life_flag:.2f} visits on average against {life_no:.2f}. Counted up "
             "to the diagnosis they are worlds apart, {pre_flag:.2f} against "
             "{pre_no:.2f}, because an undiagnosed patient has no index date and "
             "so contributes their whole record. A feature built from "
             "\"observations before the index\" therefore encodes which group a "
             "patient is in rather than anything about their growth, and it does "
             "so in the counter-intuitive direction: the labelled group has "
             "*fewer* prior visits, not more."),
        Para("**Implications for analysis.** Fixing this needs a common index date "
             "for both groups, chosen without reference to the label — a fixed age, "
             "a matched visit number, or a sampled pseudo-index for unlabelled "
             "patients. Only {with_traj:,} labelled patients "
             "({with_traj_share:.1f}%) have two or more prior heights, which is "
             "the most a trajectory-based model could train on; restricting to "
             "them changes the population being studied and should be reported "
             "rather than done silently. And a model evaluated on "
             "this label at all is being scored against recorded coding practice, "
             "not against an adjudicated growth assessment; 5.6 makes the same "
             "point about the flag itself.", role="implication"),
    ]
    return [f]


@probe("joint.features", "5.9")
def features(ctx: Context) -> list[Finding]:
    rows = []
    for lo, hi, lab in AGE_BANDS:
        n, h, w, both = ctx.one(f"""
            SELECT count(*), 100.0 * count(height_cm) / count(*),
                   100.0 * count(weight_kg) / count(*),
                   100.0 * sum(CASE WHEN height_cm IS NOT NULL
                                     AND weight_kg IS NOT NULL THEN 1 ELSE 0 END)
                   / count(*)
            FROM visits_augmented
            WHERE age_in_years >= {lo} AND age_in_years < {hi}""")
        rows.append({"band": lab, "visits": n, "height": h, "weight": w,
                     "both": both, "gap": w - both})

    co_rows = []
    for col, meaning in CO_FLAGS:
        yes = ctx.scalar("SELECT 100.0 * sum(CASE WHEN " + col +
                         " = 1 THEN 1 ELSE 0 END) / count(*) "
                         "FROM patients_augmented WHERE growth_dx_flag = 1")
        no = ctx.scalar("SELECT 100.0 * sum(CASE WHEN " + col +
                        " = 1 THEN 1 ELSE 0 END) / count(*) "
                        "FROM patients_augmented WHERE growth_dx_flag = 0")
        co_rows.append({"flag": col, "meaning": meaning, "flagged": yes,
                        "unflagged": no,
                        "ratio": (yes / no) if no else None})

    res_rows = []
    for f_val, label_text in ((1, "growth diagnosis"), (0, "no growth diagnosis")):
        n, r, m, lb = ctx.one(f"""
            SELECT count(*),
              100.0 * sum(CASE WHEN EXISTS(SELECT 1 FROM referrals x
                    WHERE x.patient_id = p.patient_id) THEN 1 ELSE 0 END) / count(*),
              100.0 * sum(CASE WHEN EXISTS(SELECT 1 FROM medications x
                    WHERE x.patient_id = p.patient_id) THEN 1 ELSE 0 END) / count(*),
              100.0 * sum(CASE WHEN EXISTS(SELECT 1 FROM labs x
                    WHERE x.patient_id = p.patient_id) THEN 1 ELSE 0 END) / count(*)
            FROM patients_augmented p WHERE growth_dx_flag = {f_val}""")
        res_rows.append({"group": label_text, "patients": n, "referral": r,
                         "medication": m, "lab": lb})

    healthy = next(r for r in co_rows if r["flag"] == "healthy_flag")
    stunting = next(r for r in co_rows if r["flag"] == "ever_stunting_flag")
    worst = min(rows, key=lambda r: r["both"])

    f = Finding(
        id="joint.features", part="5.9",
        title="What a feature vector actually contains",
        values={"worst_band": worst["band"], "worst_both": worst["both"],
                "worst_gap": worst["gap"],
                "healthy_flagged": healthy["flagged"],
                "stunt_flagged": stunting["flagged"],
                "stunt_unflagged": stunting["unflagged"],
                "stunt_ratio": stunting["ratio"],
                "ref_flag": res_rows[0]["referral"],
                "ref_no": res_rows[1]["referral"]},
        artifact=Artifact(
            name="A derived flag that is disjoint from the diagnosis flag by "
                 "construction",
            kind="derivation",
            scale="healthy_flag is set for {healthy_flagged:.1f}% of "
                  "growth-diagnosed patients",
            recoverable="Yes — define the negative class explicitly instead",
        ),
    )
    f.blocks = [
        Para("Height and weight are the two measurements a growth model needs "
             "together, and 3.4 gives each one's availability separately. Jointly "
             "is what matters, because a visit missing either contributes no "
             "complete observation."),
        Table("t-joint-hw", "Visits carrying height, weight, and both",
              [C("band", "age band (years)"),
               C("visits", "visits", ",", align="right"),
               C("height", "height", ".1f", "%", align="right"),
               C("weight", "weight", ".1f", "%", align="right"),
               C("both", "both", ".1f", "%", align="right"),
               C("gap", "weight without height", ".1f", "%", align="right")], rows),
        Para("The joint rate tracks the height rate almost exactly: where a height "
             "exists a weight nearly always does too, so height alone is the "
             "binding constraint and the last column is what a height-and-weight "
             "model discards. It is worst at {worst_band} years, where only "
             "{worst_both:.1f}% of visits carry both and {worst_gap:.1f}% carry a "
             "weight with no height to pair it with."),
        Table("t-co-flags", "Derived flags among labelled and unlabelled patients",
              [C("flag", "flag"), C("meaning", "set when the patient has"),
               C("flagged", "growth diagnosis", ".1f", "%", align="right"),
               C("unflagged", "no growth diagnosis", ".1f", "%", align="right"),
               C("ratio", "ratio", ".2f", "x", align="right")], co_rows),
        Para("Two rows here matter for anyone assembling a training set. "
             "`healthy_flag` is set for {healthy_flagged:.1f}% of "
             "growth-diagnosed patients — it is **disjoint from the diagnosis flag "
             "by construction**, so using it as a negative class defines the "
             "outcome into the input and any model separating the two is learning "
             "the definition. `ever_stunting_flag`, by contrast, is a genuine "
             "correlate: {stunt_flagged:.1f}% against {stunt_unflagged:.1f}%, a "
             "{stunt_ratio:.1f}-fold enrichment derived from the measurements "
             "themselves rather than from the code."),
        Table("t-footprint", "Cross-resource footprint by label",
              [C("group", "group"), C("patients", "patients", ",", align="right"),
               C("referral", "has a referral", ".1f", "%", align="right"),
               C("medication", "has a medication", ".1f", "%", align="right"),
               C("lab", "has a lab", ".1f", "%", align="right")], res_rows),
        Para("**Implications for analysis.** Count complete observations, not "
             "visits: the usable input rate is the joint column, not the weight "
             "column, and it varies by more than ten points across childhood so a "
             "cohort defined by complete rows is age-selected. Never use "
             "`healthy_flag` as the negative class for a growth-diagnosis model. "
             "The cross-resource footprint is a weak discriminator — a referral is "
             "present for {ref_flag:.1f}% of labelled against {ref_no:.1f}% of "
             "unlabelled patients — which is reassuring for leakage but means "
             "these resources add little on their own.", role="implication"),
    ]
    return [f]

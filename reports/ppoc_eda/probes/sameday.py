"""Part 3.8 — when one patient-day carries two measurements that disagree."""

from __future__ import annotations

from ..context import Context
from ..findings import Artifact, Finding, Para, Table, probe
from ..findings import Column as C

CHANNELS = [("height_cm", "height", "cm"), ("weight_kg", "weight", "kg"),
            ("head_circ_cm", "head circumference", "cm")]


@probe("integrity.sameday", "3.8")
def sameday(ctx: Context) -> list[Finding]:
    rows = []
    for col, label, unit in CHANNELS:
        multi, disagree = ctx.one(f"""
            WITH g AS (SELECT patient_id, age_in_days, count({col}) AS n,
                              count(DISTINCT {col}) AS d
                       FROM visits_augmented WHERE {col} IS NOT NULL
                       GROUP BY 1, 2)
            SELECT sum(CASE WHEN n > 1 THEN 1 ELSE 0 END),
                   sum(CASE WHEN d > 1 THEN 1 ELSE 0 END) FROM g""")
        spread = ctx.one(f"""
            WITH g AS (SELECT patient_id, age_in_days,
                              max({col}) - min({col}) AS s
                       FROM visits_augmented WHERE {col} IS NOT NULL
                       GROUP BY 1, 2 HAVING count(DISTINCT {col}) > 1)
            SELECT quantile_cont(s, 0.5), quantile_cont(s, 0.95), max(s) FROM g""")
        rows.append({
            "channel": label, "unit": unit,
            "multi": ctx.suppress(multi), "disagree": ctx.suppress(disagree),
            "share": 100.0 * disagree / multi if multi else 0.0,
            "median": spread[0], "p95": spread[1], "max": spread[2],
        })

    h = next(r for r in rows if r["channel"] == "height")
    f = Finding(
        id="integrity.sameday", part="3.8",
        title="Same-day measurements that disagree",
        values={"h_multi": h["multi"], "h_disagree": h["disagree"],
                "h_share": h["share"], "h_median": h["median"], "h_max": h["max"]},
        artifact=Artifact(
            name="Two measurements of one channel on one patient-day that disagree",
            kind="capture",
            scale="{h_disagree:,} patient-days for height, median spread "
                  "{h_median:.2f} cm",
            recoverable="Partly — define an explicit tie rule before ordering by age",
        ),
    )
    f.blocks = [
        Para("Section 3.1 shows that a patient-day can carry more than one visit. "
             "Where those visits each carry the same measurement, they often do not "
             "agree, and the size of the disagreement is a direct estimate of how "
             "far two records of the same child on the same day can sit apart."),
        Table("t-sameday", "Patient-days carrying more than one value of a channel",
              [C("channel", "channel"),
               C("multi", "patient-days with 2 or more", ",", align="right"),
               C("disagree", "of which they disagree", ",", align="right"),
               C("share", "share disagreeing", ".1f", "%", align="right"),
               C("median", "median spread", ".3f", align="right"),
               C("p95", "95th percentile", ".2f", align="right"),
               C("max", "maximum", ".2f", align="right")], rows,
              note="Spread columns are in each channel's own unit and describe only "
                   "the disagreeing days, not the panel."),
        Para("The height spread is the notable one. A median disagreement of "
             "{h_median:.2f} cm between two heights recorded for the same child on "
             "the same day is far larger in relative terms than the weight "
             "equivalent, and it is the size of difference expected when recumbent "
             "length and standing height are mixed, or when one value is carried "
             "from an earlier note. Section 4.5 finds the same effect across the "
             "length-to-height transition age, seen there across months rather than "
             "within a day."),
        Para("**Implications for analysis.** These days need a tie rule chosen "
             "before the analysis, not left to whatever order the query returns. "
             "Taking the minimum, the maximum, the mean, or the first row are all "
             "defensible and they give different answers; what is not defensible is "
             "not knowing which one you took. Deduplicate the patient-day before "
             "any window function, since 4.8 shows the derivation layer's own "
             "ambiguity on exactly these rows.", role="implication"),
    ]
    return [f]

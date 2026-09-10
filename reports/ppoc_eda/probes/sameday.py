"""Part 3.8 — when one patient-day carries two measurements that disagree."""

from __future__ import annotations

from ..context import Context
from ..findings import Artifact, Finding, Para, Table, probe
from ..findings import Column as C

CHANNELS = [("height_cm", "height", "cm"), ("weight_kg", "weight", "kg"),
            ("head_circ_cm", "head circumference", "cm")]

#: The length-to-height transition 4.5 locates, as day bounds. If mixing the two
#: protocols is what produces a same-day disagreement, the disagreements should
#: concentrate between them.
TRANSITION = (730, 1095)
#: 4.7's plausible band for head circumference. A day holding a value outside it
#: is an arithmetic artifact rather than two people measuring differently.
HC_HI = 65.0


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

    # The section attributes the height spread to mixed measurement protocols,
    # which predicts where the disagreements sit. Test it.
    bands = ctx.q(f"""
        WITH g AS (SELECT patient_id, age_in_days,
                          max(height_cm) - min(height_cm) AS s
                   FROM visits_augmented WHERE height_cm IS NOT NULL
                   GROUP BY 1, 2 HAVING count(DISTINCT height_cm) > 1),
        allday AS (SELECT patient_id, age_in_days FROM visits_augmented
                   WHERE height_cm IS NOT NULL GROUP BY 1, 2)
        SELECT b, count(*), quantile_cont(s, 0.5),
               (SELECT count(*) FROM allday a
                WHERE CASE WHEN a.age_in_days < {TRANSITION[0]} THEN 'before'
                           WHEN a.age_in_days < {TRANSITION[1]} THEN 'during'
                           ELSE 'after' END = b)
        FROM (SELECT s, CASE WHEN age_in_days < {TRANSITION[0]} THEN 'before'
                             WHEN age_in_days < {TRANSITION[1]} THEN 'during'
                             ELSE 'after' END AS b FROM g)
        GROUP BY b""")
    band = {b: {"days": n, "median": m, "of": tot} for b, n, m, tot in bands}

    # The head-circumference tail is 4.7's channel, not a recording disagreement.
    hc_days, hc_out, hc_in_median = ctx.one(f"""
        WITH g AS (SELECT patient_id, age_in_days,
                          max(head_circ_cm) AS hi,
                          max(head_circ_cm) - min(head_circ_cm) AS s
                   FROM visits_augmented WHERE head_circ_cm IS NOT NULL
                   GROUP BY 1, 2 HAVING count(DISTINCT head_circ_cm) > 1)
        SELECT count(*), count(*) FILTER (WHERE hi > {HC_HI}),
               quantile_cont(s, 0.5) FILTER (WHERE hi <= {HC_HI}) FROM g""")

    h = next(r for r in rows if r["channel"] == "height")
    f = Finding(
        id="integrity.sameday", part="3.8",
        title="Same-day measurements that disagree",
        values={"h_multi": h["multi"], "h_disagree": h["disagree"],
                "h_share": h["share"], "h_median": h["median"], "h_max": h["max"],
                "before_n": band["before"]["days"],
                "before_rate": 100.0 * band["before"]["days"] / band["before"]["of"],
                "during_n": band["during"]["days"],
                "during_rate": 100.0 * band["during"]["days"] / band["during"]["of"],
                "after_rate": 100.0 * band["after"]["days"] / band["after"]["of"],
                "before_med": band["before"]["median"],
                "after_med": band["after"]["median"],
                "hc_days": hc_days, "hc_out": hc_out,
                "hc_in_median": hc_in_median, "hc_hi": HC_HI},
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
             "equivalent."),
        Para("**It is not the length-to-height transition, which is the first "
             "explanation to reach for.** 4.5 locates that transition between two "
             "and three years, and mixing the two protocols on one day would "
             "concentrate the disagreements there. They are not concentrated "
             "there: {during_rate:.3f}% of patient-days in the transition window "
             "carry two heights that disagree, against {before_rate:.3f}% before it "
             "and {after_rate:.3f}% after. The largest group is the one the "
             "explanation cannot cover at all — {before_n:,} of the {h_disagree:,} "
             "disagreeing days fall under age two, where both values would have "
             "been recumbent lengths. What does change with age is the size rather "
             "than the frequency: a median of {before_med:.2f} cm under two against "
             "{after_med:.2f} cm from three, which is what a fixed relative error "
             "on a growing child looks like. A value carried from an earlier note "
             "remains a candidate; this report cannot test it."),
        Para("The head-circumference row needs 4.7 beside it. Its maximum is not "
             "two people measuring differently: {hc_out:,} of the {hc_days:,} "
             "disagreeing days hold a value above {hc_hi:.0f} cm, which 4.7 shows "
             "is an inch-to-centimetre conversion applied twice. Among the days "
             "whose values are all plausible the median spread is "
             "{hc_in_median:.2f} cm, and that is the number to read as a recording "
             "disagreement.", role="method"),
        Para("**Implications for analysis.** These days need a tie rule chosen "
             "before the analysis, not left to whatever order the query returns. "
             "Taking the minimum, the maximum, the mean, or the first row are all "
             "defensible and they give different answers; what is not defensible is "
             "not knowing which one you took. Deduplicate the patient-day before "
             "any window function, since 4.8 shows the derivation layer's own "
             "ambiguity on exactly these rows. Note that 4.5 takes the strongest "
             "rule available and drops these days from its panel entirely, which is "
             "one defensible answer and not the only one.", role="implication"),
    ]
    return [f]

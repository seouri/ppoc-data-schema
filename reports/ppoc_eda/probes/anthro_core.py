"""Part 4.1-4.3 and 4.6 — supply, recording grid, distributions, derived channels."""

from __future__ import annotations

import math

from ..context import Context
from ..findings import Artifact, Column, Figure, Finding, Para, Table, probe

CHANNELS = [
    ("height_cm", "height", "cm", 30, 200),
    ("weight_kg", "weight", "kg", 0, 160),
    ("bmi", "BMI", "kg/m^2", 5, 60),
    ("head_circ_cm", "head circumference", "cm", 0, 80),
]
Z_CHANNELS = [("height_z_score", "height z"), ("weight_z_score", "weight z"),
              ("bmi_z_score", "BMI z"), ("head_circ_z_score", "head circ z"),
              ("weight_for_length_z_score", "weight-for-length z"),
              ("weight_for_stature_z_score", "weight-for-stature z")]
PCT_CHANNELS = [("height_percentile", "height"), ("weight_percentile", "weight"),
                ("bmi_percentile", "BMI"),
                ("head_circ_percentile", "head circumference"),
                ("weight_for_length_percentile", "weight-for-length"),
                ("weight_for_stature_percentile", "weight-for-stature")]

#: The conversion factors the derived columns are checked against, the tolerance
#: the check uses, and the grid steps each channel is recorded on. The metric
#: grid steps are reported because the implication tells a reader to set
#: detection thresholds at or above the grid, and the weight channel is the one
#: that coarsens with age.
IN_TO_CM, OZ_TO_KG, CONV_TOL = 2.54, 0.0283495, 0.01
GRID_IN, GRID_OZ, GRID_LB = 0.25, 1.0, 16.0

#: The support the z channels are clamped to where they are clamped at all. The
#: table's own "beyond" column is what shows it: zero on the clamped channels.
Z_CLAMP = 5.0
AGE_BANDS = [(0, 2, "0-2"), (2, 5, "2-5"), (5, 10, "5-10"),
             (10, 15, "10-15"), (15, 19, "15-18")]


@probe("anthro.supply", "4.1")
def supply(ctx: Context) -> list[Finding]:
    total = ctx.scalar("SELECT count(*) FROM patients")
    # Distinct days, not rows. A patient-day can carry more than one visit (3.1),
    # and a design needing k observations needs k occasions; counting rows would
    # credit a child measured once and recorded twice with two.
    counts = ctx.q(
        "WITH per AS (SELECT patient_id, count(DISTINCT age_in_days) AS n "
        "             FROM visits_augmented WHERE height_cm IS NOT NULL GROUP BY 1) "
        "SELECT n, count(*) FROM per GROUP BY 1 ORDER BY 1")
    lookup = dict(counts)
    tail, cum = 0, []
    for k in range(max(lookup, default=0), 0, -1):
        tail += lookup.get(k, 0)
        cum.append((k, tail))
    cum.reverse()
    at = {k: v for k, v in cum}
    rows = [{"k": k, "patients": at.get(k, 0), "share": 100.0 * at.get(k, 0) / total}
            for k in (1, 3, 5, 10, 15, 20, 25)]

    # What counting rows instead of occasions would have added, and what the
    # derived layer's bound takes out before any of this is counted.
    infl = ctx.scalar(
        "WITH per AS (SELECT patient_id, count(*) AS rows_n, "
        "                    count(DISTINCT age_in_days) AS day_n "
        "             FROM visits_augmented WHERE height_cm IS NOT NULL GROUP BY 1) "
        "SELECT count(*) FILTER (WHERE rows_n > day_n) FROM per")
    raw_pt, der_pt, raw_only, lost_some, removed = ctx.one("""
        WITH per AS (SELECT patient_id, count(height_in) AS raw_n,
                            count(height_cm) AS der_n
                     FROM visits_augmented GROUP BY 1)
        SELECT count(*) FILTER (WHERE raw_n > 0), count(*) FILTER (WHERE der_n > 0),
               count(*) FILTER (WHERE raw_n > 0 AND der_n = 0),
               count(*) FILTER (WHERE raw_n > der_n),
               sum(raw_n) - sum(der_n)
        FROM per""")

    f = Finding(
        id="anthro.supply", part="4.1",
        title="Trajectory supply: how many heights each child has",
        values={"total": total, "kmax": max(lookup, default=0),
                "with_1": at.get(1, 0), "share_1": 100.0 * at.get(1, 0) / total,
                "with_5": at.get(5, 0), "share_5": 100.0 * at.get(5, 0) / total,
                "with_10": at.get(10, 0), "share_10": 100.0 * at.get(10, 0) / total,
                "infl": infl, "raw_pt": raw_pt, "der_pt": der_pt,
                "raw_only": raw_only, "lost_some": lost_some, "removed": removed},
    )
    f.blocks = [
        Para("{with_1:,} of {total:,} patients ({share_1:.1f}%) carry at least one "
             "derived height, {with_5:,} ({share_5:.1f}%) carry five or more, and "
             "{with_10:,} ({share_10:.1f}%) carry ten or more."),
        Para("**What is being counted.** Days, not rows, and the derived channel, "
             "not the recorded one. A patient-day can hold more than one visit "
             "(3.1), so heights are counted once per day — {infl:,} patients carry "
             "a day with more than one, and counting rows would credit them with "
             "observations a design could not use. And the count is over "
             "`height_cm`, which the augmentation bounds: {removed:,} recorded "
             "heights have no derived value, {lost_some:,} patients lose at least "
             "one, and {raw_only:,} carry a recorded height and no derived one at "
             "all, so they appear here at zero. 4.4 shows what the bound removes "
             "and why most of it should be removed. A curve built from `height_in` "
             "would sit slightly above this one.", role="method"),
        Figure("fig-supply",
               "Patients retaining at least k height observations",
               "step",
               {"x": [str(k) for k, _ in cum[:25]],
                "series": [{"name": "patients", "values": [v for _, v in cum[:25]]}],
                "title": "Height observations per patient", "height": 280},
               alt="A declining curve from all patients down to those with 25 heights."),
        Table("t-supply", "Height observations per patient",
              [Column("k", "at least k heights", align="right"),
               Column("patients", "patients", ",", align="right"),
               Column("share", "share of cohort", ".1f", "%", align="right")], rows,
              note="One height per patient-day. The most any patient carries is "
                   "{kmax}."),
        Para("**Implications for analysis.** Read this against 1.4 before treating "
             "it as a fact about pediatric care. Cohort entry required growth "
             "measurements, so a dense height series here is partly the selection "
             "rule and partly the underlying practice, and the two cannot be "
             "separated within this extract. They are not the same count, though, "
             "and the gap is worth holding: entry required five measurements **of "
             "one type** — which weight alone can satisfy — **on distinct dates "
             "spanning over 1095 days**, with the last within 400 days. This curve "
             "requires none of the span, none of the recency, and it counts one "
             "type rather than any. That is why 94% carrying five heights is not "
             "the entry rule restated. What the curve does support is a feasibility "
             "estimate: how many children remain if your design needs k "
             "observations of height.", role="implication"),
    ]
    return [f]


@probe("anthro.grid", "4.2")
def grid(ctx: Context) -> list[Finding]:
    h_total, h_whole, h_half, h_quarter = ctx.one(
        "SELECT count(*), "
        " sum(CASE WHEN height_in = floor(height_in) THEN 1 ELSE 0 END), "
        " sum(CASE WHEN height_in * 2 = floor(height_in * 2) THEN 1 ELSE 0 END), "
        " sum(CASE WHEN height_in * 4 = floor(height_in * 4) THEN 1 ELSE 0 END) "
        "FROM visits_augmented WHERE height_in IS NOT NULL")
    w_total, w_oz, w_lb = ctx.one(
        "SELECT count(*), "
        " sum(CASE WHEN weight_oz = floor(weight_oz) THEN 1 ELSE 0 END), "
        " sum(CASE WHEN weight_oz % 16 = 0 THEN 1 ELSE 0 END) "
        "FROM visits_augmented WHERE weight_oz IS NOT NULL")

    bands, hq, wp = [], [], []
    for lo, hi, label in AGE_BANDS:
        w = f"age_in_years >= {lo} AND age_in_years < {hi}"
        bands.append(label)
        hq.append(round(ctx.scalar(
            f"SELECT 100.0 * sum(CASE WHEN height_in * 4 = floor(height_in * 4) "
            f"THEN 1 ELSE 0 END) / nullif(count(height_in), 0) "
            f"FROM visits_augmented WHERE {w}") or 0.0, 1))
        wp.append(round(ctx.scalar(
            f"SELECT 100.0 * sum(CASE WHEN weight_oz % 16 = 0 THEN 1 ELSE 0 END) "
            f"/ nullif(count(weight_oz), 0) FROM visits_augmented WHERE {w}") or 0.0, 1))

    # The claim that the metric columns are exact conversions is checked, not
    # asserted: a wrong unit survives an exact conversion unchanged, so knowing
    # the arithmetic is clean is what makes 4.4's unit findings interpretable.
    h_pairs, h_bad, h_worst = ctx.one(
        f"SELECT count(*), "
        f" sum(CASE WHEN abs(height_cm - height_in * {IN_TO_CM}) > {CONV_TOL} "
        f"          THEN 1 ELSE 0 END), "
        f" max(abs(height_cm - height_in * {IN_TO_CM})) FROM visits_augmented "
        "WHERE height_in IS NOT NULL AND height_cm IS NOT NULL")
    w_pairs, w_bad, w_worst = ctx.one(
        f"SELECT count(*), "
        f" sum(CASE WHEN abs(weight_kg - weight_oz * {OZ_TO_KG}) > {CONV_TOL} "
        f"          THEN 1 ELSE 0 END), "
        f" max(abs(weight_kg - weight_oz * {OZ_TO_KG})) FROM visits_augmented "
        "WHERE weight_oz IS NOT NULL AND weight_kg IS NOT NULL")
    # The maximum deviation is what the prose reports; the threshold count is kept
    # as a guard, because a nonzero one would mean the sentence above is wrong.
    if h_bad or w_bad:
        raise ValueError(
            f"conversion is not exact: {h_bad:,} height and {w_bad:,} weight pairs "
            f"differ by more than {CONV_TOL}")
    # The check can only cover rows that have a derived value. The ones it cannot
    # see are the ones the bound removed, which is where 4.4's unit errors live.
    h_unchecked = ctx.scalar(
        "SELECT count(*) FROM visits_augmented "
        "WHERE height_in IS NOT NULL AND height_cm IS NULL")

    f = Finding(
        id="anthro.grid", part="4.2",
        title="Recording units and the measurement grid",
        values={"h_total": h_total, "w_total": w_total,
                "h_pairs": h_pairs, "h_bad": h_bad,
                "w_pairs": w_pairs, "w_bad": w_bad,
                "h_whole": 100.0 * h_whole / h_total,
                "h_half": 100.0 * h_half / h_total,
                "h_quarter": 100.0 * h_quarter / h_total,
                "w_oz": 100.0 * w_oz / w_total, "w_lb": 100.0 * w_lb / w_total,
                "grid_cm": GRID_IN * IN_TO_CM,
                "grid_oz_kg": GRID_OZ * OZ_TO_KG, "grid_lb_kg": GRID_LB * OZ_TO_KG,
                "h_worst": h_worst, "w_worst": w_worst,
                "conv_in": IN_TO_CM, "conv_oz": OZ_TO_KG,
                "h_unchecked": h_unchecked, "h_recorded": h_total},
        artifact=Artifact(
            name="Terminal-digit heaping on the imperial recording grid",
            kind="capture",
            scale="{h_quarter:.1f}% of heights fall on a quarter inch",
            recoverable="No — it is the precision the measurement actually has",
        ),
    )
    f.blocks = [
        Para("Height and weight are captured in imperial units, and the metric "
             "columns are exact conversions of them — measured, not assumed. Across "
             "{h_pairs:,} visits carrying both a raw and a derived height, the "
             "largest disagreement with `height_in` times {conv_in} is "
             "{h_worst:.4f} cm; across {w_pairs:,} weight pairs the largest "
             "disagreement with `weight_oz` times {conv_oz} is {w_worst:.5f} kg. "
             "Both sit inside the two-decimal rounding of the stored columns, which "
             "is why they are that small: there is no residue beyond the rounding "
             "for either channel."),
        Para("The arithmetic being clean is what makes 4.4's unit findings "
             "interpretable: a value keyed in the wrong unit survives an exact "
             "conversion unchanged, so a wrong unit is a wrong *recording* and not "
             "a conversion defect. The check can only speak for rows that have a "
             "derived value, though. {h_unchecked:,} of the {h_recorded:,} recorded "
             "heights have none, because the augmentation bounded them away, and "
             "those are exactly the clusters 4.4 identifies — so the population the "
             "warning is about is the one this check cannot see."),
        Para("The recorded values are heaped on human-readable fractions, and the "
             "shares below nest rather than partition — every whole inch is also a "
             "half and a quarter inch, and every whole pound is also a whole ounce, "
             "so they are cumulative and do not sum. Of {h_total:,} heights, "
             "{h_quarter:.1f}% fall on a quarter inch, {h_half:.1f}% on a half inch "
             "and {h_whole:.1f}% on a whole inch. Of {w_total:,} weights, "
             "{w_oz:.1f}% fall on a whole ounce and {w_lb:.1f}% on a whole pound."),
        Figure("fig-grid", "Share of measurements falling on the coarse grid, by age",
               "grouped_bar",
               {"categories": bands,
                "series": [{"name": "height on a quarter inch", "values": hq},
                           {"name": "weight on a whole pound", "values": wp}],
                "suffix": "%", "title": "Recording granularity by age", "height": 300},
               alt="Height grid share is flat across age; whole-pound weight rises."),
        Para("The two channels age in opposite directions. Height stays on its "
             "quarter-inch grid throughout childhood, while weight moves from "
             "ounce-level precision in infancy to whole pounds in adolescence, so "
             "the effective resolution of the weight channel degrades as children "
             "get older."),
        Para("**Implications for analysis.** The grid, in the units the derived "
             "columns are written in: one quarter inch is {grid_cm:.3f} cm, one "
             "ounce is {grid_oz_kg:.4f} kg and one pound is {grid_lb_kg:.4f} kg. "
             "Those are the floors, and the weight floor is the one that moves — a "
             "channel recorded to the pound in adolescence resolves nothing finer "
             "than {grid_lb_kg:.2f} kg however many decimals it is stored with. Any "
             "change smaller than roughly half the interval is not distinguishable "
             "from the rounding itself, which sets a floor on the smallest "
             "trajectory deflection that can be detected at all. Set detection "
             "thresholds at or above the grid, and state the assumed precision "
             "wherever a measurement is written out — the two decimals on "
             "`height_cm` are an honest record of an exact conversion and not a "
             "claim about the measurement, which is {grid_cm:.3f} cm coarse.",
             role="implication"),
    ]
    return [f]


@probe("anthro.distributions", "4.3")
def distributions(ctx: Context) -> list[Finding]:
    rows, figures = [], []
    for col, label, unit, lo, hi in CHANNELS:
        n, mn, p1, p50, p99, mx = ctx.one(
            f"SELECT count({col}), min({col}), quantile_cont({col}, 0.01), "
            f"quantile_cont({col}, 0.5), quantile_cont({col}, 0.99), max({col}) "
            f"FROM visits_augmented WHERE {col} IS NOT NULL")
        outside = ctx.scalar(
            f"SELECT count(*) FROM visits_augmented "
            f"WHERE {col} IS NOT NULL AND ({col} < {lo} OR {col} > {hi})")
        rows.append({"channel": label, "unit": unit, "n": n, "min": mn, "p1": p1,
                     "median": p50, "p99": p99, "max": mx,
                     "range": f"{lo:g} to {hi:g}",
                     "outside": ctx.suppress(outside)})
        edges = [lo + (hi - lo) * i / 40 for i in range(41)]
        counts = [ctx.scalar(
            f"SELECT count(*) FROM visits_augmented WHERE {col} >= {edges[i]} "
            f"AND {col} < {edges[i + 1]}") for i in range(40)]
        figures.append(Figure(
            f"fig-dist-{col}", f"Distribution of {label} ({unit})", "hist",
            {"edges": edges, "counts": counts, "height": 220,
             "title": f"{label} distribution"},
            alt=f"Histogram of {label} across the plausible range."))

    f = Finding(
        id="anthro.distributions", part="4.3",
        title="Distributions and plausibility bounds",
        values={"n_channels": len(CHANNELS)},
    )
    f.blocks = [
        Para("The four measurement channels, summarised on the derived metric "
             "columns. The final two columns give the screening range each channel "
             "is checked against and how many values fall outside it; those are "
             "reported, not removed, because the decision to exclude belongs to the "
             "analysis rather than to this report."),
        Table("t-dist", "Measurement channels",
              [Column("channel", "channel"), Column("unit", "unit"),
               Column("n", "values", ",", align="right"),
               Column("min", "min", ",.2f", align="right"),
               Column("p1", "1st pct", ",.2f", align="right"),
               Column("median", "median", ",.2f", align="right"),
               Column("p99", "99th pct", ",.2f", align="right"),
               Column("max", "max", ",.2f", align="right"),
               Column("range", "review range"),
               Column("outside", "outside review range", ",", align="right")], rows,
              note="The review range is a wide screening band, chosen to catch "
                   "values no measurement could produce. It is not the tighter "
                   "clinical band a channel may also have: 4.7 screens head "
                   "circumference against 25 to 65 cm and counts more values "
                   "outside it than this column does."),
        *figures,
        Para("**Implications for analysis.** Head circumference is the channel whose "
             "tails are worst, and 4.7 shows why — an arithmetic defect, not a "
             "measurement one. For the others the extremes are "
             "sparse but the bulk is clinically ordinary. Bound the raw imperial "
             "columns rather than the derived metric ones when screening, since a "
             "wrong unit survives an exact conversion unchanged.",
             role="implication"),
    ]
    return [f]


@probe("anthro.derived", "4.6")
def derived(ctx: Context) -> list[Finding]:
    z_rows = []
    for col, label in Z_CHANNELS:
        n, mn, mx = ctx.one(
            f"SELECT count({col}), min({col}), max({col}) FROM visits_augmented")
        beyond = ctx.scalar(
            f"SELECT count(*) FROM visits_augmented WHERE abs({col}) > 5")
        z_rows.append({"channel": label, "n": n, "min": mn, "max": mx,
                       "beyond": ctx.suppress(beyond)})

    p_rows = []
    for col, label in PCT_CHANNELS:
        n, at0, at100 = ctx.one(
            f"SELECT count({col}), sum(CASE WHEN {col} = 0 THEN 1 ELSE 0 END), "
            f"sum(CASE WHEN {col} = 100 THEN 1 ELSE 0 END) FROM visits_augmented")
        p_rows.append({"channel": label, "n": n, "at0": at0, "at100": at100,
                       "share0": 100.0 * at0 / n if n else 0.0,
                       "share100": 100.0 * at100 / n if n else 0.0})

    loose = sorted((r for r in z_rows if (r["beyond"] or 0) > 0),
                   key=lambda r: -r["beyond"])
    loose_list = ", ".join(
        f"{r['channel'].removesuffix(' z')} ({r['beyond']:,})" for r in loose)

    lower25, lower3, upper25, upper3 = ctx.one(
        "SELECT sum(CASE WHEN height_z_score <= -2.5 THEN 1 ELSE 0 END), "
        "       sum(CASE WHEN height_z_score <= -3 THEN 1 ELSE 0 END), "
        "       sum(CASE WHEN height_z_score >= 2.5 THEN 1 ELSE 0 END), "
        "       sum(CASE WHEN height_z_score >= 3 THEN 1 ELSE 0 END) "
        "FROM visits_augmented WHERE height_z_score IS NOT NULL")
    expected = round(upper25 * lower3 / lower25 / 100) * 100
    edges = [-5 + 0.25 * i for i in range(41)]
    counts = [ctx.scalar(
        f"SELECT count(*) FROM visits_augmented WHERE height_z_score >= {edges[i]} "
        f"AND height_z_score < {edges[i + 1]}") for i in range(40)]

    f = Finding(
        id="anthro.derived", part="4.6",
        title="Derived z-scores and percentiles: bounds and saturation",
        values={"lower25": lower25, "lower3": lower3, "upper25": upper25,
                "upper3": upper3,
                "lower_share": 100.0 * lower3 / lower25,
                "upper_share": 100.0 * upper3 / upper25,
                "expected": expected,
                "max_hz": max(r["max"] for r in z_rows if r["channel"] == "height z"),
                "n_z": len(Z_CHANNELS), "n_pct": len(PCT_CHANNELS),
                "clamp": Z_CLAMP,
                "min_hz": next(r["min"] for r in z_rows if r["channel"] == "height z"),
                "min_wz": next(r["min"] for r in z_rows if r["channel"] == "weight z"),
                "max_wz": next(r["max"] for r in z_rows if r["channel"] == "weight z"),
                # z = 3 is this percentile, so a channel bounded there cannot
                # reach 100 — which is what the percentile table shows.
                "pct_at_bound": 100.0 * 0.5 * (1.0 + math.erf(3.0 / math.sqrt(2.0))),
                "n_loose": len(loose), "loose": loose_list,
                "h_at100": next(r["at100"] for r in p_rows if r["channel"] == "height"),
                "w_at100": next(r["at100"] for r in p_rows if r["channel"] == "weight"),
                "n_h": next(r["n"] for r in p_rows if r["channel"] == "height"),
                "n_other": len(loose) - 1},
        artifact=Artifact(
            name="Height z-score truncated above at +3 while the lower tail runs to -5",
            kind="derivation",
            scale="{upper3:,} visits at or above +3 where roughly {expected:,} "
                  "would be expected",
            recoverable="Yes — recompute from the retained raw height",
        ),
    )
    f.blocks = [
        Para("The derived channels are not a neutral restatement of the "
             "measurements. Each carries its own support, and they do not share one."),
        Table("t-z", "Z-score channels",
              [Column("channel", "channel"), Column("n", "values", ",", align="right"),
               Column("min", "minimum", ",.4f", align="right"),
               Column("max", "maximum", ",.4f", align="right"),
               Column("beyond", "beyond |5|", ",", align="right")], z_rows),
        Para("**Two of these channels are clamped, and one of them twice.** Height "
             "z and weight z both stop a ten-thousandth short of ±{clamp:.0f} — "
             "height at {min_hz:.4f}, weight at {min_wz:.4f} and {max_wz:.4f} — and "
             "the `beyond` column is 0 for each, which is a bound rather than a tail "
             "that happens to end. Height is then clamped again, far tighter, on one "
             "side only: at exactly {max_hz:.2f}. So the asymmetry that exposes it is "
             "between two bounds, not between a bound and a free tail."),
        Para("The upper truncation leaves no pile-up at the boundary, so it is "
             "invisible in a summary: only {upper3:,} visits sit at or above +3. The "
             "tails are what give it away. Below, {lower3:,} of the {lower25:,} "
             "visits beyond -2.5 continue past -3 — {lower_share:.1f}%. Above, "
             "{upper25:,} visits sit beyond +2.5, so at the same rate roughly "
             "{expected:,} of them would carry on past +3 rather than the "
             "{upper3:,} that do."),
        Figure("fig-hz", "Height z-score, both tails", "hist",
               {"edges": edges, "counts": counts, "height": 260,
                "marks": [{"at": 3.0, "label": "+3 bound"}],
                "title": "Height z-score distribution"},
               alt="A distribution stopping abruptly at +3 while the left tail continues."),
        Table("t-pct", "Percentile channels and their saturation points",
              [Column("channel", "channel"), Column("n", "values", ",", align="right"),
               Column("at0", "exactly 0", ",", align="right"),
               Column("share0", "share", ".3f", "%", align="right"),
               Column("at100", "exactly 100", ",", align="right"),
               Column("share100", "share", ".3f", "%", align="right")], p_rows),
        Para("The height row is the truncation again, one transform along. A z of "
             "3 is the {pct_at_bound:.2f}th percentile, so a channel bounded there "
             "cannot reach 100 — and it does not, on any of its {n_h:,} values, "
             "against {w_at100:,} for weight. The bound propagates, which is the "
             "clearest evidence that it is a property of the derivation and not of "
             "how the z was summarised. Head circumference is listed here for "
             "completeness; its percentile inherits the defect 4.7 measures in its "
             "z, so its saturation counts describe that defect rather than the "
             "children."),
        Para("**Four channels carry mass the reference cannot produce**, counted in "
             "the `beyond` column above: {loose}. 4.7 takes up head circumference, "
             "where the cause is known and most of it is repairable. The other "
             "{n_other} are not explained anywhere in this report. Their extremes "
             "are reported so that a model consuming them does so knowingly; no "
             "mechanism has been established for them here.", role="warning"),
        Para("**Implications for analysis.** The height channel cannot support any "
             "question about tall stature: its upper tail is absent, and a "
             "trajectory approaching the bound from below is distorted too. The "
             "percentile channels carry point masses at exactly 0 and 100 that are "
             "saturated rather than measured, so they are not continuous and should "
             "not be modelled as such. Because the {n_z} z channels do not share a "
             "support, a model consuming several of them together inherits the "
             "inconsistency silently. Recomputing from the raw measurement against a "
             "stated reference avoids most of this — but not for head circumference, "
             "where 4.7 shows the z transform is defective independently of the "
             "measurement, so recomputation is necessary there and not sufficient.",
             role="implication"),
    ]
    return [f]

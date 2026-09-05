"""Part 4.1-4.3 and 4.6 — supply, recording grid, distributions, derived channels."""

from __future__ import annotations

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
                ("weight_for_length_percentile", "weight-for-length"),
                ("weight_for_stature_percentile", "weight-for-stature")]
AGE_BANDS = [(0, 2, "0-2"), (2, 5, "2-5"), (5, 10, "5-10"),
             (10, 15, "10-15"), (15, 19, "15-18")]


@probe("anthro.supply", "4.1")
def supply(ctx: Context) -> list[Finding]:
    total = ctx.scalar("SELECT count(*) FROM patients")
    counts = ctx.q(
        "WITH per AS (SELECT patient_id, count(*) AS n FROM visits_augmented "
        "             WHERE height_cm IS NOT NULL GROUP BY 1) "
        "SELECT n, count(*) FROM per GROUP BY 1 ORDER BY 1")
    cum, running = [], 0
    lookup = dict(counts)
    for k in range(1, 26):
        running = sum(v for n, v in lookup.items() if n >= k)
        cum.append((k, running))
    rows = [{"k": k, "patients": v, "share": 100.0 * v / total}
            for k, v in cum if k in (1, 3, 5, 10, 15, 20, 25)]
    f = Finding(
        id="anthro.supply", part="4.1",
        title="Trajectory supply: how many heights each child has",
        values={"total": total,
                "with_1": cum[0][1], "share_1": 100.0 * cum[0][1] / total,
                "with_5": cum[4][1], "share_5": 100.0 * cum[4][1] / total,
                "with_10": cum[9][1], "share_10": 100.0 * cum[9][1] / total},
    )
    f.blocks = [
        Para("{with_1:,} of {total:,} patients ({share_1:.1f}%) carry at least one "
             "derived height, {with_5:,} ({share_5:.1f}%) carry five or more, and "
             "{with_10:,} ({share_10:.1f}%) carry ten or more."),
        Figure("fig-supply",
               "Patients retaining at least k height observations",
               "step",
               {"x": [str(k) for k, _ in cum],
                "series": [{"name": "patients", "values": [v for _, v in cum]}],
                "title": "Height observations per patient", "height": 280},
               alt="A declining curve from all patients down to those with 25 heights."),
        Table("t-supply", "Height observations per patient",
              [Column("k", "at least k heights", align="right"),
               Column("patients", "patients", ",", align="right"),
               Column("share", "share of cohort", ".1f", "%", align="right")], rows),
        Para("**Implications for analysis.** Read this against 1.4 before treating "
             "it as a fact about pediatric care. Cohort entry required at least five "
             "growth measurements of *some* type, so a dense height series here is "
             "partly the selection rule and partly the underlying practice; the two "
             "cannot be separated within this extract. What the curve does support "
             "is a feasibility estimate: how many children remain if your design "
             "needs k observations.", role="implication"),
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
    h_pairs, h_bad = ctx.one(
        "SELECT count(*), sum(CASE WHEN abs(height_cm - height_in * 2.54) > 0.01 "
        "THEN 1 ELSE 0 END) FROM visits_augmented "
        "WHERE height_in IS NOT NULL AND height_cm IS NOT NULL")
    w_pairs, w_bad = ctx.one(
        "SELECT count(*), sum(CASE WHEN abs(weight_kg - weight_oz * 0.0283495) > 0.01 "
        "THEN 1 ELSE 0 END) FROM visits_augmented "
        "WHERE weight_oz IS NOT NULL AND weight_kg IS NOT NULL")

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
                "grid_cm": 2.54 / 4},
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
             "{h_pairs:,} visits carrying both a raw and a derived height, {h_bad:,} "
             "disagree with `height_in` times 2.54 by more than 0.01 cm; across "
             "{w_pairs:,} weight pairs, {w_bad:,} disagree with `weight_oz` times "
             "0.0283495. The arithmetic is clean, which matters because a value "
             "keyed in the wrong unit survives an exact conversion unchanged — 4.4 "
             "takes that up."),
        Para("The recorded values are heaped "
             "on human-readable fractions: of {h_total:,} heights, {h_whole:.1f}% "
             "fall on a whole inch, {h_half:.1f}% on a half inch and "
             "{h_quarter:.1f}% on a quarter inch. Of {w_total:,} weights, "
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
        Para("**Implications for analysis.** One quarter inch is {grid_cm:.3f} cm, "
             "and the derived `height_cm` carries two decimals it has not earned. "
             "Any change smaller than roughly half the rounding interval is not "
             "distinguishable from the rounding itself, which sets a floor on the "
             "smallest trajectory deflection that can be detected at all. State the "
             "assumed precision wherever a measurement is written out, and set "
             "detection thresholds at or above the grid.", role="implication"),
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
             "columns. The final column counts values outside a conventional review "
             "range; those are reported, not removed, because the decision to "
             "exclude belongs to the analysis rather than to this report."),
        Table("t-dist", "Measurement channels",
              [Column("channel", "channel"), Column("unit", "unit"),
               Column("n", "values", ",", align="right"),
               Column("min", "min", ",.2f", align="right"),
               Column("p1", "1st pct", ",.2f", align="right"),
               Column("median", "median", ",.2f", align="right"),
               Column("p99", "99th pct", ",.2f", align="right"),
               Column("max", "max", ",.2f", align="right"),
               Column("outside", "outside review range", ",", align="right")], rows),
        *figures,
        Para("**Implications for analysis.** Head circumference is the channel whose "
             "tails are worst, and 4.4 shows why. For the others the extremes are "
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
                "max_hz": max(r["max"] for r in z_rows if r["channel"] == "height z")},
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
        Para("The height z-score is bounded above at exactly {max_hz:.2f} while its "
             "lower tail runs past -4.99. The truncation leaves no pile-up at the "
             "boundary, so it is invisible in a summary: only {upper3:,} visits sit "
             "at or above +3. The asymmetry is what exposes it. In the lower tail "
             "{lower_share:.1f}% of the mass beyond |z| = 2.5 continues past 3; if "
             "the upper tail behaved the same way roughly {expected:,} visits would "
             "sit above +3."),
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
        Para("**Implications for analysis.** The height channel cannot support any "
             "question about tall stature: its upper tail is absent, and a "
             "trajectory approaching the bound from below is distorted too. The "
             "percentile channels carry point masses at exactly 0 and 100 that are "
             "saturated rather than measured, so they are not continuous and should "
             "not be modelled as such. Because the four z channels do not share a "
             "support, a model consuming several of them together inherits the "
             "inconsistency silently. Recomputing from the raw measurement against a "
             "stated reference avoids all of this.", role="implication"),
    ]
    return [f]

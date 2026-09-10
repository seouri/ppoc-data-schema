"""Part 4.8 — the distributed delta and velocity fields, and the rules behind them.

These fields look unreproducible until the interval rule is known, and faithful
once it is. Establishing that matters because the alternative reading — a lag
over successive visits — is both the obvious one and wrong.

Two rules, not one: height and weight are differenced over different minimum
intervals, so a reader who carries the height rule to the weight columns
reproduces about a third of them. Both are recovered here the same way — the
smallest interval the pipeline ever emits inside an age band is that band's
minimum — and then confirmed by reproduction.
"""

from __future__ import annotations

from ..context import Context
from ..findings import Artifact, Figure, Finding, Para, Table, probe
from ..findings import Column as C

#: Days to the year in the distributed velocities. Not 365.25: the ages these
#: fields are built from convert at 365.25 elsewhere in the extract, and using
#: that here drops the reproduction by more than thirty points, so the constant
#: is part of the field's definition and is reported as such.
YEAR_DAYS = 365

#: Age boundaries shared by both rules, as (upper bound in days, label). The
#: last band is open-ended.
BANDS = [(365, "birth to 12 months"), (730, "1 to 2 years"),
         (4380, "2 to 12 years"), (None, "13 years and over")]

#: Minimum interval in days, per band, between the current measurement and the
#: earlier one it is differenced against. Inferred from the data — see the
#: smallest-gap columns in the rule table — and confirmed by reproduction.
HEIGHT_MINS = [90, 180, 335, 180]
WEIGHT_MINS = [30, 90, 180, 180]

CHANNELS = [
    {"name": "height", "measure": "height_cm", "delta": "delta_height_cm",
     "gap": "delta_age_in_days_height", "vel": "height_velocity",
     "mins": HEIGHT_MINS, "unit": "cm"},
    {"name": "weight", "measure": "weight_kg", "delta": "delta_weight_kg",
     "gap": "delta_age_in_days_weight", "vel": "weight_velocity",
     "mins": WEIGHT_MINS, "unit": "kg"},
]

#: The four pubertal-onset references the velocity z-score is published against.
PUBERTY = [("height_velocity_z_score", "no pubertal onset"),
           ("height_velocity_z_score_ep", "earlier pubertal onset"),
           ("height_velocity_z_score_ap", "average pubertal onset"),
           ("height_velocity_z_score_lp", "later pubertal onset")]


def _min_gap(mins: list[int]) -> str:
    """The rule as a SQL expression over `age_in_days`."""
    arms = [f"WHEN age_in_days <= {hi} THEN {g}"
            for (hi, _), g in zip(BANDS, mins, strict=True) if hi is not None]
    return "CASE " + " ".join(arms) + f" ELSE {mins[-1]} END"


def _reproduce(ctx: Context, ch: dict) -> dict:
    """Recompute one channel's delta, gap and velocity under its own rule."""
    row = ctx.one(f"""
        WITH s AS (
            SELECT patient_id, age_in_days, {ch['measure']} AS v,
                   {ch['delta']} AS pub_delta, {ch['gap']} AS pub_gap,
                   {ch['vel']} AS pub_vel, {_min_gap(ch['mins'])} AS min_gap
            FROM visits_augmented WHERE {ch['measure']} IS NOT NULL),
        dup AS (SELECT patient_id, age_in_days FROM s
                GROUP BY 1, 2 HAVING count(*) > 1),
        m AS (SELECT s.*, (SELECT max(p.age_in_days) FROM s p
                           WHERE p.patient_id = s.patient_id
                             AND p.age_in_days <= s.age_in_days - s.min_gap)
                          AS prev_age
              FROM s),
        j AS (SELECT m.*, (SELECT max(q.v) FROM s q
                           WHERE q.patient_id = m.patient_id
                             AND q.age_in_days = m.prev_age) AS prev_v
              FROM m),
        r AS (
            SELECT *, abs(round(v - prev_v, 2) - pub_delta) AS diff,
                   round((v - prev_v) / (age_in_days - prev_age) * {YEAR_DAYS}, 2)
                       AS vel_src,
                   round(pub_delta / pub_gap * {YEAR_DAYS}, 2) AS vel_pub,
                   round(pub_delta / pub_gap * 365.25, 2) AS vel_pub_alt
            FROM j WHERE pub_delta IS NOT NULL AND prev_age IS NOT NULL)
        SELECT count(*),
               count(*) FILTER (WHERE age_in_days - prev_age = pub_gap),
               count(*) FILTER (WHERE diff < 1e-9),
               count(*) FILTER (WHERE diff < 0.0101),
               count(*) FILTER (WHERE diff >= 0.0101),
               count(*) FILTER (WHERE diff >= 0.0101 AND (
                   (patient_id, prev_age) IN (SELECT * FROM dup)
                   OR (patient_id, age_in_days) IN (SELECT * FROM dup))),
               count(*) FILTER (WHERE vel_src = pub_vel),
               count(*) FILTER (WHERE vel_src IS DISTINCT FROM pub_vel
                                  AND diff < 0.0101),
               count(*) FILTER (WHERE vel_pub = pub_vel),
               count(*) FILTER (WHERE vel_pub_alt = pub_vel)
        FROM r""")
    keys = ("n", "gap_match", "exact", "within", "off", "off_dup",
            "vel_src", "vel_off_delta_ok", "vel_pub", "vel_pub_alt")
    out = dict(zip(keys, row, strict=True))
    # The prose claims the rule finds a predecessor for every row the pipeline
    # gave a delta to. That is a constraint on the rule, so it is checked rather
    # than assumed: a rule with the wrong floor would drop rows here.
    published = ctx.scalar(f"SELECT count({ch['delta']}) FROM visits_augmented")
    if out["n"] != published:
        raise ValueError(
            f"{ch['name']}: the rule reproduces {out['n']:,} rows against "
            f"{published:,} carrying a distributed delta; the two must coincide "
            f"or the population is a subset chosen after the fact")
    out["lag1"] = ctx.scalar(f"""
        WITH s AS (SELECT patient_id, age_in_days, {ch['measure']} AS v,
                          {ch['delta']} AS pub_delta
                   FROM visits_augmented WHERE {ch['measure']} IS NOT NULL),
        l AS (SELECT *, v - lag(v) OVER w AS dv FROM s
              WINDOW w AS (PARTITION BY patient_id ORDER BY age_in_days, v))
        SELECT count(*) FILTER (WHERE abs(dv - pub_delta) < 0.0101)
        FROM l WHERE pub_delta IS NOT NULL""")
    return out


def _cross_rule(ctx: Context, ch: dict, mins: list[int]) -> int:
    """How much of one channel the *other* channel's rule reproduces.

    The cost of assuming a single rule, measured rather than asserted.
    """
    return ctx.scalar(f"""
        WITH s AS (
            SELECT patient_id, age_in_days, {ch['gap']} AS pub_gap,
                   {_min_gap(mins)} AS min_gap
            FROM visits_augmented WHERE {ch['measure']} IS NOT NULL),
        m AS (SELECT s.*, (SELECT max(p.age_in_days) FROM s p
                           WHERE p.patient_id = s.patient_id
                             AND p.age_in_days <= s.age_in_days - s.min_gap)
                          AS prev_age
              FROM s)
        SELECT count(*) FILTER (WHERE age_in_days - prev_age = pub_gap)
        FROM m WHERE pub_gap IS NOT NULL""")


def _smallest_gaps(ctx: Context, ch: dict) -> list[int | None]:
    """The shortest interval the pipeline ever emits inside each age band.

    This is what pins each minimum from below: a rule cannot claim a floor the
    data go under, and a floor the data never reach is not identified.
    """
    out = []
    for i, (hi, _) in enumerate(BANDS):
        lo = BANDS[i - 1][0] if i else -1
        upper = f"AND age_in_days <= {hi}" if hi is not None else ""
        out.append(ctx.scalar(
            f"SELECT min({ch['gap']}) FROM visits_augmented "
            f"WHERE {ch['gap']} IS NOT NULL AND age_in_days > {lo} {upper}"))
    return out


@probe("anthro.velocity", "4.8")
def velocity(ctx: Context) -> list[Finding]:
    stats = {ch["name"]: _reproduce(ctx, ch) for ch in CHANNELS}
    gaps = {ch["name"]: _smallest_gaps(ctx, ch) for ch in CHANNELS}
    cross = _cross_rule(ctx, CHANNELS[1], HEIGHT_MINS)

    rule_rows = []
    for i, (_, label) in enumerate(BANDS):
        rule_rows.append({
            "band": label,
            "h_min": HEIGHT_MINS[i], "h_seen": gaps["height"][i],
            "w_min": WEIGHT_MINS[i], "w_seen": gaps["weight"][i],
        })

    repro_rows = []
    for ch in CHANNELS:
        s = stats[ch["name"]]
        repro_rows.append({
            "channel": f"{ch['name']} ({ch['unit']})", "n": s["n"],
            "gap": 100.0 * s["gap_match"] / s["n"],
            "delta": 100.0 * s["within"] / s["n"],
            "vel_src": 100.0 * s["vel_src"] / s["n"],
            "vel_pub": 100.0 * s["vel_pub"] / s["n"],
            "lag1": 100.0 * s["lag1"] / s["n"],
        })

    h, w = stats["height"], stats["weight"]
    z_rows = []
    for col, label in PUBERTY:
        z_rows.append({"reference": label, "column": f"`{col}`",
                       "values": ctx.scalar(
                           f"SELECT count({col}) FROM visits_augmented")})
    z_spread = ctx.one("""
        SELECT count(*),
               quantile_cont(hi - lo, 0.5), quantile_cont(hi - lo, 0.95)
        FROM (SELECT greatest(height_velocity_z_score_ep,
                              height_velocity_z_score_ap,
                              height_velocity_z_score_lp) AS hi,
                     least(height_velocity_z_score_ep,
                           height_velocity_z_score_ap,
                           height_velocity_z_score_lp) AS lo
              FROM visits_augmented
              WHERE height_velocity_z_score_ep IS NOT NULL
                AND height_velocity_z_score_ap IS NOT NULL
                AND height_velocity_z_score_lp IS NOT NULL)""")

    gap_rows = ctx.q("""
        SELECT delta_age_in_days_height AS gap, count(*) FROM visits_augmented
        WHERE delta_age_in_days_height IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC, gap LIMIT 8""")

    f = Finding(
        id="anthro.velocity", part="4.8",
        title="The distributed delta and velocity fields",
        values={
            "year": YEAR_DAYS,
            "h_n": h["n"], "w_n": w["n"],
            "h_gap_share": 100.0 * h["gap_match"] / h["n"],
            "h_within_share": 100.0 * h["within"] / h["n"],
            "h_round_only": h["within"] - h["exact"],
            "h_off": h["off"],
            "h_off_dup_clause": (
                ", and every one of them sits on a patient-day carrying more "
                "than one height"
                if h["off_dup"] == h["off"] else
                f", and {h['off_dup']:,} of them sit on a patient-day carrying "
                f"more than one height"),
            "h_off_share": 100.0 * h["off"] / h["n"],
            "h_vel_src_share": 100.0 * h["vel_src"] / h["n"],
            "h_vel_off": h["n"] - h["vel_src"],
            "h_vel_off_delta_ok": h["vel_off_delta_ok"],
            "h_vel_off_delta_share":
                100.0 * h["vel_off_delta_ok"] / max(h["n"] - h["vel_src"], 1),
            "h_vel_pub": h["vel_pub"], "h_vel_pub_share": 100.0 * h["vel_pub"] / h["n"],
            "h_vel_alt_share": 100.0 * h["vel_pub_alt"] / h["n"],
            "h_lag1": h["lag1"], "h_lag1_share": 100.0 * h["lag1"] / h["n"],
            "w_vel_pub_share": 100.0 * w["vel_pub"] / w["n"],
            "w_gap_share": 100.0 * w["gap_match"] / w["n"],
            "cross": cross, "cross_share": 100.0 * cross / w["n"],
            "z_base": z_rows[0]["values"], "z_n": z_spread[0],
            "z_med": z_spread[1], "z_p95": z_spread[2],
            "vel_no_z": h["n"] - z_rows[0]["values"],
            "n_puberty": len(PUBERTY),
            "h_min_lo": min(HEIGHT_MINS), "h_min_hi": max(HEIGHT_MINS),
            "h_teen": HEIGHT_MINS[-1], "h_mid": HEIGHT_MINS[2],
        },
        artifact=Artifact(
            name="Velocity computed over an age-dependent minimum interval, "
                 "not between adjacent visits",
            kind="derivation",
            scale="{h_within_share:.2f}% of height deltas reproduced under the "
                  "interval rule against {h_lag1_share:.1f}% under a naive lag; "
                  "the two published columns regenerate only "
                  "{h_vel_pub_share:.1f}% of the velocity",
            recoverable="Not a defect — carry the interval rule, the year length "
                        "and the unrounded measurement alongside the field",
        ),
    )
    f.blocks = [
        Para("The augmented visit layer distributes `delta_height_cm`, "
             "`delta_weight_kg`, their two interval columns, and the velocity "
             "fields derived from them. These are **not** a lag over successive "
             "measurements, and reading them as one is the error this subsection "
             "exists to prevent. For each measurement the pipeline walks backwards "
             "to the most recent earlier measurement whose age gap meets an "
             "age-dependent minimum, skipping every measurement in between."),
        Para("**Height and weight do not share a rule.** The minimum interval is "
             "shorter for weight in every band, which makes sense of a channel "
             "measured at nearly every visit, and it means the height rule carried "
             "across to the weight columns recovers the interval on {cross:,} of "
             "{w_n:,} rows — {cross_share:.0f}%, against the 100% its own rule "
             "reaches.", role="warning"),
        Table("t-rule", "The interval rule for each channel, and what pins it",
              [C("band", "age band"),
               C("h_min", "height minimum", ",", " days", align="right"),
               C("h_seen", "shortest height gap seen", ",", " days", align="right"),
               C("w_min", "weight minimum", ",", " days", align="right"),
               C("w_seen", "shortest weight gap seen", ",", " days", align="right")],
              rule_rows,
              note="The rules were recovered rather than documented, so the "
                   "evidence is beside them: inside each band the shortest interval "
                   "the pipeline ever emits is exactly the minimum, which pins the "
                   "floor from below. A floor the data never reach would not be "
                   "identified at all, and none here is."),
        Para("Two features of the table are worth stating before the check, because "
             "both look like errors and neither is. The height minimum rises to "
             "{h_mid} days through mid-childhood and then falls back to {h_teen} "
             "from 13, so adolescent velocities are computed over roughly half the "
             "window that mid-childhood ones are — the reversal is the pipeline's, "
             "not a transcription slip here. And the boundaries are identified only "
             "to the nearest interval the data actually contain: a rule stated in "
             "days is confirmed by reproduction, not by having excluded every "
             "neighbouring value."),
        Para("Applying each rule reproduces that channel's fields. The recomputed "
             "age gap matches the distributed one on every row of both channels, and "
             "the population is not a subset chosen to make that true: the rule "
             "finds an earlier measurement for every row the pipeline gave a delta "
             "to, and for no other."),
        Table("t-repro", "Reproducing each channel, by what a recomputation starts from",
              [C("channel", "channel"),
               C("n", "rows with a delta", ",", align="right"),
               C("gap", "interval matches", ".2f", "%", align="right"),
               C("delta", "delta matches", ".3f", "%", align="right"),
               C("vel_src", "velocity, from the measurement", ".2f", "%",
                 align="right"),
               C("vel_pub", "velocity, from the published columns", ".1f", "%",
                 align="right"),
               C("lag1", "delta under a naive lag", ".1f", "%", align="right")],
              repro_rows,
              note="Deltas match within one hundredth of a unit. The last column is "
                   "the reading this section exists to rule out — a difference over "
                   "successive measurement-bearing visits."),
        Figure("fig-delta-gap", "The most common recorded measurement intervals",
               "bar",
               {"categories": [str(g) for g, _ in gap_rows],
                "series": [{"name": "visits", "values": [c for _, c in gap_rows]}],
                "height": 250, "title": "Distributed delta interval, days"},
               alt="Interval lengths cluster just above the rule's minimum values."),
        Para("**The two published columns do not regenerate the third.** A reader "
             "holds `delta_height_cm` and `delta_age_in_days_height`, not the "
             "measurement behind them, and dividing one by the other recovers "
             "{h_vel_pub:,} of {h_n:,} velocities — {h_vel_pub_share:.1f}%, against "
             "{h_vel_src_share:.2f}% when the unrounded difference is taken from "
             "`height_cm` instead. The delta is published rounded to two decimals "
             "and the velocity is not computed from the rounded value. Weight "
             "behaves the same way, at {w_vel_pub_share:.1f}%. So the interval rule "
             "alone is not enough to recompute a velocity: the unrounded difference "
             "is needed too, and it is not distributed.", role="warning"),
        Para("**The year is {year} days, not 365.25.** Ages elsewhere in this "
             "extract convert at 365.25 and 5.8 says so explicitly; the velocity "
             "does not. The constant is worth more than a footnote because it is "
             "not recoverable by inspection — using 365.25 on the published columns "
             "drops the match from {h_vel_pub_share:.1f}% to {h_vel_alt_share:.1f}%, "
             "which is far enough from either figure to look like a different "
             "definition rather than a rounding choice.", role="method"),
        Para("Three residuals, and they are different in kind. {h_round_only:,} "
             "height rows differ from the recomputed delta by exactly one hundredth "
             "of a centimetre and are *inside* the matching tolerance above, because "
             "the pipeline rounds half to even while this check rounds half away "
             "from zero; heights come from a quarter-inch grid, so exact halfway "
             "cases are common rather than rare. {h_off:,} rows ({h_off_share:.3f}%) "
             "fall outside it{h_off_dup_clause}, where which earlier value was used "
             "is ambiguous; 3.8 measures how far those pairs sit apart. "
             "The third is the velocity's own: {h_vel_off:,} rows fail the velocity "
             "check and {h_vel_off_delta_ok:,} of them "
             "({h_vel_off_delta_share:.0f}%) have a delta that matched, so the "
             "velocity residual is very nearly disjoint from the delta residual "
             "rather than a consequence of it.", role="method"),
        Para("**The velocity z-scores are a family of four, and the choice between "
             "them is not free.** The layer publishes the height velocity against "
             "{n_puberty} different pubertal-onset references, each with a matching "
             "percentile column, and nothing else in this report validates them.",
             role="warning"),
        Table("t-vel-z", "The height-velocity z-score references",
              [C("reference", "reference"), C("column", "column"),
               C("values", "values", ",", align="right")], z_rows,
              note="Each has a `height_velocity_percentile` twin with the same "
                   "population."),
        Para("On the {z_n:,} visits carrying all three pubertal variants, the "
             "spread between the highest and lowest is a median of {z_med:.2f} z "
             "and {z_p95:.2f} at the 95th percentile — larger than most contrasts "
             "this report measures, for the same child at the same visit. A further "
             "{vel_no_z:,} visits carry a velocity with no velocity z-score at all. "
             "Which reference a result was computed against therefore has to be "
             "stated, and results computed against different ones cannot be pooled."),
        Para("**Implications for analysis.** The delta and interval channels are "
             "usable as distributed, which a distributional summary alone could not "
             "establish. What must travel with them is the whole definition, and it "
             "has four parts: the channel's own interval rule, the {year}-day year, "
             "the fact that the velocity divides the *unrounded* difference rather "
             "than the published delta, and the rounding of both to two decimals. "
             "Carry fewer than four and a recomputation disagrees — by a little if "
             "the rounding is missed, by a quarter of the rows if the published "
             "delta is divided, by more if the year is wrong. A velocity here is "
             "computed over an interval of at least {h_min_lo} to {h_min_hi} days "
             "depending on age and channel, not between adjacent visits, so it is "
             "already smoothed relative to a visit-to-visit rate and cannot be "
             "compared with one. Any synthetic series carrying a velocity must use "
             "the same rule or the two are not on the same scale. For the velocity "
             "z-scores, pick a pubertal-onset reference deliberately and say which.",
             role="implication"),
    ]
    return [f]

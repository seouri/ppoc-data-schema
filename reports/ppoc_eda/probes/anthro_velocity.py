"""Part 4.8 — the distributed delta and velocity fields, and the rule behind them.

These fields look unreproducible until the interval rule is known, and faithful
once it is. Establishing that matters because the alternative reading — a lag
over successive visits — is both the obvious one and wrong.
"""

from __future__ import annotations

from ..context import Context
from ..findings import Artifact, Figure, Finding, Para, Table, probe
from ..findings import Column as C

#: Minimum interval, in days, between the current height and the earlier one it
#: is differenced against. Inferred from the data and confirmed by reproduction.
MIN_GAP = """
    CASE WHEN age_in_days <= 365 THEN 90
         WHEN age_in_days <= 730 THEN 180
         WHEN age_in_days <= 4380 THEN 335
         ELSE 180 END
"""
RULE = [("birth to 12 months", "up to 365 days", 90),
        ("1 to 2 years", "up to 730 days", 180),
        ("2 to 12 years", "up to 4380 days", 335),
        ("13 years and over", "beyond 4380 days", 180)]


@probe("anthro.velocity", "4.8")
def velocity(ctx: Context) -> list[Finding]:
    n, age_match, exact, within, off, vel_match = ctx.one(f"""
        WITH h AS (
            SELECT patient_id, age_in_days, height_cm, delta_height_cm,
                   delta_age_in_days_height, height_velocity, {MIN_GAP} AS min_gap
            FROM visits_augmented WHERE height_cm IS NOT NULL),
        m AS (
            SELECT h.*, (SELECT max(p.age_in_days) FROM h p
                         WHERE p.patient_id = h.patient_id
                           AND p.age_in_days <= h.age_in_days - h.min_gap) AS prev_age
            FROM h),
        j AS (
            SELECT m.*, (SELECT max(p2.height_cm) FROM h p2
                         WHERE p2.patient_id = m.patient_id
                           AND p2.age_in_days = m.prev_age) AS prev_h
            FROM m),
        d AS (
            SELECT *, abs(round(height_cm - prev_h, 2) - delta_height_cm) AS diff
            FROM j WHERE delta_height_cm IS NOT NULL AND prev_age IS NOT NULL)
        SELECT count(*),
               sum(CASE WHEN age_in_days - prev_age = delta_age_in_days_height
                        THEN 1 ELSE 0 END),
               sum(CASE WHEN diff < 1e-9 THEN 1 ELSE 0 END),
               sum(CASE WHEN diff < 0.0101 THEN 1 ELSE 0 END),
               sum(CASE WHEN diff >= 0.0101 THEN 1 ELSE 0 END),
               sum(CASE WHEN round((height_cm - prev_h) / (age_in_days - prev_age)
                                   * 365, 2) = height_velocity THEN 1 ELSE 0 END)
        FROM d""")

    lag1 = ctx.scalar("""
        WITH s AS (SELECT patient_id, age_in_days, height_cm, delta_height_cm
                   FROM visits_augmented WHERE height_cm IS NOT NULL),
        l AS (SELECT *, height_cm - lag(height_cm) OVER w AS dh FROM s
              WINDOW w AS (PARTITION BY patient_id ORDER BY age_in_days, height_cm))
        SELECT sum(CASE WHEN abs(dh - delta_height_cm) < 0.0101 THEN 1 ELSE 0 END)
        FROM l WHERE delta_height_cm IS NOT NULL""")

    gap_rows = ctx.q("""
        SELECT delta_age_in_days_height AS gap, count(*) FROM visits_augmented
        WHERE delta_age_in_days_height IS NOT NULL
        GROUP BY 1 ORDER BY 2 DESC LIMIT 8""")

    f = Finding(
        id="anthro.velocity", part="4.8",
        title="The distributed delta and velocity fields",
        values={
            "n": n, "age_match": age_match,
            "age_share": 100.0 * age_match / n,
            "within": within, "within_share": 100.0 * within / n,
            "off": off, "off_share": 100.0 * off / n,
            "vel_share": 100.0 * vel_match / n,
            "lag1": lag1, "lag1_share": 100.0 * lag1 / n,
            "round_only": within - exact,
        },
        artifact=Artifact(
            name="Velocity computed over an age-dependent minimum interval, "
                 "not between adjacent visits",
            kind="derivation",
            scale="{within_share:.2f}% reproduced under the interval rule against "
                  "{lag1_share:.1f}% under a naive lag",
            recoverable="Not a defect — carry the interval rule alongside the field",
        ),
    )
    f.blocks = [
        Para("The augmented visit layer distributes `delta_height_cm`, "
             "`delta_age_in_days_height`, and the velocity fields derived from "
             "them. These are **not** a lag over successive measurements, and "
             "reading them as one is the error this subsection exists to prevent. "
             "For each measurement the pipeline walks backwards to the most recent "
             "earlier measurement whose age gap meets an age-dependent minimum, "
             "skipping every measurement in between."),
        Table("t-rule", "The interval rule, inferred from the data",
              [C("band", "age band"), C("condition", "condition on current age"),
               C("gap", "minimum interval", ",", " days", align="right")],
              [{"band": b, "condition": c, "gap": g} for b, c, g in RULE]),
        Para("Applying that rule reproduces the distributed fields. Across {n:,} "
             "visits carrying a nonmissing `delta_height_cm`, the recomputed age gap "
             "matches the distributed one on {age_match:,} rows "
             "({age_share:.2f}%), the recomputed delta matches within one hundredth "
             "of a centimetre on {within:,} rows ({within_share:.3f}%), and the "
             "recomputed velocity matches on {vel_share:.2f}% of rows. A naive lag "
             "over successive height-bearing visits matches only {lag1:,} rows "
             "({lag1_share:.1f}%) — which is what makes these fields look "
             "unreproducible when the rule is not known."),
        Figure("fig-delta-gap", "The most common recorded measurement intervals",
               "bar",
               {"categories": [str(g) for g, _ in gap_rows],
                "series": [{"name": "visits", "values": [c for _, c in gap_rows]}],
                "height": 250, "title": "Distributed delta interval, days"},
               alt="Interval lengths cluster at the rule's minimum values."),
        Para("Two residuals are worth recording. {round_only:,} rows differ by "
             "exactly one hundredth of a centimetre, because the pipeline rounds "
             "half to even while this check rounds half away from zero; heights come "
             "from a quarter-inch grid, so exact halfway cases are common rather "
             "than rare. Only {off:,} rows ({off_share:.3f}%) differ by more than "
             "that, and they sit on the duplicate patient-days of 3.1, where which "
             "earlier height was used is ambiguous.", role="method"),
        Para("**Implications for analysis.** The velocity channels are usable as "
             "distributed, which a distributional summary alone could not establish. "
             "What must travel with them is the definition: a velocity here is "
             "computed over an interval of at least 90 to 335 days depending on age, "
             "not between adjacent visits, so it is already smoothed relative to a "
             "visit-to-visit rate and cannot be compared with one. Any "
             "recomputation, and any synthetic series carrying a velocity, must use "
             "the same rule or the two are not on the same scale. The rounding to "
             "two decimals is part of what the distributed values are.",
             role="implication"),
    ]
    return [f]

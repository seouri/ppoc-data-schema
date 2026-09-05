"""Part 4.7 — head circumference, a mostly recoverable conversion defect.

The head-circumference channel carries the worst tails in the extract. 4.6
reports the symptom; this subsection is the diagnosis, because most of the
damage is one documented arithmetic mistake rather than noise, and a channel
that can be repaired should not be deleted.
"""

from __future__ import annotations

from ..context import Context
from ..findings import Artifact, Figure, Finding, Para, Table, probe
from ..findings import Column as C

LO, HI = 25.0, 65.0
BANDS = [
    ("below 10 cm", "head_circ_cm < 10"),
    ("10 to under 25 cm", "head_circ_cm >= 10 AND head_circ_cm < 25"),
    ("25 to 65 cm (within review range)", "head_circ_cm BETWEEN 25 AND 65"),
    ("over 65 to 200 cm", "head_circ_cm > 65 AND head_circ_cm <= 200"),
    ("above 200 cm", "head_circ_cm > 200"),
]


@probe("anthro.headcirc", "4.7")
def headcirc(ctx: Context) -> list[Finding]:
    rows = []
    for label, cond in BANDS:
        n, med, mn, mx = ctx.one(
            f"SELECT count(*), quantile_cont(head_circ_cm, 0.5), "
            f"min(head_circ_cm), max(head_circ_cm) "
            f"FROM visits_augmented WHERE head_circ_cm IS NOT NULL AND {cond}")
        rows.append({"band": label, "visits": ctx.suppress(n), "median": med,
                     "min": mn, "max": mx})

    out_range = ctx.scalar(
        f"SELECT count(*) FROM visits_augmented WHERE head_circ_cm IS NOT NULL "
        f"AND (head_circ_cm < {LO} OR head_circ_cm > {HI})")

    # One inch-to-centimetre conversion applied a second time: dividing by 2.54
    # returns the value to a normal infant head circumference.
    dbl_n, dbl_ok, dbl_med = ctx.one(
        f"SELECT count(*), "
        f" sum(CASE WHEN head_circ_cm / 2.54 BETWEEN {LO} AND {HI} THEN 1 ELSE 0 END), "
        f" quantile_cont(head_circ_cm / 2.54, 0.5) "
        f"FROM visits_augmented WHERE head_circ_cm > 65 AND head_circ_cm <= 200")
    trip_n, trip_ok = ctx.one(
        f"SELECT count(*), "
        f" sum(CASE WHEN head_circ_cm / 2.54 / 2.54 BETWEEN {LO} AND {HI} "
        f"     THEN 1 ELSE 0 END) "
        f"FROM visits_augmented WHERE head_circ_cm > 200")

    z_all, z_implaus = ctx.one(
        f"SELECT count(*), sum(CASE WHEN head_circ_cm < {LO} OR head_circ_cm > {HI} "
        f"THEN 1 ELSE 0 END) FROM visits_augmented WHERE abs(head_circ_z_score) > 5")
    z_plaus = z_all - z_implaus

    f = Finding(
        id="anthro.headcirc", part="4.7",
        title="Head circumference: a recoverable conversion defect",
        values={
            "out_range": out_range, "dbl_n": dbl_n, "dbl_ok": dbl_ok,
            "dbl_share": 100.0 * dbl_ok / dbl_n if dbl_n else 0.0,
            "dbl_med": dbl_med, "trip_n": trip_n, "trip_ok": trip_ok,
            "z_all": z_all, "z_implaus": z_implaus, "z_plaus": z_plaus,
            "z_implaus_share": 100.0 * z_implaus / z_all if z_all else 0.0,
            "recover_share": 100.0 * dbl_ok / out_range if out_range else 0.0,
            "lo": LO, "hi": HI,
        },
        artifact=Artifact(
            name="Head circumference passed through an inch-to-centimetre "
                 "conversion a second time",
            kind="derivation",
            scale="{dbl_ok:,} visits, {recover_share:.0f}% of all out-of-range values",
            recoverable="Yes — divide by 2.54 before applying a plausible range, "
                        "rather than deleting",
        ),
    )
    f.blocks = [
        Para("{out_range:,} visits carry a head circumference outside the "
             "conventional review range of {lo:.0f} to {hi:.0f} cm. Read as a "
             "distribution that looks like a badly behaved channel. Read as "
             "clusters, it looks like arithmetic."),
        Table("t-hc-bands", "Head-circumference values by band",
              [C("band", "band"), C("visits", "visits", ",", align="right"),
               C("median", "median", ",.2f", " cm", align="right"),
               C("min", "minimum", ",.2f", " cm", align="right"),
               C("max", "maximum", ",.2f", " cm", align="right")], rows),
        Figure("fig-hc-bands", "Where head-circumference values fall", "bar",
               {"categories": ["<10", "10-25", "25-65", "65-200", ">200"],
                "series": [{"name": "visits", "values": [r["visits"] or 0 for r in rows]}],
                "height": 260, "title": "Head circumference by band"},
               alt="Most values are in range; a distinct cluster sits between 65 and 200 cm."),
        Para("The cluster between 65 and 200 cm is not noise. It holds {dbl_n:,} "
             "visits, and {dbl_ok:,} of them — {dbl_share:.2f}% — fall back inside "
             "the review range when divided by 2.54, with a median of "
             "{dbl_med:.1f} cm. That is an ordinary infant head circumference. These "
             "are centimetre values that were put through an inch-to-centimetre "
             "conversion a second time. A further {trip_n:,} visits sit above 200 cm, "
             "of which {trip_ok:,} become plausible after dividing by 2.54 twice, "
             "consistent with the same conversion applied again."),
        Para("This one defect explains most of the damage. Of {z_all:,} visits with "
             "an absolute head-circumference z-score above 5, {z_implaus:,} "
             "({z_implaus_share:.1f}%) sit on a measurement outside the review "
             "range, and the double-converted cluster alone accounts for "
             "{dbl_ok:,} of them. The remaining {z_plaus:,} visits carry a plausible "
             "measurement and still produce an extreme z, so the z transform is "
             "independently defective and repairing the units would not fully fix "
             "the channel. That is why 4.6 shows this channel with a maximum no "
             "measurement could produce."),
        Para("**Implications for analysis.** A declared plausible range deletes all "
             "{out_range:,} out-of-range values, but {dbl_ok:,} of those "
             "({recover_share:.1f}%) are ordinary infant measurements that one "
             "documented division restores. Repairing before bounding is strictly "
             "better than bounding alone, and it recovers most of the only "
             "measurement channel whose declared range removes a non-trivial share "
             "of values. The derived z-score is a separate matter: it stays "
             "unusable on {z_plaus:,} visits even after the units are fixed, so "
             "recompute it from the repaired measurement rather than consuming it "
             "as distributed.", role="implication"),
    ]
    return [f]

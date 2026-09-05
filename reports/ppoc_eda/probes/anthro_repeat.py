"""Part 4.5 — repeated measurements, zero growth, and apparent height loss."""

from __future__ import annotations

from ..context import Context
from ..findings import Artifact, Column, Figure, Finding, Para, Table, probe

GRID_CM = 2.54 / 4
GAPS = [(0, 7, "up to 7 days"), (8, 30, "8 to 30 days"), (31, 90, "31 to 90 days"),
        (91, 180, "91 to 180 days"), (181, 365, "181 to 365 days"),
        (366, 1 << 30, "over 365 days")]
MONTH_BANDS = [(18, 24), (24, 30), (30, 36), (36, 42), (48, 60), (60, 84),
               (84, 120), (120, 144), (144, 168), (168, 192), (192, 216)]
SEX_BANDS = [(144, 168), (168, 192), (192, 216)]

VIEW = """
CREATE OR REPLACE TEMP VIEW _pairs AS
WITH one_per_day AS (
    SELECT patient_id, age_in_days, any_value(sex) AS sex, min(height_cm) AS hc
    FROM visits_augmented WHERE height_cm IS NOT NULL
    GROUP BY 1, 2 HAVING count(DISTINCT height_cm) = 1),
framed AS (
    SELECT patient_id, age_in_days, sex, hc,
        lag(hc) OVER w AS hp, lag(age_in_days) OVER w AS ap, lead(hc) OVER w AS hn
    FROM one_per_day WINDOW w AS (PARTITION BY patient_id ORDER BY age_in_days))
SELECT *, hc - hp AS chg, age_in_days - ap AS gap
FROM framed WHERE hp IS NOT NULL
"""


@probe("anthro.repeat", "4.5")
def repeat(ctx: Context) -> list[Finding]:
    ctx.con.execute(VIEW)

    by_gap = []
    for lo, hi, label in GAPS:
        where = f"gap BETWEEN {lo} AND {hi} AND ap >= 730"
        n = ctx.scalar(f"SELECT count(*) FROM _pairs WHERE {where}")
        zero = ctx.scalar(f"SELECT count(*) FROM _pairs WHERE {where} AND chg = 0")
        dec = ctx.scalar(f"SELECT count(*) FROM _pairs WHERE {where} AND chg < 0")
        med = ctx.scalar(f"SELECT quantile_cont(-chg, 0.5) FROM _pairs "
                         f"WHERE {where} AND chg < 0")
        by_gap.append({"gap": label, "pairs": n, "zero": 100.0 * zero / n,
                       "decrease": 100.0 * dec / n, "median": med})

    bands, rates, medians = [], [], []
    for lo, hi in MONTH_BANDS:
        where = (f"gap BETWEEN 181 AND 365 AND ap >= {lo * 30.4375} "
                 f"AND ap < {hi * 30.4375}")
        n = ctx.scalar(f"SELECT count(*) FROM _pairs WHERE {where}")
        if n < 50:
            continue
        dec = ctx.scalar(f"SELECT count(*) FROM _pairs WHERE {where} AND chg < 0")
        bands.append(f"{lo}-{hi}")
        rates.append(round(100.0 * dec / n, 2))
        medians.append({"band": f"{lo}-{hi}", "pairs": n, "rate": 100.0 * dec / n,
                        "median": ctx.scalar(f"SELECT quantile_cont(-chg, 0.5) "
                                             f"FROM _pairs WHERE {where} AND chg < 0"),
                        "mean_change": ctx.scalar(f"SELECT avg(chg) FROM _pairs "
                                                  f"WHERE {where}")})

    sex_bands, f_rates, m_rates, sex_rows = [], [], [], []
    for lo, hi in SEX_BANDS:
        sex_bands.append(f"{lo}-{hi}")
        row = {"band": f"{lo}-{hi}"}
        for sex, bucket in (("F", f_rates), ("M", m_rates)):
            where = (f"gap BETWEEN 181 AND 365 AND ap >= {lo * 30.4375} "
                     f"AND ap < {hi * 30.4375} AND sex = '{sex}'")
            n = ctx.scalar(f"SELECT count(*) FROM _pairs WHERE {where}")
            dec = ctx.scalar(f"SELECT count(*) FROM _pairs WHERE {where} AND chg < 0")
            rate = 100.0 * dec / n if n else 0.0
            bucket.append(round(rate, 2))
            row[f"n_{sex}"] = n
            row[f"rate_{sex}"] = rate
            row[f"mean_{sex}"] = ctx.scalar(f"SELECT avg(chg) FROM _pairs WHERE {where}")
        sex_rows.append(row)

    all_n = ctx.scalar("SELECT count(*) FROM _pairs WHERE gap > 365 AND ap >= 730")
    all_dec = ctx.scalar("SELECT count(*) FROM _pairs WHERE gap > 365 AND ap >= 730 "
                         "AND chg < 0")
    gro_n = ctx.scalar("SELECT count(*) FROM _pairs WHERE gap > 365 "
                       "AND ap BETWEEN 730 AND 3652")
    gro_dec = ctx.scalar("SELECT count(*) FROM _pairs WHERE gap > 365 "
                         "AND ap BETWEEN 730 AND 3652 AND chg < 0")
    p_tot = ctx.scalar("SELECT count(*) FROM _pairs WHERE gap > 365 AND ap >= 730 "
                       "AND chg < -1 AND hn IS NOT NULL")
    p_back = ctx.scalar("SELECT count(*) FROM _pairs WHERE gap > 365 AND ap >= 730 "
                        "AND chg < -1 AND hn IS NOT NULL AND hn >= hp - 0.5")

    f = Finding(
        id="anthro.repeat", part="4.5",
        title="Repeated measurements: zero growth and apparent height loss",
        values={
            "all_n": all_n, "all_dec": all_dec, "all_share": 100.0 * all_dec / all_n,
            "gro_n": gro_n, "gro_dec": gro_dec, "gro_share": 100.0 * gro_dec / gro_n,
            "p_tot": p_tot, "p_back": p_back, "p_persist": p_tot - p_back,
            "back_share": 100.0 * p_back / p_tot,
            "persist_share": 100.0 * (p_tot - p_back) / p_tot,
            "grid_cm": GRID_CM,
        },
        artifact=Artifact(
            name="Apparent height loss from the recording grid on a flat trajectory",
            kind="capture",
            scale="{all_share:.2f}% of pairs over a year apart, falling to "
                  "{gro_share:.3f}% at ages 2 to 10",
            recoverable="Not a defect — do not filter it as an outlier",
        ),
    )
    f.blocks = [
        Para("Children do not shrink, so a recorded decrease is recording behaviour "
             "rather than physiology. That much is easy. What matters is that the "
             "behaviour is not one thing, and the interval between measurements "
             "separates the mechanisms."),
        Table("t-gap", "Repeat height pairs at age 2 or later, by interval",
              [Column("gap", "interval"), Column("pairs", "pairs", ",", align="right"),
               Column("zero", "exactly zero change", ".2f", "%", align="right"),
               Column("decrease", "any decrease", ".2f", "%", align="right"),
               Column("median", "median loss", ".2f", " cm", align="right")], by_gap),
        Para("At short intervals a child genuinely has not grown a measurable amount "
             "and the quarter-inch grid absorbs the rest. At long intervals both "
             "effects should vanish, and they do not entirely. The residue is small "
             "and its median size is about one grid step of {grid_cm:.3f} cm, which "
             "is the first clue that it is rounding rather than error."),
        Para("Holding the interval fixed and varying age identifies the mechanisms "
             "directly."),
        Figure("fig-loss-age", "Apparent height loss by age, over 181-365 day intervals",
               "line",
               {"x": bands, "series": [{"name": "any decrease", "values": rates}],
                "suffix": "%", "height": 280, "title": "Apparent loss by age"},
               alt="A curve with a spike near 30-36 months and a steep adolescent rise."),
        Table("t-loss-age", "Apparent loss by age at the earlier measurement",
              [Column("band", "age band (months)"),
               Column("pairs", "pairs", ",", align="right"),
               Column("rate", "any decrease", ".2f", "%", align="right"),
               Column("median", "median loss", ".2f", " cm", align="right"),
               Column("mean_change", "mean change", ".2f", " cm", align="right")],
              medians),
        Para("Two separate excesses, with different signatures. The first is a narrow "
             "spike at 30 to 36 months carrying a median loss of over a centimetre "
             "— the age at which recumbent length gives way to standing height, and "
             "a standing height genuinely is shorter than a recumbent length for the "
             "same child. It is a change of measurement protocol recorded in a field "
             "that does not name the protocol."),
        Figure("fig-loss-sex", "Apparent loss in adolescence, by sex", "grouped_bar",
               {"categories": sex_bands,
                "series": [{"name": "female", "values": f_rates},
                           {"name": "male", "values": m_rates}],
                "suffix": "%", "height": 280, "title": "Adolescent apparent loss by sex"},
               alt="Girls reach high apparent-loss rates about two years before boys."),
        Table("t-loss-sex", "Adolescent bands split by recorded sex",
              [Column("band", "age band (months)"),
               Column("n_F", "female pairs", ",", align="right"),
               Column("rate_F", "female decrease", ".2f", "%", align="right"),
               Column("mean_F", "female mean change", ".2f", " cm", align="right"),
               Column("n_M", "male pairs", ",", align="right"),
               Column("rate_M", "male decrease", ".2f", "%", align="right"),
               Column("mean_M", "male mean change", ".2f", " cm", align="right")],
              sex_rows),
        Para("The second excess is the adolescent rise, and the sex split identifies "
             "it. Girls reach the high rates about two years before boys, in the same "
             "order as growth cessation, while the mean change over the same interval "
             "falls towards zero. Once annual growth drops below the recording grid, "
             "re-measuring a child who has stopped growing returns a lower value "
             "about as often as a higher one. Restricting to ages 2 to 10, where "
             "growth is unambiguously ongoing, collapses the long-interval decrease "
             "rate from {all_share:.3f}% to {gro_share:.3f}% — {gro_dec:,} pairs of "
             "{gro_n:,}."),
        Para("What survives both explanations divides again. Of {p_tot:,} decreases "
             "over a centimetre across more than a year that are followed by a "
             "further measurement, {p_back:,} ({back_share:.1f}%) are followed by a "
             "value back at or above the earlier level, and {p_persist:,} "
             "({persist_share:.1f}%) by one that stays below it. In the first the low "
             "value is the suspect; in the second it is corroborated and the earlier, "
             "higher measurement is the candidate error."),
        Para("**Implications for analysis.** Most apparent shrinkage here is not "
             "error and should not be filtered as an outlier: it is the recording "
             "grid acting on a flattened trajectory, plus a protocol change at two "
             "to three years. A synthetic or smoothed trajectory that lacks both "
             "will not resemble this panel. Where a decrease does need adjudication, "
             "{persist_share:.0f}% of long-interval losses persist into the next "
             "measurement, so a rule that always discards the lower value is wrong "
             "on that share.", role="implication"),
    ]
    return [f]

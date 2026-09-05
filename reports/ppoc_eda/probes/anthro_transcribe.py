"""Part 4.4 — transcription-error signatures in the typed anthropometric fields.

Height and weight arrive as typed imperial values, so a transposed pair of
digits, a dropped digit, a misplaced decimal point, or a value keyed in the
wrong unit is an error in `height_in` or `weight_oz`. Each mechanism is scored
against a deviation-preserving permutation null, because the mechanisms differ
enormously in how much freedom they have to fit an arbitrary number and an
unscored digit search always finds hits.
"""

from __future__ import annotations

import functools
import random
from collections import Counter

from ..context import Context
from ..findings import Artifact, Figure, Finding, Para, Table, probe
from ..findings import Column as C

HEIGHT_DEV, HEIGHT_TOL = 3.0, 1.0
WEIGHT_DEV, WEIGHT_TOL = 0.5, 0.05
NULL_REPS, NULL_SEED = 20, 20260905
H_LO, H_HI, W_LO, W_HI, MAX_SPAN = 15.0, 80.0, 48.0, 6400.0, 1460
SHIFTS = (0.01, 0.1, 10.0, 100.0)
SAMPLE = 200_000

FEET = "height recorded in whole feet"
CAL = "one digit wrong (calibration class)"
SWAP = "adjacent digit transposition"
OMIT = "one digit omitted"
SHIFT = "decimal point misplaced"
H_SCALES = [("centimetre value in the inch field", 1.0 / 2.54),
            ("inch value where a centimetre is expected", 2.54)]
W_SCALES = [("pound value in the ounce field", 16.0),
            ("ounce value where a pound is expected", 1.0 / 16.0),
            ("kilogram value in the ounce field", 35.27396),
            ("gram value in the ounce field", 0.03527396)]


def _canon(x: float) -> str:
    s = f"{x:.6f}".rstrip("0").rstrip(".")
    return s or "0"


def _val(s: str) -> float | None:
    if s.count(".") > 1 or s in ("", "."):
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v > 0 else None


@functools.cache
def _edits(s: str) -> tuple[frozenset, frozenset, frozenset]:
    """Transposition, insertion, and substitution candidates for a typed value.

    Transposition swaps two adjacent *digits*: swapping a digit with the decimal
    point is a decimal-place error and is carried by its own class. Insertion is
    the candidate set for "the recorded value is the truth with one digit
    dropped". Substitution is the calibration class — the most permissive
    hypothesis available, kept to show where the method saturates.
    """
    self_val, swap, ins, sub = _val(s), set(), set(), set()
    for i in range(len(s) - 1):
        if s[i] != s[i + 1] and s[i].isdigit() and s[i + 1].isdigit():
            v = _val(s[:i] + s[i + 1] + s[i] + s[i + 2:])
            if v is not None:
                swap.add(v)
    for p in range(len(s) + 1):
        for c in "0123456789":
            v = _val(s[:p] + c + s[p:])
            if v is not None:
                ins.add(v)
    for i, ch in enumerate(s):
        if ch.isdigit():
            for c in "0123456789":
                if c != ch:
                    v = _val(s[:i] + c + s[i + 1:])
                    if v is not None:
                        sub.add(v)
    swap.discard(self_val)
    ins.discard(self_val)
    return frozenset(swap), frozenset(ins), frozenset(sub)


def _mechanisms(rec: float, exp: float, tol: float, scales, feet: bool) -> set[str]:
    found = set()
    if feet and rec == int(rec) and 1 <= rec <= 6 and int(exp // 12) == int(rec):
        found.add(FEET)
    for name, factor in scales:
        if abs(rec * factor - exp) <= tol:
            found.add(name)
    for factor in SHIFTS:
        if abs(rec * factor - exp) <= tol:
            found.add(SHIFT)
    swap, ins, sub = _edits(_canon(rec))
    if any(abs(c - exp) <= tol for c in swap):
        found.add(SWAP)
    if any(abs(c - exp) <= tol for c in ins):
        found.add(OMIT)
    if any(abs(c - exp) <= tol for c in sub):
        found.add(CAL)
    return found


def _score(rows, tol_of, scales, feet, order):
    pool: dict[int, list[float]] = {}
    for value, expected, age in rows:
        pool.setdefault(min(age // 365, 17), []).append(expected - value)
    for deviations in pool.values():
        deviations.sort()
    rng = random.Random(NULL_SEED)
    obs, null, excl = Counter(), Counter(), Counter()
    for value, expected, age in rows:
        hits = _mechanisms(value, expected, tol_of(expected), scales, feet)
        obs.update(hits)
        excl[next((n for n in order if n in hits), "no mechanism reconciles it")] += 1
    for _ in range(NULL_REPS):
        for value, expected, age in rows:
            shuffled = value + rng.choice(pool[min(age // 365, 17)])
            null.update(_mechanisms(value, shuffled, tol_of(shuffled), scales, feet))
    return {"n": len(rows), "obs": obs,
            "null": {k: v / NULL_REPS for k, v in null.items()}, "excl": excl}


def _rows(scored: dict, order: list[str]) -> list[dict]:
    n = scored["n"]
    out = []
    for name in order:
        o = scored["obs"].get(name, 0)
        nu = scored["null"].get(name, 0.0)
        out.append({"mechanism": name, "obs": o, "share": 100.0 * o / n,
                    "null": 100.0 * nu / n,
                    "ratio": (o / nu) if nu >= 0.2 else None})
    return out


def _series(ctx: Context, col: str, lo: float, hi: float, extra: str) -> None:
    ctx.con.execute(f"""
        CREATE OR REPLACE TEMP VIEW _ser AS
        WITH one_per_day AS (
            SELECT patient_id, age_in_days, min({col}) AS v FROM visits_augmented
            WHERE {col} IS NOT NULL GROUP BY 1, 2
            HAVING count(DISTINCT {col}) = 1),
        framed AS (
            SELECT patient_id, age_in_days, v,
                lag(v) OVER w AS vp, lag(age_in_days) OVER w AS ap,
                lead(v) OVER w AS vn, lead(age_in_days) OVER w AS an
            FROM one_per_day WINDOW w AS (PARTITION BY patient_id ORDER BY age_in_days))
        SELECT age_in_days, v,
               vp + (vn - vp) * (age_in_days - ap)::DOUBLE / nullif(an - ap, 0) AS expect
        FROM framed
        WHERE vp IS NOT NULL AND vn IS NOT NULL
          AND vp BETWEEN {lo} AND {hi} AND vn BETWEEN {lo} AND {hi}
          AND an - ap <= {MAX_SPAN} {extra}""")


def _sensitivity(ctx: Context, gate: float | None, absolute: float | None) -> tuple:
    vals = ctx.q(f"SELECT v FROM _ser WHERE expect > 0 "
                 f"USING SAMPLE reservoir({SAMPLE} ROWS) REPEATABLE (42)")
    total = caught = 0
    for (value,) in vals:
        for cand in _edits(_canon(value))[0]:
            total += 1
            moved = abs(cand - value) / value if gate else abs(cand - value)
            caught += moved > (gate if gate else absolute)
    return len(vals), total, caught


@probe("anthro.transcribe", "4.4")
def transcribe(ctx: Context) -> list[Finding]:
    h_order = [FEET, *[n for n, _ in H_SCALES], SHIFT, SWAP, OMIT, CAL]
    w_order = [*[n for n, _ in W_SCALES], SHIFT, SWAP, OMIT, CAL]

    _series(ctx, "height_in", H_LO, H_HI, "AND vn >= vp - 0.5")
    h_rows = ctx.q(f"SELECT v, expect, age_in_days FROM _ser WHERE expect > 0 "
                   f"AND abs(v - expect) > {HEIGHT_DEV} ORDER BY v, expect, age_in_days")
    h_sens = _sensitivity(ctx, None, HEIGHT_DEV)
    h_multi = [r for r in h_rows if len(_canon(r[0]).split(".")[0]) > 1]
    h_multi_hit = sum(any(abs(c - e) <= HEIGHT_TOL for c in _edits(_canon(v))[1])
                      for v, e, _ in h_multi)
    height = _score(h_rows, lambda e: HEIGHT_TOL, H_SCALES, True, h_order)

    _series(ctx, "weight_oz", W_LO, W_HI, "")
    w_rows = ctx.q(f"SELECT v, expect, age_in_days FROM _ser WHERE expect > 0 "
                   f"AND abs(v - expect) / expect > {WEIGHT_DEV} "
                   f"ORDER BY v, expect, age_in_days")
    w_sens = _sensitivity(ctx, WEIGHT_DEV, None)
    weight = _score(w_rows, lambda e: max(WEIGHT_TOL * e, 2.0), W_SCALES, False, w_order)

    feet_n, feet_cm = ctx.one(
        "SELECT count(*), count(height_cm) FROM visits_augmented "
        "WHERE height_in IN (1, 2, 3, 4, 5, 6)")
    feet_age = ctx.scalar("SELECT quantile_cont(age_in_years, 0.5) FROM visits_augmented "
                          "WHERE height_in IN (2, 3, 4, 5, 6)")
    cm_n, cm_grid, cm_cm, cm_age = ctx.one(
        "SELECT count(*), sum(CASE WHEN height_in * 4 = floor(height_in * 4) "
        "THEN 1 ELSE 0 END), count(height_cm), quantile_cont(age_in_years, 0.5) "
        "FROM visits_augmented WHERE height_in BETWEEN 90 AND 115")
    grid_all, grid_hit = ctx.one(
        "SELECT count(*), sum(CASE WHEN height_in * 4 = floor(height_in * 4) "
        "THEN 1 ELSE 0 END) FROM visits_augmented WHERE height_in IS NOT NULL")

    def acct(g):
        cal = g["excl"].get(CAL, 0)
        none = g["excl"].get("no mechanism reconciles it", 0)
        return {"named": g["n"] - cal - none, "cal": cal, "none": none}

    h_acct, w_acct = acct(height), acct(weight)
    h_rows_t, w_rows_t = _rows(height, h_order), _rows(weight, w_order)

    f = Finding(
        id="anthro.transcribe", part="4.4",
        title="Transcription-error signatures in the typed fields",
        values={
            "h_n": height["n"], "w_n": weight["n"],
            "feet_n": feet_n, "feet_live": feet_n - feet_cm, "feet_age": feet_age,
            "cm_n": cm_n, "cm_live": cm_n - cm_cm, "cm_age": cm_age,
            "cm_grid": 100.0 * cm_grid / cm_n, "grid_base": 100.0 * grid_hit / grid_all,
            "h_sens": 100.0 * h_sens[2] / h_sens[1], "h_sens_n": h_sens[0],
            "w_sens": 100.0 * w_sens[2] / w_sens[1], "w_sens_n": w_sens[0],
            "h_multi": len(h_multi), "h_multi_hit": h_multi_hit,
            "h_omit": height["obs"].get(OMIT, 0),
            "h_omit_share": 100.0 * height["obs"].get(OMIT, 0) / height["n"],
            "w_shift": weight["obs"].get(SHIFT, 0),
            "w_shift_ratio": weight["obs"].get(SHIFT, 0) / max(weight["null"].get(SHIFT, 1e-9), 1e-9),
            "reps": NULL_REPS, "hdev": HEIGHT_DEV, "wdev": WEIGHT_DEV * 100,
            "h_named": h_acct["named"], "h_cal": h_acct["cal"], "h_none": h_acct["none"],
            "w_named": w_acct["named"], "w_cal": w_acct["cal"], "w_none": w_acct["none"],
        },
        artifact=Artifact(
            name="Wrong-unit and decimal-place entry in the typed measurement fields",
            kind="capture",
            scale="{feet_n:,} whole-foot heights, {cm_n:,} centimetre values in the "
                  "inch field, and a weight decimal artifact enriched "
                  "{w_shift_ratio:.0f}-fold",
            recoverable="Yes — bound and repair the raw imperial columns before "
                        "converting",
        ),
    )
    f.blocks = [
        Para("**Method.** Each measurement is anchored by linear interpolation "
             "between the same child's previous and next measurement. Both "
             "neighbours must themselves be plausible and span no more than four "
             "years, so a bad neighbour cannot manufacture an anomaly. A height is "
             "anomalous more than {hdev:.0f} inches from that anchor, a weight more "
             "than {wdev:.0f}% from it. A mechanism *reconciles* an anomaly when "
             "applying it to the recorded value lands back at the anchor.",
             role="method"),
        Para("**The null.** Each anomaly's anchor is replaced by the recorded value "
             "plus a deviation drawn from another anomaly in the same year-of-age "
             "band, {reps} times. That preserves the distribution of deviations "
             "exactly and destroys only the arithmetic relationship between the "
             "recorded digits and the anchor, which is the thing under test. A "
             "mechanism that reconciles anomalies no more often than it reconciles "
             "these scrambled pairs has no evidence behind it, however many hits it "
             "returns.", role="method"),
        Para("**Height.** {h_n:,} anomalies in the testable interior. Mechanisms are "
             "tested one at a time and are not mutually exclusive, so the rows do "
             "not sum to the total."),
        Table("t-hmech", "Height: mechanisms against the null",
              [C("mechanism", "mechanism"), C("obs", "reconciled", ",", align="right"),
               C("share", "share", ".2f", "%", align="right"),
               C("null", "null", ".2f", "%", align="right"),
               C("ratio", "ratio", ".1f", "x", align="right")], h_rows_t),
        Figure("fig-mech-h", "Height: observed against null, by mechanism",
               "grouped_bar",
               {"categories": [r["mechanism"].split(" (")[0][:22] for r in h_rows_t],
                "series": [{"name": "observed", "values": [r["share"] for r in h_rows_t]},
                           {"name": "null", "values": [r["null"] for r in h_rows_t]}],
                "suffix": "%", "height": 300, "title": "Height mechanism enrichment"},
               alt="Whole-feet entry stands far above its null; transposition does not."),
        Para("Adjacent digit transposition — the classic keying error, and the one "
             "most often assumed — reconciles fewer height anomalies than chance "
             "alone. The unit error is real and it is directional: a centimetre "
             "value in the inch field is enriched, while the arithmetically opposite "
             "reading sits at or below the null. That asymmetry is what a one-way "
             "data-entry confusion looks like; a spurious mechanism would be "
             "symmetric."),
        Para("The dropped-digit row does not survive inspection, and it is worth "
             "showing why. Inserting a digit into a two-digit inch value always "
             "produces a three-digit one, which is never a plausible height, so the "
             "class can only fire on a value with a single-digit integer part. Among "
             "the {h_multi:,} height anomalies whose integer part has two or more "
             "digits it reconciles {h_multi_hit:,}. Its entire {h_omit_share:.2f}% "
             "is the whole-foot family reached by another route."),
        Para("Two clusters are visible without any anchor at all. {feet_n:,} visits "
             "record a `height_in` of 1 to 6 as an exact integer, median age "
             "{feet_age:.1f} years — a height of 3 or 4 for a child three or four "
             "feet tall. And {cm_n:,} record a `height_in` between 90 and 115, which "
             "read as inches is implausible and read as centimetres is an ordinary "
             "preschool stature at a median age of {cm_age:.1f} years. The recording "
             "grid decides between the two readings: {cm_grid:.1f}% of that cluster "
             "falls on the quarter-inch grid against {grid_base:.1f}% of all heights, "
             "so those values never passed through the inch-typing workflow."),
        Para("**Weight.** {w_n:,} anomalies in the testable interior."),
        Table("t-wmech", "Weight: mechanisms against the null",
              [C("mechanism", "mechanism"), C("obs", "reconciled", ",", align="right"),
               C("share", "share", ".2f", "%", align="right"),
               C("null", "null", ".2f", "%", align="right"),
               C("ratio", "ratio", ".1f", "x", align="right")], w_rows_t),
        Para("Transposition is again below chance, so neither channel shows evidence "
             "of digit swapping. A misplaced decimal point, which the height channel "
             "does not show at all, is the dominant weight artifact: {w_shift:,} "
             "anomalies at {w_shift_ratio:.0f} times the null rate, the strongest "
             "enrichment measured anywhere in this report. An ounce value has more "
             "digits than an inch value and no natural decimal point, so a factor of "
             "ten is both easy to key and hard to notice."),
        Para("The calibration row is why the null is not optional. Allowing any "
             "single digit to be wrong reconciles about half of all height anomalies "
             "and reconciles almost exactly as many randomly paired values. Reported "
             "without a null it would look like the largest finding here."),
        Para("**How strong is the transposition negative?** Only as strong as the "
             "share of transpositions the anomaly gate could have caught. Applying "
             "every adjacent digit swap to a sample of measurements in the testable "
             "interior gives that share directly: {h_sens:.1f}% of height swaps "
             "would displace a value past the gate, against {w_sens:.1f}% of weight "
             "swaps. The height negative is well powered; the weight negative rules "
             "out only large swaps, since a four-digit ounce value can absorb a swap "
             "without moving far.", role="method"),
        Table("t-acct", "What the mechanisms account for",
              [C("channel", "channel"), C("n", "anomalies", ",", align="right"),
               C("named", "a named mechanism fits", ",", align="right"),
               C("cal", "only the calibration class", ",", align="right"),
               C("none", "nothing fits", ",", align="right")],
              [{"channel": "height", "n": height["n"], **h_acct},
               {"channel": "weight", "n": weight["n"], **w_acct}]),
        Para("**Implications for analysis.** Digit transposition can be dropped from "
             "the checklist for this extract at the magnitude that displaces a "
             "measurement from its own trajectory; for weight the same test is only "
             "about a third sensitive, so a small swap is not ruled out. Unit "
             "confusion and decimal placement do matter, and both are cheap to "
             "screen because both produce values implausible on their face. Bound "
             "`height_in` and `weight_oz` before any conversion, and check the "
             "recording grid rather than the value alone — the grid separates a tall "
             "adolescent from a centimetre in the wrong field where magnitude "
             "cannot. Note also that {feet_live:,} of the whole-foot entries and "
             "{cm_live:,} of the centimetre cluster already carry a null "
             "`height_cm`: the derived layer's own bound removes them as a side "
             "effect, so anyone reading the derived channels is protected and anyone "
             "reading the raw ones is not.", role="implication"),
    ]
    return [f]

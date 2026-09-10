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

#: DEV gates what counts as an anomaly; TOL is how close a mechanism has to land
#: to count as reconciling one. TOL is reported in the section: at a window of an
#: inch, "this is 3 feet" and "this is 33.5 with the leading digit dropped" land
#: in the same place, which is why those two classes overlap rather than
#: partition.
HEIGHT_DEV, HEIGHT_TOL = 3.0, 1.0
WEIGHT_DEV, WEIGHT_TOL, W_TOL_FLOOR = 0.5, 0.05, 2.0
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


def _score(rows, tol_of, scales, feet):
    pool: dict[int, list[float]] = {}
    for value, expected, age in rows:
        pool.setdefault(min(age // 365, 17), []).append(expected - value)
    for deviations in pool.values():
        deviations.sort()
    rng = random.Random(NULL_SEED)
    obs, null, per_row, null_rows = Counter(), Counter(), [], []
    for value, expected, age in rows:
        hits = _mechanisms(value, expected, tol_of(expected), scales, feet)
        obs.update(hits)
        per_row.append(hits)
    for _ in range(NULL_REPS):
        for value, expected, age in rows:
            shuffled = value + rng.choice(pool[min(age // 365, 17)])
            hits = _mechanisms(value, shuffled, tol_of(shuffled), scales, feet)
            null.update(hits)
            null_rows.append(hits)
    return {"n": len(rows), "obs": obs, "hits": per_row, "null_hits": null_rows,
            "null": {k: v / NULL_REPS for k, v in null.items()}}


def _credible(scored: dict, order: list[str]) -> list[str]:
    """The named mechanisms that reconcile more than chance does.

    A class at or below its null has no evidence behind it, so counting its hits
    as explanations would contradict the tables above. The calibration class is
    excluded here because it is reported in its own column.
    """
    return [n for n in order if n != CAL
            and scored["obs"].get(n, 0) > scored["null"].get(n, 0.0)]


def _account(scored: dict, credible: list[str]) -> dict:
    """Split the anomalies three ways: enriched class, calibration only, neither."""
    keep, out = set(credible), {"named": 0, "cal": 0, "none": 0}
    for hits in scored["hits"]:
        if hits & keep:
            out["named"] += 1
        elif CAL in hits:
            out["cal"] += 1
        else:
            out["none"] += 1
    return out


def _alone(scored: dict, name: str, credible: list[str]) -> tuple[int, float]:
    """Anomalies this class reconciles that no better-evidenced class claims.

    Returned with its own null, not the whole class's: the overlap with a
    stronger class is itself something the scrambled pairs reproduce, so
    subtracting it from the observed count and not from the null would flatter
    whatever is left.
    """
    others = set(credible) - {name}
    obs = sum(1 for hits in scored["hits"] if name in hits and not hits & others)
    null = sum(1 for hits in scored["null_hits"]
               if name in hits and not hits & others) / NULL_REPS
    return obs, null


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
    height = _score(h_rows, lambda e: HEIGHT_TOL, H_SCALES, True)

    _series(ctx, "weight_oz", W_LO, W_HI, "")
    w_rows = ctx.q(f"SELECT v, expect, age_in_days FROM _ser WHERE expect > 0 "
                   f"AND abs(v - expect) / expect > {WEIGHT_DEV} "
                   f"ORDER BY v, expect, age_in_days")
    w_sens = _sensitivity(ctx, WEIGHT_DEV, None)
    weight = _score(w_rows, lambda e: max(WEIGHT_TOL * e, W_TOL_FLOOR), W_SCALES,
                    False)

    feet_n, feet_cm = ctx.one(
        "SELECT count(*), count(height_cm) FROM visits_augmented "
        "WHERE height_in IN (1, 2, 3, 4, 5, 6)")
    # Count and median over the same rows. They used to differ — the median
    # excluded a bare 1 — which made the sentence describe two populations as
    # one. No visit records a 1, so aligning them changes no number and removes
    # the way this could silently become wrong.
    feet_age_n, feet_age = ctx.one(
        "SELECT count(*), quantile_cont(age_in_years, 0.5) FROM visits_augmented "
        "WHERE height_in IN (1, 2, 3, 4, 5, 6)")
    if feet_age_n != feet_n:
        raise ValueError(
            f"the whole-foot cluster counts {feet_n:,} visits but its median age is "
            f"taken over {feet_age_n:,}; one sentence would be describing two "
            f"populations")
    cm_n, cm_grid, cm_cm, cm_age = ctx.one(
        "SELECT count(*), sum(CASE WHEN height_in * 4 = floor(height_in * 4) "
        "THEN 1 ELSE 0 END), count(height_cm), quantile_cont(age_in_years, 0.5) "
        "FROM visits_augmented WHERE height_in BETWEEN 90 AND 115")
    grid_all, grid_hit = ctx.one(
        "SELECT count(*), sum(CASE WHEN height_in * 4 = floor(height_in * 4) "
        "THEN 1 ELSE 0 END) FROM visits_augmented WHERE height_in IS NOT NULL")

    h_cred, w_cred = _credible(height, h_order), _credible(weight, w_order)
    h_acct, w_acct = _account(height, h_cred), _account(weight, w_cred)
    h_alone, w_alone = _alone(height, OMIT, h_cred), _alone(weight, OMIT, w_cred)
    h_rejected = [n for n in h_order if n != CAL and n not in h_cred]
    w_rejected = [n for n in w_order if n != CAL and n not in w_cred]
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
            "h_omit_feet": sum(1 for hits in height["hits"]
                               if OMIT in hits and FEET in hits),
            "h_omit_alone": h_alone[0], "h_omit_null": h_alone[1],
            "h_omit_alone_ratio": h_alone[0] / max(h_alone[1], 1e-9),
            "w_omit": weight["obs"].get(OMIT, 0),
            "w_omit_alone": w_alone[0], "w_omit_null": w_alone[1],
            "w_omit_alone_ratio": w_alone[0] / max(w_alone[1], 1e-9),
            "htol": HEIGHT_TOL, "wtol": WEIGHT_TOL * 100, "wtol_floor": W_TOL_FLOOR,
            "h_cal_share": 100.0 * height["obs"].get(CAL, 0) / height["n"],
            "h_cal_null": 100.0 * height["null"].get(CAL, 0.0) / height["n"],
            "w_cal_share": 100.0 * weight["obs"].get(CAL, 0) / weight["n"],
            "w_cal_null": 100.0 * weight["null"].get(CAL, 0.0) / weight["n"],
            "h_rejected": ", ".join(h_rejected), "w_rejected": ", ".join(w_rejected),
            "clusters_all": (" — every value in both clusters"
                             if feet_cm == 0 and cm_cm == 0 else ""),
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
             "applying it to the recorded value lands back at the anchor — within "
             "{htol:.0f} inch for height, and within the larger of {wtol:.0f}% and "
             "{wtol_floor:.0f} ounces for weight. That window is wide, deliberately, "
             "because a transcription error need not be exact; the cost is that two "
             "mechanisms can land in the same place, and the dropped-digit row below "
             "is where that happens.", role="method"),
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
        Para("The dropped-digit row is mostly borrowed from the row above it, and "
             "it is worth showing why. Inserting a digit into a two-digit inch value "
             "always produces a three-digit one, which is never a plausible height, "
             "so the class can only fire on a value with a single-digit integer "
             "part. Among the {h_multi:,} height anomalies whose integer part has "
             "two or more digits it reconciles {h_multi_hit:,}. That leaves the short "
             "values, and there the whole-foot class has already claimed most of "
             "them: of the {h_omit:,} anomalies this class reconciles, "
             "{h_omit_feet:,} are whole-foot entries too, which the one-inch window "
             "above makes almost unavoidable. What is left is {h_omit_alone:,} "
             "anomalies against a null of {h_omit_null:.0f} — still enriched "
             "{h_omit_alone_ratio:.1f} times, so a dropped digit is real on this "
             "channel, but it accounts for {h_omit_alone:,} of the {h_n:,} anomalies "
             "rather than the {h_omit:,} the row reads as. An overlapping class is "
             "not a spurious one; it is one whose headline belongs to its neighbour."),
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
             "enrichment against a null anywhere in this report. An ounce value has more "
             "digits than an inch value and no natural decimal point, so a factor of "
             "ten is both easy to key and hard to notice."),
        Para("The dropped-digit row does **not** reduce the same way on this "
             "channel, and the height argument does not transfer: an ounce value has "
             "three or four digits, so inserting one can still land on a plausible "
             "weight. Of the {w_omit:,} weight anomalies the class reconciles, "
             "{w_omit_alone:,} are claimed by no better-evidenced mechanism, against "
             "{w_omit_null:.0f} expected under the null — a ratio of "
             "{w_omit_alone_ratio:.1f}. The class is weaker here than the "
             "{w_omit:,} in the table suggests, and weaker than the height residual, "
             "but it is not disposed of by the argument that reduces the height row."),
        Para("The calibration row is why the null is not optional, and the two "
             "channels show why in opposite directions. Allowing any single digit to "
             "be wrong reconciles {h_cal_share:.0f}% of height anomalies against a "
             "{h_cal_null:.0f}% null, and {w_cal_share:.0f}% of weight anomalies "
             "against {w_cal_null:.0f}% — barely above chance on one channel and "
             "well below it on the other. Reported without a null the height row "
             "would look like the largest finding here."),
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
               C("named", "an enriched mechanism fits", ",", align="right"),
               C("cal", "only the calibration class", ",", align="right"),
               C("none", "nothing beyond chance fits", ",", align="right")],
              [{"channel": "height", "n": height["n"], **h_acct},
               {"channel": "weight", "n": weight["n"], **w_acct}],
              note="Only classes reconciling more than their own null count as "
                   "explanations here, so the first column does not contradict the "
                   "tables above. Excluded on that test: {h_rejected} for height, "
                   "and {w_rejected} for weight. A row in the last column may still "
                   "have had one of those fire on it; a class at chance explains "
                   "nothing it happens to fit."),
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
             "`height_cm`{clusters_all}: the derived layer's own bound removes them "
             "as a side effect, so anyone reading the derived channels is protected "
             "and anyone reading the raw ones is not.", role="implication"),
    ]
    return [f]

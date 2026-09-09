"""Part 5.14 — an exhaustive screen for fields that encode the label.

5.11 and 5.13 test a hand-curated list of clinically obvious candidates. That is
a hypothesis test rather than a search: it can confirm that growth hormone leaks
and it cannot discover the leak nobody thought to name. This probe screens every
value of five categorical fields against the label, reports the top of the lift
distribution instead of a chosen subset, and repeats the screen under the
alternative index event 5.11 recommends — because the shortcut set is a property
of the label, not of the extract.
"""

from __future__ import annotations

from ..context import SUPPRESS_BELOW, Context
from ..findings import Artifact, Finding, Para, Table, probe
from ..findings import Column as C
from .growth import ICD_LOOKUP, PANEL_SPLIT_YEARS
from .icd import patient_codes
from .joint import WORKUP_INDEX

#: Patients who must carry a value before it is screened. Well above the
#: suppression floor: a lift computed on a dozen patients is noise, and the
#: point of the screen is the shape of the distribution rather than its tail.
SUPPORT = 200

#: Rows shown per field. The screen looks at everything; the table shows the top.
TOP_N = 5

#: Every categorical field a feature build would draw on except the diagnosis
#: code, with the query that yields one row per patient and value. The code is
#: screened separately because the tracked panel has to be split out of it.
#: Free-text names are screened as delivered rather than normalised, since that
#: is how a join would see them.
SOURCES = [
    ("medication", "`medications.med_simple_generic_name`",
     "SELECT patient_id, med_simple_generic_name AS value FROM medications"),
    ("lab procedure", "`labs.lab_procedure_name`",
     "SELECT patient_id, lab_procedure_name AS value FROM labs"),
    ("referral specialty", "`referrals.requested_specialty`",
     "SELECT patient_id, requested_specialty AS value FROM referrals"),
    ("encounter type", "`visits.encounter_type`",
     "SELECT patient_id, encounter_type AS value FROM visits"),
    ("medication record type", "`medications.med_record_type`",
     "SELECT patient_id, med_record_type AS value FROM medications"),
    ("lab result flag", "`labs.result_flag`",
     "SELECT patient_id, result_flag AS value FROM labs"),
]

#: Candidates carried forward from the curated sections, plus the two the screen
#: adds, scored against both labels. Fixed rather than data-driven so the
#: comparison is the same one 5.11 and 5.13 make.
def candidates(pc: str) -> list[tuple[str, str]]:
    return [
        ("endocrinology referral (5.13)",
         ("SELECT patient_id FROM referrals "
          "WHERE lower(requested_specialty) LIKE '%endocrin%'")),
        ("growth hormone prescription (5.11)",
         ("SELECT patient_id FROM medications "
          "WHERE lower(med_simple_generic_name) LIKE '%somatropin%'")),
        ("stunting flag ever set (5.10)",
         "SELECT patient_id FROM patients_augmented WHERE ever_stunting_flag = 1"),
        ("failure to thrive or short stature in the child, R62.5x",
         f"SELECT patient_id FROM {pc} WHERE starts_with(code, 'R62.5')"),
        ("pediatric BMI-percentile code, Z68.5x",
         f"SELECT patient_id FROM {pc} WHERE starts_with(code, 'Z68.5')"),
        ("any encounter converted from the legacy system",
         "SELECT patient_id FROM visits WHERE orig_enc_source_Epic_yn <> 'Y'"),
        ("no converted encounter: recorded natively throughout",
         ("SELECT patient_id FROM visits GROUP BY 1 HAVING "
          "max(CASE WHEN orig_enc_source_Epic_yn <> 'Y' THEN 1 ELSE 0 END) = 0")),
    ]

#: 5.11 matches this substring across the procedure name and the result
#: component and reports no signal. The screen ranks procedure names, which is a
#: different unit; both numbers are computed here so the gap is measured rather
#: than argued.
DILUTED = "%ALKALINE PHOS%"

LABEL_TABLE = "_shortcut_label"

#: Substrings that put a record inside the workup index itself. A value matching
#: one of these scores the index's maximum against it by construction rather
#: than by discrimination, so its workup lift is withheld the same way an
#: unbacked one is. `%IGF%` catches the binding protein as well as IGF-1, which
#: is a property of the index definition in 5.11 and not of this screen.
INDEX_TERMS = ("SOMATROPIN", "IGF", "GROWTH HORMONE")


def _perinatal_share(ctx: Context) -> dict:
    """How much of the label's positive class is the earlier-diagnosed stratum.

    Both screens score against the pooled `growth_dx_flag`, so whatever that
    class is mostly made of is what a lift or a rank statistic here describes.
    5.9 splits it at `PANEL_SPLIT_YEARS`; this is the same split counted, so the
    screens can state their own denominator instead of implying it is uniform.
    """
    aged, early = ctx.one(
        "SELECT count(*), sum(CASE WHEN dx_age_years <= "
        f"{PANEL_SPLIT_YEARS} THEN 1 ELSE 0 END) "
        "FROM patients_augmented "
        "WHERE growth_dx_flag = 1 AND dx_age_years IS NOT NULL")
    return {"label_aged": aged, "label_early": early,
            "label_early_share": 100.0 * early / aged if aged else 0.0,
            "split": PANEL_SPLIT_YEARS}


def _defines_index(value: object) -> bool:
    text = str(value).upper()
    return any(term in text for term in INDEX_TERMS)


def _labels(ctx: Context) -> tuple[float, float, int]:
    """Materialise both labels once, and return their base rates."""
    ctx.con.execute(f"""
        CREATE OR REPLACE TEMP TABLE {LABEL_TABLE} AS
        SELECT p.patient_id, p.growth_dx_flag AS dx,
               CASE WHEN w.patient_id IS NULL THEN 0 ELSE 1 END AS workup
        FROM patients_augmented p
        LEFT JOIN ({WORKUP_INDEX}) w USING (patient_id)""")
    dx_base, w_base, w_n = ctx.one(
        f"SELECT 100.0 * avg(dx), 100.0 * avg(workup), sum(workup) FROM {LABEL_TABLE}")
    return dx_base, w_base, w_n


def _screen(ctx: Context, source: str, dx_base: float, w_base: float) -> list[dict]:
    """Every value of one field, scored against both labels.

    No ORDER BY: equal shares would be ordered by whatever the parallel scan
    produced, so the ranking is applied in Python over stabilised values.
    """
    rows = ctx.q(f"""
        WITH v AS (
            SELECT DISTINCT patient_id, value FROM ({source}) s
            WHERE value IS NOT NULL AND trim(value) <> '')
        SELECT v.value, count(*), sum(l.dx), sum(l.workup)
        FROM v JOIN {LABEL_TABLE} l USING (patient_id)
        GROUP BY 1 HAVING count(*) >= {SUPPORT}""")
    out = []
    for value, n, flagged, workup in rows:
        share = 100.0 * flagged / n
        out.append({
            "value": value, "patients": n, "flagged": flagged, "share": share,
            "lift": share / dx_base,
            # A workup lift resting on fewer than the suppression threshold of
            # patients is not shown. The base rate is under one percent, so a
            # value carried by 200 patients expects one, and zero of them is an
            # absence of evidence rather than a measured zero.
            "workup_lift": (100.0 * workup / n) / w_base
                           if workup >= SUPPRESS_BELOW and not _defines_index(value)
                           else None,
        })
    return sorted(out, key=lambda r: (-float(format(r["lift"], ".8g")), str(r["value"])))


def _distinct(ctx: Context, source: str) -> int:
    return ctx.scalar(f"SELECT count(DISTINCT value) FROM ({source}) s "
                      "WHERE value IS NOT NULL AND trim(value) <> ''")


def _cohort(ctx: Context, sql: str, dx_base: float, w_base: float,
            name: str = "") -> dict:
    """Score one hand-named cohort against both labels."""
    n, flagged, workup = ctx.one(f"""
        SELECT count(*), sum(l.dx), sum(l.workup)
        FROM (SELECT DISTINCT patient_id FROM ({sql}) c) t
        JOIN {LABEL_TABLE} l USING (patient_id)""")
    return {"patients": ctx.suppress(n), "share": 100.0 * flagged / n,
            "lift": (100.0 * flagged / n) / dx_base,
            "workup_lift": (100.0 * workup / n) / w_base
                           if workup >= SUPPRESS_BELOW and not _defines_index(name)
                           else None}


@probe("shortcuts.audit", "5.14")
def audit(ctx: Context) -> list[Finding]:
    pc = patient_codes(ctx)
    dx_base, w_base, w_n = _labels(ctx)

    # --- the diagnosis fields, split from the rest because the tracked panel
    # and its descendants are the label itself rather than a shortcut for it.
    tracked = [c.replace("dx_age_years_", "").upper().replace("_", ".")
               for c in ctx.columns("patients_augmented")
               if c.startswith("dx_age_years_")]
    code_source = f"SELECT patient_id, code AS value FROM {pc}"
    codes = _screen(ctx, code_source, dx_base, w_base)
    for row in codes:
        row["is_label"] = any(str(row["value"]).startswith(t) for t in tracked)
    label_codes = [r for r in codes if r["is_label"]]
    perfect = [r for r in label_codes if r["share"] >= 100.0]
    other_codes = [r for r in codes if not r["is_label"]][:TOP_N]

    lookup = dict(ctx.q(f"""
        WITH l AS ({ICD_LOOKUP})
        SELECT l.code, l.descr FROM l"""))
    for row in other_codes:
        key = str(row["value"]).replace(".", "")
        row["descr"] = lookup.get(key, "[not in the ICD-10 lookup]")
    untracked = [r for r in codes if not r["is_label"]]

    # --- the other four fields
    screens = {name: _screen(ctx, sql, dx_base, w_base) for name, _, sql in SOURCES}
    distinct = {name: _distinct(ctx, sql) for name, _, sql in SOURCES}
    distinct["diagnosis code"] = _distinct(ctx, code_source)
    screened = sum(len(v) for v in screens.values()) + len(codes)
    field_rows = []
    for name, _, _ in SOURCES:
        for row in screens[name][:TOP_N]:
            field_rows.append(dict(row, field=name))

    cand_rows = [dict(_cohort(ctx, sql, dx_base, w_base, name), feature=name)
                 for name, sql in candidates(pc)]
    by_name = {r["feature"]: r for r in cand_rows}
    endo = by_name["endocrinology referral (5.13)"]
    conv = by_name["any encounter converted from the legacy system"]
    native = by_name["no converted encounter: recorded natively throughout"]

    # --- the medication result, which is what the curated panel could not find.
    # The cut is 5.11's own growth-hormone figure, so the two sections compare
    # the same population rather than two spellings of somatropin.
    meds = screens["medication"]
    med_cut = by_name["growth hormone prescription (5.11)"]["lift"]
    med_high = [r for r in meds if r["lift"] > med_cut]
    med_examples = ", ".join(f"`{r['value']}`" for r in med_high[:4])

    # --- the fields the screen clears, which are results of the same kind
    record_type = {str(r["value"]): r for r in screens["medication record type"]}
    flags = {str(r["value"]): r for r in screens["lab result flag"]}
    enc = {str(r["value"]): r for r in screens["encounter type"]}
    enc_named = [("Weight Check", "weight check"), ("Nutrition", "nutrition visit")]
    enc_shown = [(label, enc[key]["lift"]) for key, label in enc_named if key in enc]
    enc_top = str(screens["encounter type"][0]["value"])

    # --- the same substring, screened as a procedure name and as 5.11 matches it
    diluted = [r for r in screens["lab procedure"]
               if DILUTED.strip("%") in str(r["value"]).upper()]
    panel = _cohort(ctx, f"""
        SELECT patient_id FROM labs
        WHERE upper(lab_procedure_name) LIKE '{DILUTED}'
           OR upper(result_component_name) LIKE '{DILUTED}'""", dx_base, w_base)

    # --- the column that is the label
    pre = {bool(t): (n, hit) for t, n, hit in ctx.q("""
        SELECT visits_count_pre_dx < visits_count, count(*), sum(growth_dx_flag)
        FROM patients_augmented GROUP BY 1""")}
    (yes_n, yes_hit), (no_n, no_hit) = pre[True], pre[False]
    pre_rows = [
        {"group": "pre-diagnosis count is shorter than the lifetime count",
         "patients": ctx.suppress(yes_n), "flagged": ctx.suppress(yes_hit),
         "share": 100.0 * yes_hit / yes_n},
        {"group": "the two counts are equal",
         "patients": ctx.suppress(no_n), "flagged": ctx.suppress(no_hit),
         "share": 100.0 * no_hit / no_n},
    ]

    f = Finding(
        id="shortcuts.audit", part="5.14",
        title="A shortcut audit: which fields encode the label",
        values={
            **_perinatal_share(ctx),
            "support": SUPPORT, "screened": screened, "n_other": len(SOURCES),
            "distinct": sum(distinct.values()), "base": dx_base,
            "w_base": w_base, "w_n": w_n, "suppress": SUPPRESS_BELOW,
            "n_fields": len(SOURCES) + 1,
            "label_codes": len(label_codes), "perfect": len(perfect),
            # Reads as a subset when the two counts coincide, which they do here.
            "perfect_all": (", which is every code in that group"
                            if len(perfect) == len(label_codes) else ""),
            "max_lift": 100.0 / dx_base,
            "code_shown": len(other_codes), "code_untracked": len(untracked),
            "med_high": len(med_high), "med_screened": len(meds),
            "med_examples": med_examples, "gh_lift": med_cut,
            "enc_top": enc_top, "enc_top_lift": screens["encounter type"][0]["lift"],
            "ext_lift": record_type["External"]["lift"],
            "int_lift": record_type["Internal"]["lift"],
            "none_lift": flags["(NONE)"]["lift"], "none_n": flags["(NONE)"]["patients"],
            "enc_named": ", ".join(f"the {label} at {lift:.2f}"
                                   for label, lift in enc_shown),
            "yes_n": ctx.suppress(yes_n), "yes_hit": ctx.suppress(yes_hit),
            "no_n": ctx.suppress(no_n), "no_hit": ctx.suppress(no_hit),
            "precision": 100.0 * yes_hit / yes_n,
            "recall": 100.0 * yes_hit / (yes_hit + no_hit),
            "endo_lift": endo["lift"], "endo_workup": endo["workup_lift"],
            "conv_lift": conv["lift"], "native_lift": native["lift"],
            "conv_ratio": native["lift"] / conv["lift"],
        },
        artifact=Artifact(
            name="A derived column that is a function of the label",
            kind="derivation",
            scale="`visits_count_pre_dx` recovers `growth_dx_flag` at "
                  "{precision:.1f}% precision and {recall:.1f}% recall",
            recoverable="No — the column cannot be made label-free; exclude it",
        ),
    )

    blocks = [
        Para("5.11 and 5.13 measure the leakage in a list of candidates chosen for "
             "being clinically obvious. This section runs the search those sections "
             "imply: every value of {n_fields} categorical fields that {support:,} "
             "or more patients carry, scored against the label. {screened:,} values "
             "meet that floor, out of {distinct:,} distinct ones. Lift is the share "
             "of patients carrying a value who also carry `growth_dx_flag`, over the "
             "cohort's {base:.2f}% base rate; a lift of 1 is no information."),
        Para("**What the positive class is made of bounds what every lift here "
             "means.** Of the {label_aged:,} labelled patients with a diagnosis "
             "age, {label_early:,} ({label_early_share:.1f}%) are diagnosed at or "
             "before age {split:.0f} — 5.9's earlier stratum, the one with no "
             "measurement history before the code. A lift in this table is "
             "therefore mostly a statement about what co-occurs with perinatal "
             "coding, not about what precedes a growth problem. That does not make "
             "a leaking field safe to keep: a shortcut that works because the "
             "label is perinatal still works. It does mean a field that screens "
             "clean here has not been cleared for the later-diagnosed stratum, "
             "where the base rate, the timing and the available history are all "
             "different, and re-screening against a stratified label is the check "
             "this section does not perform.", role="warning"),
        Para("A value counts once per patient, ever, with no temporal cut — which is "
             "what an unrestricted feature build sees, and it mixes leakage with "
             "concurrency: a code recorded at the same encounter as the diagnosis "
             "scores as high as one recorded years before it. Beside each lift is "
             "the same figure against the alternative index of 5.11, the first "
             "growth workup or treatment, which {w_n:,} patients carry at a base "
             "rate of {w_base:.2f}%. It is suppressed where fewer than {suppress} "
             "patients back it, and where the value is itself part of the index "
             "definition — the somatropin, growth hormone and IGF records — since "
             "those score the index's maximum by construction rather than by "
             "discrimination.", role="method"),
        Para("**The raw diagnosis fields carry the label verbatim.** {label_codes} "
             "screened codes are one of the tracked panel or a descendant of one "
             "(3.9, 5.7), and {perfect} of them are carried by no unlabelled "
             "patient at all{perfect_all} — a lift of {max_lift:.2f}, the maximum "
             "the base rate allows. Dropping the `dx_age_years_*` columns therefore does not take "
             "the label out of a feature set: `enc_diag_*` and `pl_diag` "
             "reconstruct it exactly. The table below excludes that group and shows "
             "what is left."),
        Table("t-shortcut-codes",
              "Diagnosis codes with the highest lift, excluding the tracked panel "
              "and its descendants",
              [C("value", "ICD-10"), C("descr", "description"),
               C("patients", "patients", ",", align="right"),
               C("share", "carry the label", ".1f", "%", align="right"),
               C("lift", "lift", ".2f", "x", align="right"),
               C("workup_lift", "lift, workup index", ".2f", "x", align="right")],
              other_codes,
              note="Top {code_shown} by lift among codes carried by {support:,} or "
                   "more patients."),
        Para("What sits below the panel is the neighbourhood of a label 5.9 shows to "
             "be overwhelmingly perinatal: prematurity, its complications, and "
             "newborn morbidity. None is a growth code and none is tracked, but a "
             "patient carrying one was in the neonatal course that produced the "
             "label, and the screen reaches {code_untracked:,} untracked codes in "
             "all. That is the kind of shortcut a curated exclusion list does not "
             "reach: it is built by naming the condition, and none of these names "
             "the condition."),
        Table("t-shortcut-fields",
              "The top of the lift distribution in the other {n_other} fields",
              [C("field", "field"), C("value", "value"),
               C("patients", "patients", ",", align="right"),
               C("share", "carry the label", ".1f", "%", align="right"),
               C("lift", "lift", ".2f", "x", align="right"),
               C("workup_lift", "lift, workup index", ".2f", "x", align="right")],
              field_rows,
              note="Top {code_shown} values per field, by lift, among those carried "
                   "by {support:,} or more patients."),
        Para("Encounter type is the field the screen clears, and a measured null is "
             "as useful as a hit. Its highest value is `{enc_top}` at "
             "{enc_top_lift:.2f}, and the types whose names promise growth "
             "surveillance sit at the base rate: {enc_named}. Nothing in the report "
             "would otherwise establish that, since an argument from the name alone "
             "points the other way."),
        Para("The two fields added last behave differently from each other and "
             "neither carries much. Medication record type is flat — {ext_lift:.2f} "
             "for a patient with any external record against {int_lift:.2f} for an "
             "internal one. The laboratory result flag is flat too, apart from one "
             "value: its most enriched is the literal `(NONE)` at {none_lift:.2f} "
             "across {none_n:,} patients, which 3.5 shows is the string meaning "
             "*normal* and which became a null on nine rows in ten. A flag value "
             "asserting that nothing was abnormal is the one that discriminates, "
             "which is more plausibly a fact about which records still carry the "
             "sentinel than about the children carrying them."),
        Para("**The medication screen finds what a curated list could not.** "
             "{med_high} of the {med_screened} screened generic names lift higher "
             "than the {gh_lift:.2f} that 5.11 measures for growth hormone, and "
             "none of them is a growth treatment: {med_examples}. Type 1 diabetes is in the tracked panel "
             "(5.7), so every product dispensed to a child who carries that code — "
             "consumables included — reconstructs part of the label. An exclusion "
             "list built by naming growth treatments does not catch a box of "
             "lancets."),
    ]
    if diluted:
        top = diluted[0]
        f.values.update({"dil_value": top["value"], "dil_n": top["patients"],
                         "dil_lift": top["lift"], "panel_n": panel["patients"],
                         "panel_lift": panel["lift"]})
        blocks.append(
            Para("**The unit of the screen decides the answer.** 5.11 matches "
                 "`{dil_value}` as a substring across the procedure name and the "
                 "result component, finds {panel_n:,} patients at a lift of "
                 "{panel_lift:.2f}, and reads it as a general screen carrying no "
                 "information. Screened as a procedure name in its own right the "
                 "same test is {dil_n:,} patients at {dil_lift:.2f}. Both figures "
                 "are correct and they answer different questions: ordering the "
                 "test deliberately is not the same event as receiving it inside a "
                 "panel, and a substring match pools them.", role="method"))
    blocks += [
        Para("**One column reconstructs the label on its own.** "
             "`visits_count_pre_dx` counts a patient's visits up to the diagnosis, "
             "and for a patient without one it equals the lifetime count. The "
             "inequality between the two columns is therefore the label: "
             "{yes_n:,} patients have a shorter pre-diagnosis count and {yes_hit:,} "
             "of them are labelled, against {no_hit:,} of the {no_n:,} others. That "
             "is {precision:.1f}% precision at {recall:.1f}% recall from a single "
             "comparison of two delivered columns. 5.9 makes the point about counts "
             "measured to an index date; this is the same asymmetry shipped as a "
             "column, and no model given the augmented patient table can avoid it."),
        Table("t-shortcut-predx",
              "`visits_count_pre_dx` against `visits_count`",
              [C("group", "patients where"),
               C("patients", "patients", ",", align="right"),
               C("flagged", "carry the label", ",", align="right"),
               C("share", "share", ".2f", "%", align="right")], pre_rows),
        Para("**The shortcut set belongs to the label, not to the extract.** The "
             "same features scored against the alternative index reorder "
             "completely. An endocrinology referral lifts {endo_lift:.2f} against "
             "the code and {endo_workup:.2f} against the workup, so 5.13's advice "
             "to use it as a cohort filter selects on the outcome under 5.11's "
             "recommended design; and the growth-hormone and IGF-1 records that "
             "5.11 screens as leaking features are that design's definition of the "
             "label rather than features at all. Nothing here is transferable "
             "between the two."),
        Table("t-shortcut-index",
              "Named candidates against both labels",
              [C("feature", "feature"),
               C("patients", "patients", ",", align="right"),
               C("share", "carry the code label", ".1f", "%", align="right"),
               C("lift", "lift, code label", ".2f", "x", align="right"),
               C("workup_lift", "lift, workup index", ".2f", "x", align="right")],
              cand_rows),
        Para("Three rows deserve a second look. The pediatric BMI-percentile codes "
             "are the growth chart written into the diagnosis field and they carry "
             "no lift at all, because the label is perinatal rather than "
             "anthropometric — an obvious candidate that a screen clears and an "
             "argument would not. And the last two rows separate patients by nothing "
             "clinical at all: a record kept natively throughout lifts "
             "{native_lift:.2f} against {conv_lift:.2f} for one carrying any "
             "encounter converted from the practice network's previous system, a "
             "{conv_ratio:.1f}-fold spread on a provenance field. 3.7 measures that "
             "field's effect on diagnosis completeness; this is what the same effect "
             "does to a label."),
        Para("One bound on all of this comes from 1.4. The cohort excluded every "
             "code, medication and procedure seen fewer than 11 times along with "
             "the patients carrying them, and 5.11 measures how much of the "
             "laboratory vocabulary that removed. The rarest and most specific "
             "markers are the most likely to be gone, so a screen on this extract "
             "under-detects exactly the shortcuts it most wants to find.",
             role="warning"),
        Para("**Implications for analysis.** Screen rather than enumerate: run this "
             "against your own label and index before building a feature set, and "
             "re-run it after any change to either. Exclude the fields that "
             "reconstruct the label — the raw diagnosis slots and the problem list, "
             "`visits_count_pre_dx`, and the treatment records of 5.11 — and "
             "remember that a field carrying no clinical meaning can still "
             "discriminate. A lift measured here is an upper bound on what a "
             "temporally honest feature could contribute, not an estimate of it: "
             "everything above is scored without a cut, so a value that only ever "
             "appears alongside the diagnosis scores as high as one that precedes "
             "it.", role="implication"),
    ]
    f.blocks = blocks
    return [f]


# ---------------------------------------------------------------------------
# 5.15 — the same question asked of the numbers
# ---------------------------------------------------------------------------

#: A lift needs a category. A continuous column needs a statistic that does not
#: depend on where a threshold is put, so this is the rank statistic: the
#: probability that a labelled patient ranks above an unlabelled one, with ties
#: taking their mid-rank. 0.5 is no separation, and below 0.5 means the labelled
#: patients rank lower rather than that the column carries nothing.
NEUTRAL = 0.5

#: The observation-window control: a record running to at least this age and
#: spanning at least this long. Coarse rather than matched, and 5.15 says so.
RESTRICT_DAYS = 1826

NUMERIC_TABLE = "_shortcut_numeric"

#: Features a modeller would build rather than find. Each is (key, label,
#: expression over the assembled table). The pair of problem-list counts is
#: deliberate: the tracked panel reaches the problem list (5.12), so the total
#: is contaminated by the label and the difference between the two rows is how
#: much.
CONSTRUCTED = [
    ("visits_per_year", "visits per year of record"),
    ("med_gap", "median days between consecutive visits"),
    ("problems_all", "problem-list entries"),
    ("problems_untracked", "problem-list entries, excluding the tracked panel"),
    ("lab_orders", "distinct laboratory orders"),
    ("lab_procs", "distinct laboratory procedures"),
    ("med_orders", "medication records"),
    ("height_share", "share of visits carrying a height"),
    ("hc_late", "head circumferences recorded after age 3"),
    ("same_day", "days carrying two or more heights (3.8)"),
    ("file_order", "position in the delivered patient file"),
]


def _tracked_codes(ctx: Context) -> list[str]:
    return [c.replace("dx_age_years_", "").upper().replace("_", ".")
            for c in ctx.columns("patients_augmented")
            if c.startswith("dx_age_years_")]


def _build_numeric(ctx: Context) -> None:
    """One row per patient: the delivered columns plus the constructed ones."""
    tracked = " OR ".join(f"starts_with(pl_diag, '{t}')" for t in _tracked_codes(ctx))
    ctx.con.execute(f"""
        CREATE OR REPLACE TEMP TABLE {NUMERIC_TABLE} AS
        WITH v AS (
            SELECT patient_id,
                   avg(CASE WHEN height_in IS NOT NULL THEN 1.0 ELSE 0.0 END)
                       AS height_share,
                   CAST(sum(CASE WHEN head_circ_cm IS NOT NULL
                                  AND age_in_days > 1095 THEN 1 ELSE 0 END)
                        AS BIGINT) AS hc_late
            FROM visits GROUP BY 1),
        gaps AS (
            SELECT patient_id, quantile_cont(gap, 0.5) AS med_gap FROM (
                SELECT patient_id, age_in_days
                       - lag(age_in_days) OVER (PARTITION BY patient_id
                                                ORDER BY age_in_days) AS gap
                FROM visits)
            WHERE gap IS NOT NULL GROUP BY 1),
        repeats AS (
            SELECT patient_id, CAST(count(*) AS BIGINT) AS same_day FROM (
                SELECT patient_id, age_in_days FROM visits
                WHERE height_in IS NOT NULL GROUP BY 1, 2 HAVING count(*) >= 2)
            GROUP BY 1),
        labs_by_patient AS (
            SELECT patient_id, count(DISTINCT lab_order_id) AS lab_orders,
                   count(DISTINCT lab_procedure_name) AS lab_procs
            FROM labs GROUP BY 1),
        meds AS (SELECT patient_id, count(*) AS med_orders FROM medications GROUP BY 1),
        probs AS (
            SELECT patient_id, count(*) AS problems_all,
                   sum(CASE WHEN {tracked} THEN 0 ELSE 1 END) AS problems_untracked
            FROM problem_list GROUP BY 1)
        SELECT p.*,
               CASE WHEN p.max_visit_age_days >= {RESTRICT_DAYS}
                     AND p.visits_span_days >= {RESTRICT_DAYS}
                    THEN 1 ELSE 0 END AS long_record,
               p.visits_count / greatest(p.visits_span_days, 1) * 365.25
                   AS visits_per_year,
               gaps.med_gap, v.height_share, v.hc_late,
               coalesce(repeats.same_day, 0) AS same_day,
               coalesce(labs_by_patient.lab_orders, 0) AS lab_orders,
               coalesce(labs_by_patient.lab_procs, 0) AS lab_procs,
               coalesce(meds.med_orders, 0) AS med_orders,
               coalesce(probs.problems_all, 0) AS problems_all,
               coalesce(probs.problems_untracked, 0) AS problems_untracked,
               f.file_order
        FROM patients_augmented p
        LEFT JOIN v USING (patient_id)
        LEFT JOIN gaps USING (patient_id)
        LEFT JOIN repeats USING (patient_id)
        LEFT JOIN labs_by_patient USING (patient_id)
        LEFT JOIN meds USING (patient_id)
        LEFT JOIN probs USING (patient_id)
        LEFT JOIN (SELECT patient_id, rowid AS file_order FROM patients) f
               USING (patient_id)""")


def _auc(ctx: Context, column: str, where: str = "TRUE") -> tuple[float, int] | None:
    """The rank statistic for one column, with ties at their mid-rank."""
    total, labelled, rank_sum = ctx.one(f"""
        WITH x AS (
            SELECT growth_dx_flag AS dx, {column} AS value
            FROM {NUMERIC_TABLE} WHERE {column} IS NOT NULL AND {where}),
        r AS (
            SELECT dx, rank() OVER (ORDER BY value) AS low,
                   count(*) OVER (PARTITION BY value) AS ties
            FROM x)
        SELECT count(*), sum(dx),
               sum(CASE WHEN dx = 1 THEN low + (ties - 1) / 2.0 ELSE 0 END)
        FROM r""")
    unlabelled = total - labelled
    if not labelled or not unlabelled:
        return None
    auc = (rank_sum - labelled * (labelled + 1) / 2.0) / (labelled * unlabelled)
    return auc, total


def _score(ctx: Context, column: str, label: str) -> dict | None:
    full = _auc(ctx, column)
    if full is None:
        return None
    auc, n = full
    long_record = _auc(ctx, column, "long_record = 1")
    return {"column": label, "patients": ctx.suppress(n), "auc": auc,
            "separation": abs(2.0 * auc - 1.0),
            "long_auc": long_record[0] if long_record else None}


@probe("shortcuts.numbers", "5.15")
def numbers(ctx: Context) -> list[Finding]:
    _labels(ctx)
    _build_numeric(ctx)
    types = ctx.coltype("patients_augmented")
    dx_cols = [c for c in types if c.startswith("dx_age_years")]
    delivered = [c for c in ctx.columns("patients_augmented")
                 if types[c] in ("BIGINT", "DOUBLE", "INTEGER")
                 and c != "growth_dx_flag" and not c.startswith("dx_age_years")]

    rows = [r for r in (_score(ctx, c, f"`{c}`") for c in delivered) if r]
    rows.sort(key=lambda r: (-float(format(r["separation"], ".8g")), r["column"]))
    built = [r for r in (_score(ctx, key, label) for key, label in CONSTRUCTED) if r]
    built.sort(key=lambda r: (-float(format(r["separation"], ".8g")), r["column"]))

    top = rows[:10]
    flat = [r for r in rows if r["separation"] < 0.1]
    by_col = {r["column"]: r for r in rows}
    by_key = {r["column"]: r for r in built}

    n_long, labelled_long, dx_age_long = ctx.one(f"""
        SELECT count(*), sum(growth_dx_flag), quantile_cont(dx_age_years, 0.5)
        FROM {NUMERIC_TABLE} WHERE long_record = 1""")

    f = Finding(
        id="shortcuts.numbers", part="5.15",
        title="The same screen over the numbers: derived columns and constructed "
              "features",
        values={
            **_perinatal_share(ctx),
            "delivered": len(delivered), "dx_cols": len(dx_cols),
            "shown": len(top), "flat": len(flat), "neutral": NEUTRAL,
            "built": len(built), "restrict_years": RESTRICT_DAYS / 365.25,
            "n_long": n_long, "long_base": 100.0 * labelled_long / n_long,
            "long_dx_age": dx_age_long,
            "pre_dx_auc": by_col["`visits_count_pre_dx`"]["auc"],
            "max_age_auc": by_col["`max_visit_age_days`"]["auc"],
            "span_auc": by_col["`visits_span_days`"]["auc"],
            "bmi_count_auc": by_col["`count_bmi_z_score`"]["auc"],
            "min_weight_auc": by_col["`min_weight_z_score`"]["auc"],
            "hc_count_auc": by_col["`count_head_circ_z_score`"]["auc"],
            "stunting_auc": by_col["`ever_stunting_flag`"]["auc"],
            "visits_auc": by_col["`visits_count`"]["auc"],
            "rate_auc": by_key["visits per year of record"]["auc"],
            "rate_long": by_key["visits per year of record"]["long_auc"],
            "gap_auc": by_key["median days between consecutive visits"]["auc"],
            "gap_long": by_key["median days between consecutive visits"]["long_auc"],
            "prob_all": by_key["problem-list entries"]["auc"],
            "prob_clean": by_key[
                "problem-list entries, excluding the tracked panel"]["auc"],
            "same_day_auc": by_key["days carrying two or more heights (3.8)"]["auc"],
            "procs_auc": by_key["distinct laboratory procedures"]["auc"],
            "procs_long": by_key["distinct laboratory procedures"]["long_auc"],
            "order_auc": by_key["position in the delivered patient file"]["auc"],
        },
        artifact=Artifact(
            name="Contact intensity separates the label without measuring the child",
            kind="derivation",
            scale="visits per year of record ranks a labelled patient above an "
                  "unlabelled one {rate_auc:.3f} of the time, against "
                  "{visits_auc:.3f} for lifetime visit count",
            recoverable="Yes — fix a common index date and observation window, or "
                        "exclude the record-shape columns",
        ),
    )
    f.blocks = [
        Para("5.14 screens categorical fields, where a lift answers the question. A "
             "continuous column needs a statistic that does not depend on where a "
             "threshold is put, so this section uses the rank statistic: the "
             "probability that a labelled patient ranks above an unlabelled one, "
             "with ties at their mid-rank. {neutral} is no separation. Below it "
             "means the labelled patients rank lower, which is a direction rather "
             "than an absence, so the tables sort on distance from {neutral} and "
             "carry it as its own column."),
        Para("The same caveat as 5.14 applies to every figure below, and for the "
             "same reason: {label_early_share:.1f}% of the labelled patients with "
             "a diagnosis age are diagnosed at or before age {split:.0f}, so a "
             "rank statistic here mostly separates the perinatal stratum of 5.9 "
             "from everyone else. A column that separates the pooled label may "
             "separate the later-diagnosed stratum better, worse, or not at all.",
             role="warning"),
        Para("Every numeric column of the augmented patient layer is screened — "
             "{delivered} of them, after setting aside the label and the "
             "{dx_cols} `dx_age_years` columns that carry its age. Beside each is "
             "the same statistic among patients whose record reaches "
             "{restrict_years:.0f} years of age and spans {restrict_years:.0f} "
             "years, which is a coarse control for how much record exists rather "
             "than a matched design.", role="method"),
        Table("t-numeric-delivered",
              "The {shown} delivered patient columns that separate the label most",
              [C("column", "column"), C("patients", "patients", ",", align="right"),
               C("auc", "rank statistic", ".3f", align="right"),
               C("separation", "distance from neutral", ".3f", align="right"),
               C("long_auc", "long records only", ".3f", align="right")], top,
              note="Of {delivered} columns screened, {flat} sit within 0.05 of "
                   "{neutral} and carry almost nothing on their own."),
        Para("**After the column that is the label, growth and bookkeeping are "
             "interleaved.** `visits_count_pre_dx` leads at {pre_dx_auc:.3f} because "
             "5.14 shows it to be the label written as a count. Then the lowest "
             "weight z-score a child ever recorded at {min_weight_auc:.3f} — and "
             "immediately behind it the age at the last visit at {max_age_auc:.3f}, "
             "the number of BMI values at {bmi_count_auc:.3f}, and the span of the "
             "record at {span_auc:.3f}. **The shape of a patient's record separates "
             "this label about as well as the child's growth does**, because a "
             "labelled patient is younger and less observed when the label is "
             "perinatal (5.9)."),
        Para("Two columns further down the same screen are worth putting side by "
             "side; neither reaches the ten shown above. The count of head "
             "circumference measurements separates at {hc_count_auc:.3f} and the "
             "stunting flag at {stunting_auc:.3f}: **how often a child was measured "
             "carries more about this label than whether the measurement was low.** "
             "Meanwhile `visits_count` itself is {visits_auc:.3f}, which is nothing "
             "— lifetime volume does not discriminate, and the rate at which that "
             "volume accumulates does."),
        Table("t-numeric-built", "Constructed features, scored the same way",
              [C("column", "feature"), C("patients", "patients", ",", align="right"),
               C("auc", "rank statistic", ".3f", align="right"),
               C("separation", "distance from neutral", ".3f", align="right"),
               C("long_auc", "long records only", ".3f", align="right")], built,
              note="Features a modeller would build rather than find, each computed "
                   "over the whole record with no temporal cut."),
        Para("**Contact intensity separates the label, and it is not only "
             "censoring.** Visits per year runs {rate_auc:.3f} and the median gap "
             "between visits {gap_auc:.3f}; restricted to records of "
             "{restrict_years:.0f} years or more they hold at {rate_long:.3f} and "
             "{gap_long:.3f}. A model given visit timing has been told something "
             "about the label that no growth measurement supplied. Read the rate "
             "with its denominator in mind, though: it divides by a span that is "
             "itself a {span_auc:.3f} separator."),
        Para("The restriction controls the observation window and nothing else. "
             "Inside it {n_long:,} patients remain at a labelled rate of "
             "{long_base:.1f}%, and their median age at diagnosis is still "
             "{long_dx_age:.3f} years. The perinatal concentration survives the cut, "
             "so a separation that holds under it is bounded above by what an "
             "age-matched design would find, not established by it. Restricting on "
             "record length is the wrong axis for that: 5.9 splits the labelled "
             "class on age at diagnosis instead, and it is that split rather than "
             "this one which separates the patients who have a history before the "
             "label from the ones who do not.", role="warning"),
        Para("**The problem-list count shows what contamination costs.** Counting "
             "every entry gives {prob_all:.3f}; counting only entries outside the "
             "tracked panel gives {prob_clean:.3f}. The tracked codes reach the "
             "problem list (5.12), so the first number is part label and part "
             "utilisation, and only the second is a feature. A count over a "
             "diagnosis resource needs the label's own codes taken out of it before "
             "it means anything."),
        Para("Several results are negative, and they are worth recording as such. "
             "Days carrying two or more heights — the same-day disagreement of 3.8, "
             "read as a sign of a clinician re-measuring — sit at "
             "{same_day_auc:.3f}. A patient's position in the delivered file is "
             "{order_auc:.3f}: the delivery is not ordered by anything related to "
             "the label, which is the one shortcut that would have been invisible "
             "in every other check in this report. The breadth of the laboratory "
             "workup is {procs_auc:.3f} across the whole cohort but "
             "{procs_long:.3f} among long records, which is the pattern to expect "
             "when a flat result is itself an artifact of the age mix rather than "
             "a finding: a null measured over this cohort is not a null."),
        Para("**Implications for analysis.** Screen continuous features the same way "
             "you screen categorical ones, and screen the ones you build as well as "
             "the ones you were given — the highest-ranking features here are a "
             "count of measurements and a rate of contact, neither of which looks "
             "like a leak in a feature list. Where a column describes the record "
             "rather than the child, either exclude it or make the observation "
             "window an explicit part of the design; 5.9's common index date is the "
             "same remedy arrived at from the other direction.", role="implication"),
    ]
    return [f]

"""Part 5.13 — an exhaustive screen for fields that encode the label.

5.10 and 5.12 test a hand-curated list of clinically obvious candidates. That is
a hypothesis test rather than a search: it can confirm that growth hormone leaks
and it cannot discover the leak nobody thought to name. This probe screens every
value of five categorical fields against the label, reports the top of the lift
distribution instead of a chosen subset, and repeats the screen under the
alternative index event 5.10 recommends — because the shortcut set is a property
of the label, not of the extract.
"""

from __future__ import annotations

from ..context import SUPPRESS_BELOW, Context
from ..findings import Artifact, Finding, Para, Table, probe
from ..findings import Column as C
from .growth import ICD_LOOKUP
from .icd import patient_codes
from .joint import WORKUP_INDEX

#: Patients who must carry a value before it is screened. Well above the
#: suppression floor: a lift computed on a dozen patients is noise, and the
#: point of the screen is the shape of the distribution rather than its tail.
SUPPORT = 200

#: Rows shown per field. The screen looks at everything; the table shows the top.
TOP_N = 5

#: Four of the five categorical fields a feature build would draw on, with the
#: query that yields one row per patient and value; the diagnosis code is the
#: fifth and is screened separately, since the tracked panel has to be split out
#: of it. Free-text names are screened as delivered rather than normalised,
#: since that is how a join would see them.
SOURCES = [
    ("medication", "`medications.med_simple_generic_name`",
     "SELECT patient_id, med_simple_generic_name AS value FROM medications"),
    ("lab procedure", "`labs.lab_procedure_name`",
     "SELECT patient_id, lab_procedure_name AS value FROM labs"),
    ("referral specialty", "`referrals.requested_specialty`",
     "SELECT patient_id, requested_specialty AS value FROM referrals"),
    ("encounter type", "`visits.encounter_type`",
     "SELECT patient_id, encounter_type AS value FROM visits"),
]

#: Candidates carried forward from the curated sections, plus the two the screen
#: adds, scored against both labels. Fixed rather than data-driven so the
#: comparison is the same one 5.10 and 5.12 make.
def candidates(pc: str) -> list[tuple[str, str]]:
    return [
        ("endocrinology referral (5.12)",
         ("SELECT patient_id FROM referrals "
          "WHERE lower(requested_specialty) LIKE '%endocrin%'")),
        ("growth hormone prescription (5.10)",
         ("SELECT patient_id FROM medications "
          "WHERE lower(med_simple_generic_name) LIKE '%somatropin%'")),
        ("stunting flag ever set (5.9)",
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

#: 5.10 matches this substring across the procedure name and the result
#: component and reports no signal. The screen ranks procedure names, which is a
#: different unit; both numbers are computed here so the gap is measured rather
#: than argued.
DILUTED = "%ALKALINE PHOS%"

LABEL_TABLE = "_shortcut_label"

#: Substrings that put a record inside the workup index itself. A value matching
#: one of these scores the index's maximum against it by construction rather
#: than by discrimination, so its workup lift is withheld the same way an
#: unbacked one is. `%IGF%` catches the binding protein as well as IGF-1, which
#: is a property of the index definition in 5.10 and not of this screen.
INDEX_TERMS = ("SOMATROPIN", "IGF", "GROWTH HORMONE")


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


@probe("shortcuts.audit", "5.13")
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
    endo = by_name["endocrinology referral (5.12)"]
    conv = by_name["any encounter converted from the legacy system"]
    native = by_name["no converted encounter: recorded natively throughout"]

    # --- the medication result, which is what the curated panel could not find.
    # The cut is 5.10's own growth-hormone figure, so the two sections compare
    # the same population rather than two spellings of somatropin.
    meds = screens["medication"]
    med_cut = by_name["growth hormone prescription (5.10)"]["lift"]
    med_high = [r for r in meds if r["lift"] > med_cut]
    med_examples = ", ".join(f"`{r['value']}`" for r in med_high[:4])

    # --- the field the screen clears, which is a result of the same kind
    enc = {str(r["value"]): r for r in screens["encounter type"]}
    enc_named = [("Weight Check", "weight check"), ("Nutrition", "nutrition visit")]
    enc_shown = [(label, enc[key]["lift"]) for key, label in enc_named if key in enc]
    enc_top = str(screens["encounter type"][0]["value"])

    # --- the same substring, screened as a procedure name and as 5.10 matches it
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
        id="shortcuts.audit", part="5.13",
        title="A shortcut audit: which fields encode the label",
        values={
            "support": SUPPORT, "screened": screened,
            "distinct": sum(distinct.values()), "base": dx_base,
            "w_base": w_base, "w_n": w_n, "suppress": SUPPRESS_BELOW,
            "n_fields": len(SOURCES) + 1,
            "label_codes": len(label_codes), "perfect": len(perfect),
            "max_lift": 100.0 / dx_base,
            "code_shown": len(other_codes), "code_untracked": len(untracked),
            "med_high": len(med_high), "med_screened": len(meds),
            "med_examples": med_examples, "gh_lift": med_cut,
            "enc_top": enc_top, "enc_top_lift": screens["encounter type"][0]["lift"],
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
        Para("5.10 and 5.12 measure the leakage in a list of candidates chosen for "
             "being clinically obvious. This section runs the search those sections "
             "imply: every value of {n_fields} categorical fields that {support:,} "
             "or more patients carry, scored against the label. {screened:,} values "
             "clear that floor, out of {distinct:,} distinct ones. Lift is the share "
             "of patients carrying a value who also carry `growth_dx_flag`, over the "
             "cohort's {base:.2f}% base rate; a lift of 1 is no information."),
        Para("A value counts once per patient, ever, with no temporal cut — which is "
             "what an unrestricted feature build sees, and it mixes leakage with "
             "concurrency: a code recorded at the same encounter as the diagnosis "
             "scores as high as one recorded years before it. Beside each lift is "
             "the same figure against the alternative index of 5.10, the first "
             "growth workup or treatment, which {w_n:,} patients carry at a base "
             "rate of {w_base:.2f}%. It is suppressed where fewer than {suppress} "
             "patients back it, and where the value is itself part of the index "
             "definition — the somatropin, growth hormone and IGF records — since "
             "those score the index's maximum by construction rather than by "
             "discrimination.", role="method"),
        Para("**The raw diagnosis fields carry the label verbatim.** {label_codes} "
             "screened codes are one of the tracked panel or a descendant of one "
             "(3.9, 5.7), and {perfect} of those are carried by no unlabelled "
             "patient at all — a lift of {max_lift:.2f}, the maximum the base rate "
             "allows. Dropping the `dx_age_years_*` columns therefore does not take "
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
        Para("What sits below the panel is the neighbourhood of a label 5.8 shows to "
             "be overwhelmingly perinatal: prematurity, its complications, and "
             "newborn morbidity. None is a growth code and none is tracked, but a "
             "patient carrying one was in the neonatal course that produced the "
             "label, and the screen clears {code_untracked:,} untracked codes in "
             "all. That is the kind of shortcut a curated exclusion list does not "
             "reach: it is built by naming the condition, and none of these names "
             "the condition."),
        Table("t-shortcut-fields",
              "The top of the lift distribution in the other four fields",
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
        Para("**The medication screen finds what a curated list could not.** "
             "{med_high} of the {med_screened} screened generic names lift higher "
             "than the {gh_lift:.2f} that 5.10 measures for growth hormone, and "
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
            Para("**The unit of the screen decides the answer.** 5.10 matches "
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
             "comparison of two delivered columns. 5.8 makes the point about counts "
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
             "the code and {endo_workup:.2f} against the workup, so 5.12's advice "
             "to use it as a cohort filter selects on the outcome under 5.10's "
             "recommended design; and the growth-hormone and IGF-1 records that "
             "5.10 screens as leaking features are that design's definition of the "
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
             "the patients carrying them, and 5.10 measures how much of the "
             "laboratory vocabulary that removed. The rarest and most specific "
             "markers are the most likely to be gone, so a screen on this extract "
             "under-detects exactly the shortcuts it most wants to find.",
             role="warning"),
        Para("**Implications for analysis.** Screen rather than enumerate: run this "
             "against your own label and index before building a feature set, and "
             "re-run it after any change to either. Exclude the fields that "
             "reconstruct the label — the raw diagnosis slots and the problem list, "
             "`visits_count_pre_dx`, and the treatment records of 5.10 — and "
             "remember that a field carrying no clinical meaning can still "
             "discriminate. A lift measured here is an upper bound on what a "
             "temporally honest feature could contribute, not an estimate of it: "
             "everything above is scored without a cut, so a value that only ever "
             "appears alongside the diagnosis scores as high as one that precedes "
             "it.", role="implication"),
    ]
    f.blocks = blocks
    return [f]

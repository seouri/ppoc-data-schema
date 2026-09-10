"""Part 1.2, 1.3, 1.5 — resource map, the raw/augmented split, de-identification."""

from __future__ import annotations

from ..context import COHORT_AS_OF, RESOURCES, Context
from ..findings import Artifact, Column, Finding, Para, Table, probe
from .snapshot import VENDOR_RESOURCES

GRAIN = {
    "patients": ("one row per patient", "patient_id", "—"),
    "patients_augmented": ("one row per patient", "patient_id", "patients"),
    "visits": ("one row per patient per encounter", "visit_id", "patients"),
    "visits_augmented": ("one row per patient per encounter", "visit_id", "visits"),
    # Not simply "one row per resulted component": 5.2 measures 2.3 million rows
    # that are orders which returned nothing and still occupy a row.
    "labs": ("one row per resulted component, or per order that returned none",
             "lab_order_id + result_line_num", "patients; visits (partial)"),
    "medications": ("one row per medication order or historical record",
                    "med_record_id", "patients; visits (partial)"),
    "problem_list": ("one row per problem-list entry", "problem_list_id", "patients"),
    "referrals": ("one row per referral order", "referral_id",
                  "patients; visits (partial)"),
}

#: Every check de-identification forecloses. 1.5 says this is stated once and
#: referenced from Part 2, so it has to be the complete list: it used to hold
#: seven while Part 2's not-applicable column held nine. `coverage.py` checks
#: itself against this rather than keeping a second copy.
DEIDENT_CHECKS = [
    ("Duplicate-patient detection", "no name, birth date, or linkage key survives"),
    ("Batch-entry clustering", "ages are integer days; there is no time of day"),
    ("System downtime gaps", "no calendar axis on which a void could appear"),
    ("Missingness by site or provider", "no such column exists in any resource"),
    ("Site or provider volume", "no such column exists in any resource"),
    ("Calendar trend breaks", "no calendar axis"),
    ("Guideline or policy shift", "no calendar axis to place a change on"),
    ("Copy-forward of note text", "no note text is included"),
    ("Template or boilerplate detection", "no note text is included"),
    ("Documentation timing", "no timestamps"),
]

# Fields carried by both the raw and the augmented visit layer under the same
# meaning. `bmi` is compared case-insensitively: the raw column is `BMI`.
SHARED = [("height_in", "height_in"), ("weight_oz", "weight_oz"),
          ("head_circ_cm", "head_circ_cm"), ("encounter_type", "encounter_type"),
          ("age_in_days", "age_in_days"), ("BMI", "bmi")]

# The same question on the patient layer. `race_1` stands for the eight race
# slots, which are cleaned identically. Checking only the visit layer left the
# larger divergence unmeasured: Part 5 works in the augmented patient table.
SHARED_PATIENT = ["sex", "ethnicity", "race_1"]


@probe("layers.resources", "1.2")
def resources(ctx: Context) -> list[Finding]:
    rows = []
    for name, (grain, key, links) in GRAIN.items():
        rows.append({
            "resource": name,
            "source": "PPOC" if name in VENDOR_RESOURCES else "scripts/augment.py",
            "rows": ctx.scalar(f"SELECT count(*) FROM {name}"),
            "columns": len(ctx.columns(name)),
            "grain": grain, "key": key, "links": links,
        })
    # Counted from GRAIN rather than written into the sentence: it was "three"
    # against a table showing four.
    off_axis = sum(1 for _, (_, key, _) in GRAIN.items()
                   if key not in ("patient_id", "visit_id"))
    f = Finding(
        id="layers.resources", part="1.2", title="Resource map, grain, and keys",
        values={"n": len(rows), "off_axis": off_axis,
                "cols": sum(r["columns"] for r in rows),
                "delivered": sum(1 for r in rows if r["source"] == "PPOC"),
                "generated": sum(1 for r in rows if r["source"] != "PPOC")},
    )
    f.blocks = [
        Para("The package is {n} tables carrying {cols} columns between them, but "
             "they do not share a provenance: {delivered} were delivered by PPOC and "
             "{generated} are generated locally (1.3). Grain matters more than row "
             "count here: {off_axis} of the resources are keyed on something other "
             "than the patient or the visit, and one of them needs two columns to "
             "be unique."),
        Table("t-resources", "The eight resources",
              [Column("resource", "resource"), Column("source", "source"),
               Column("rows", "rows", ",", align="right"),
               Column("columns", "cols", ",", align="right"), Column("grain", "grain"),
               Column("key", "primary key"), Column("links", "links to")], rows,
              note="Six resources were delivered by PPOC; the two augmented ones "
                   "are generated locally from them. 1.3 explains why that "
                   "distinction matters."),
        Para("`visit_id` on labs, medications, and referrals is a partial link by "
             "design, not a defect: an order placed outside a visit carries an "
             "identifier that resolves to no encounter in this extract. Section 3.2 "
             "measures how partial.", role="body"),
    ]
    return [f]


@probe("layers.agreement", "1.3")
def agreement(ctx: Context) -> list[Finding]:
    total = ctx.scalar("SELECT count(*) FROM visits v JOIN visits_augmented a "
                       "USING (visit_id)")
    rows = []
    for raw, aug in SHARED:
        diff = ctx.scalar(
            f"SELECT count(*) FROM visits v JOIN visits_augmented a USING (visit_id) "
            f'WHERE v."{raw}" IS DISTINCT FROM a."{aug}"'
        )
        rows.append({"field": raw if raw == aug else f"{raw} / {aug}",
                     "differs": diff, "share": 100.0 * diff / total})

    raw_only, aug_only, both_differ = ctx.one(
        "SELECT sum(CASE WHEN v.BMI IS NOT NULL AND a.bmi IS NULL THEN 1 ELSE 0 END), "
        "       sum(CASE WHEN v.BMI IS NULL AND a.bmi IS NOT NULL THEN 1 ELSE 0 END), "
        "       sum(CASE WHEN v.BMI IS NOT NULL AND a.bmi IS NOT NULL "
        "                AND abs(v.BMI - a.bmi) > 0.01 THEN 1 ELSE 0 END) "
        "FROM visits v JOIN visits_augmented a USING (visit_id)")
    med_age = ctx.scalar(
        "SELECT quantile_cont(a.age_in_years, 0.5) FROM visits v "
        "JOIN visits_augmented a USING (visit_id) "
        "WHERE v.BMI IS NOT NULL AND a.bmi IS NULL")

    p_total = ctx.scalar("SELECT count(*) FROM patients p "
                         "JOIN patients_augmented g USING (patient_id)")
    p_rows = []
    for col in SHARED_PATIENT:
        diff, lost, raw_n, aug_n = ctx.one(
            f"SELECT sum(CASE WHEN p.\"{col}\" IS DISTINCT FROM g.\"{col}\" "
            f"                THEN 1 ELSE 0 END), "
            f"       sum(CASE WHEN p.\"{col}\" IS NOT NULL "
            f"                AND g.\"{col}\" IS NULL THEN 1 ELSE 0 END), "
            f'       count(p."{col}"), count(g."{col}") '
            "FROM patients p JOIN patients_augmented g USING (patient_id)")
        p_rows.append({
            "field": col, "differs": diff, "share": 100.0 * diff / p_total,
            "lost": lost,
            "raw_distinct": ctx.scalar(f'SELECT count(DISTINCT "{col}") FROM patients'),
            "aug_distinct": ctx.scalar(
                f'SELECT count(DISTINCT "{col}") FROM patients_augmented'),
            "raw_n": raw_n, "aug_n": aug_n,
        })
    p_worst = max(p_rows, key=lambda r: r["differs"])
    dropped = ctx.q(
        "SELECT DISTINCT ethnicity FROM patients WHERE ethnicity IS NOT NULL "
        "AND ethnicity NOT IN (SELECT ethnicity FROM patients_augmented "
        "                      WHERE ethnicity IS NOT NULL) ORDER BY 1")

    f = Finding(
        id="layers.agreement", part="1.3",
        title="Two layers with different provenance",
        values={"total": total, "raw_only": raw_only, "aug_only": aug_only,
                "both_differ": both_differ, "med_age": med_age,
                "p_total": p_total, "p_field": p_worst["field"],
                "p_differs": p_worst["differs"], "p_lost": p_worst["lost"],
                "p_raw_distinct": p_worst["raw_distinct"],
                "p_aug_distinct": p_worst["aug_distinct"],
                "n_dropped": len(dropped),
                "dropped": ", ".join(f'"{r[0]}"' for r in dropped),
                "delivered": len(VENDOR_RESOURCES),
                "generated": len(RESOURCES) - len(VENDOR_RESOURCES),
                "resources": len(RESOURCES)},
        artifact=Artifact(
            name="Raw and augmented BMI disagree on infants",
            kind="derivation",
            scale=("{raw_only:,} visits carry a raw BMI the augmented layer "
                   "withholds; {both_differ:,} differ outright"),
            recoverable="Yes — pick the layer deliberately and state which",
        ),
    )
    f.blocks = [
        Para("**Only {delivered} of the {resources} resources in this package came "
             "from PPOC.** The delivery comprised patients, visits, problem list, "
             "medications, labs, and referral orders; the data dictionary and the "
             "extract diagram committed under `docs/` describe those {delivered} and "
             "no others. The remaining {generated} — `patients_augmented` and "
             "`visits_augmented` — are **generated locally** by `scripts/augment.py` "
             "from the delivered files, using CDC LMS reference tables, velocity "
             "rules, and outlier detection.", role="warning"),
        Para("That distinction decides who can fix what. A defect in a delivered "
             "resource is the source system's and can only be worked around; a "
             "defect in the augmented layer belongs to a script in this repository "
             "and can be corrected by re-running it. Everything this report labels a "
             "*derivation* artifact — the truncated height z-score of 4.6, the "
             "double-converted head circumference of 4.7, the interval rule behind "
             "the velocity fields of 4.8 — is a property of that local step, not of "
             "the data PPOC sent."),
        Para("Because the augmented layer is derived from the delivered one, the "
             "fields they share should agree exactly. Across all {total:,} joined "
             "visit rows, five of the six do."),  # patient layer follows below
        Table("t-layers", "Shared visit fields, raw against augmented",
              [Column("field", "field"), Column("differs", "rows differing", ",", align="right"),
               Column("share", "share", ".2f", "%", align="right")], rows),
        Para("BMI is the exception, and the disagreement is structured rather than "
             "noisy. {raw_only:,} visits carry a raw `BMI` where the augmented `bmi` "
             "is null, at a median age of {med_age:.2f} years; the augmented layer "
             "withholds BMI below age 2, where a CDC BMI-for-age reference does not "
             "apply, while the raw value is computed inside the source EHR at every "
             "age. A further {aug_only:,} rows go the other way, and {both_differ:,} "
             "carry both values differing by more than 0.01."),
        Para("**The patient layer diverges further, and Part 5 works in it.** "
             "`patients` and `patients_augmented` also share `sex`, `ethnicity` and "
             "the race slots, over {p_total:,} joined patient rows. Sex agrees "
             "exactly; the other two do not, and the disagreement is a great deal "
             "larger than BMI's in relative terms.", role="warning"),
        Table("t-layers-patients", "Shared patient fields, raw against augmented",
              [Column("field", "field"),
               Column("raw_n", "populated, raw", ",", align="right"),
               Column("aug_n", "populated, augmented", ",", align="right"),
               Column("differs", "rows differing", ",", align="right"),
               Column("share", "share", ".2f", "%", align="right"),
               Column("raw_distinct", "distinct, raw", ",", align="right"),
               Column("aug_distinct", "distinct, augmented", ",", align="right")],
              p_rows,
              note="`race_1` stands for the eight race slots, which are cleaned "
                   "the same way."),
        Para("This is a documented transformation rather than a defect: "
             "`docs/patients_augmented.md` records that the augmented layer converts "
             "non-informative responses in `ethnicity` and `race_*` to null. On "
             "`{p_field}` it moves {p_lost:,} patients from a recorded value to a "
             "null and collapses the vocabulary from {p_raw_distinct} categories to "
             "{p_aug_distinct}. The {n_dropped} values that go are {dropped} — every "
             "recorded form of non-response, and nothing else."),
        Para("**Implications for analysis.** Reading `visits.BMI` silently yields "
             "infant BMI values that the augmented layer deliberately suppresses, "
             "and the two layers will not reproduce each other's descriptive "
             "statistics. Choose a layer for a stated reason and record which; do "
             "not mix them within one analysis. The {both_differ:,} rows where both "
             "are present and disagree are small enough to screen individually. On "
             "the patient layer the consequence is sharper: 5.5 reports identity "
             "non-response as its own category and advises keeping it that way, "
             "which is only possible against the delivered `patients` table. In the "
             "augmented layer a declined answer and a question never asked are the "
             "same null, so take identity from `patients` whenever the distinction "
             "carries any weight.", role="implication"),
    ]
    return [f]


@probe("layers.deident", "1.5")
def deident(ctx: Context) -> list[Finding]:
    absent = ["calendar dates", "time of day", "patient names or identifiers",
              "site, practice, department, or facility", "provider or clinician",
              "geography", "free-text notes"]
    checks = list(DEIDENT_CHECKS)
    f = Finding(
        id="layers.deident", part="1.5",
        title="The de-identification envelope",
        values={"n_absent": len(absent), "n_checks": len(checks),
                "cohort_as_of": COHORT_AS_OF},
    )
    f.blocks = [
        Para("`age_in_days` is the only clock. The extract carries no calendar date, "
             "no time of day, no site, practice, provider, or geography, and no free "
             "text from any note. That is stated once here and referenced from Part "
             "2 rather than re-argued at each check it rules out."),
        Table("t-deident", "Checks this extract forecloses, and why",
              [Column("check", "standard check"), Column("why", "why it cannot be run")],
              [{"check": c, "why": w} for c, w in checks]),
        Para("One qualification, because \"no calendar axis\" is easy to overstate: "
             "the cohort itself is pinned to a fixed date and the extract was cut "
             "shortly after it, both given in 1.4. Ages are relative to each child's birth, but the "
             "*window* is fixed and known, which is what makes the recency criterion "
             "in 1.4 a right-censoring rule rather than an unknown.", role="method"),
    ]
    return [f]

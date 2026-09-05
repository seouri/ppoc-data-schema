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
    "labs": ("one row per resulted component of a lab order",
             "lab_order_id + result_line_num", "patients; visits (partial)"),
    "medications": ("one row per medication order or historical record",
                    "med_record_id", "patients; visits (partial)"),
    "problem_list": ("one row per problem-list entry", "problem_list_id", "patients"),
    "referrals": ("one row per referral order", "referral_id",
                  "patients; visits (partial)"),
}

# Fields carried by both the raw and the augmented visit layer under the same
# meaning. `bmi` is compared case-insensitively: the raw column is `BMI`.
SHARED = [("height_in", "height_in"), ("weight_oz", "weight_oz"),
          ("head_circ_cm", "head_circ_cm"), ("encounter_type", "encounter_type"),
          ("age_in_days", "age_in_days"), ("BMI", "bmi")]


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
    f = Finding(
        id="layers.resources", part="1.2", title="Resource map, grain, and keys",
        values={"n": len(rows),
                "cols": sum(r["columns"] for r in rows),
                "delivered": sum(1 for r in rows if r["source"] == "PPOC"),
                "generated": sum(1 for r in rows if r["source"] != "PPOC")},
    )
    f.blocks = [
        Para("The package is {n} tables carrying {cols} columns between them, but "
             "they do not share a provenance: {delivered} were delivered by PPOC and "
             "{generated} are generated locally (1.3). Grain matters more than row "
             "count here: three of the resources are keyed on something other than "
             "the patient or the visit, and one of them needs two columns to be "
             "unique."),
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

    f = Finding(
        id="layers.agreement", part="1.3",
        title="Two layers with different provenance",
        values={"total": total, "raw_only": raw_only, "aug_only": aug_only,
                "both_differ": both_differ, "med_age": med_age,
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
             "visit rows, five of the six do."),
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
        Para("**Implications for analysis.** Reading `visits.BMI` silently yields "
             "infant BMI values that the augmented layer deliberately suppresses, "
             "and the two layers will not reproduce each other's descriptive "
             "statistics. Choose a layer for a stated reason and record which; do "
             "not mix them within one analysis. The {both_differ:,} rows where both "
             "are present and disagree are small enough to screen individually.",
             role="implication"),
    ]
    return [f]


@probe("layers.deident", "1.5")
def deident(ctx: Context) -> list[Finding]:
    absent = ["calendar dates", "time of day", "patient names or identifiers",
              "site, practice, department, or facility", "provider or clinician",
              "geography", "free-text notes"]
    checks = [
        ("Duplicate-patient detection", "no name, birth date, or linkage key survives"),
        ("Batch-entry clustering", "ages are integer days; there is no time of day"),
        ("System downtime gaps", "no calendar axis on which a void could appear"),
        ("Missingness by site or provider", "no such column exists in any resource"),
        ("Calendar trend breaks and policy shifts", "no calendar axis"),
        ("Copy-forward of note text", "no note text is included"),
        ("Documentation timing", "no timestamps"),
    ]
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
             "the cohort itself is pinned to {cohort_as_of} and the extract was cut "
             "shortly after. Ages are relative to each child's birth, but the "
             "*window* is fixed and known, which is what makes the recency criterion "
             "in 1.4 a right-censoring rule rather than an unknown.", role="method"),
    ]
    return [f]

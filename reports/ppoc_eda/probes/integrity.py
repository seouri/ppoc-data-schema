"""Part 3.1-3.3 — keys and grain, referential integrity, and the age axis."""

from __future__ import annotations

from ..context import RESOURCES, SUPPRESS_BELOW, Context
from ..findings import Artifact, Column, Finding, Para, Table, probe

KEYS = [
    ("patients", "patient_id"), ("patients_augmented", "patient_id"),
    ("visits", "visit_id"), ("visits_augmented", "visit_id"),
    ("medications", "med_record_id"), ("problem_list", "problem_list_id"),
    ("referrals", "referral_id"),
]
LINKED = ["labs", "medications", "referrals"]

#: The labs key, which no delivery document declares: `docs/labs.md` gives the
#: grain as one row per result component and lists no composite key, and the data
#: description's "Key Columns" for labs omit `result_line_num` entirely. So it is
#: reconstructed here, and the reconstruction is minimal — order plus line is
#: unique on its own, and the component column adds nothing. The superkey is
#: measured beside it because the report used to call all three necessary.
LAB_KEY = ["lab_order_id", "result_line_num"]
LAB_SUPERKEY = ["lab_order_id", "result_component_name", "result_line_num"]
#: The combination an analysis reaches for instead, which is not a key.
LAB_TRAP = ["lab_order_id", "result_component_name"]

ORDERING = [
    ("Lab result age earlier than lab order age", "labs",
     "lab_result_date_age_in_days < lab_order_date_age_in_days",
     "lab_result_date_age_in_days IS NOT NULL AND lab_order_date_age_in_days IS NOT NULL"),
    ("Medication start age earlier than order age", "medications",
     "med_start_date_age_in_days < med_order_date_age_in_days",
     "med_start_date_age_in_days IS NOT NULL AND med_order_date_age_in_days IS NOT NULL"),
    ("Medication end age earlier than start age", "medications",
     "med_end_date_age_in_days < med_start_date_age_in_days",
     "med_end_date_age_in_days IS NOT NULL AND med_start_date_age_in_days IS NOT NULL"),
    ("Problem resolved age earlier than noted age", "problem_list",
     "resolved_date_age_in_days < noted_date_age_in_days",
     "resolved_date_age_in_days IS NOT NULL AND noted_date_age_in_days IS NOT NULL"),
    ("Problem noted before birth", "problem_list",
     "noted_date_age_in_days < 0", "noted_date_age_in_days IS NOT NULL"),
    ("Lab ordered before birth", "labs",
     "lab_order_date_age_in_days < 0", "lab_order_date_age_in_days IS NOT NULL"),
    ("Medication ordered before birth", "medications",
     "med_order_date_age_in_days < 0", "med_order_date_age_in_days IS NOT NULL"),
    ("Visit recorded before birth", "visits", "age_in_days < 0", "TRUE"),
]


@probe("integrity.keys", "3.1")
def keys(ctx: Context) -> list[Finding]:
    rows = []
    for table, key in KEYS:
        n, distinct = ctx.one(f"SELECT count(*), count(DISTINCT {key}) FROM {table}")
        rows.append({"resource": table, "key": key, "rows": n,
                     "distinct": distinct, "unique": "yes" if n == distinct else "NO"})
    # Same two columns as every other row: the table's rows, and its distinct
    # keys. The labs row used to report the group count and groups-minus-duplicates
    # instead, which coincide with these only while the key holds.
    lab_rows = ctx.scalar("SELECT count(*) FROM labs")
    lab_distinct = ctx.scalar(
        f"SELECT count(*) FROM (SELECT 1 FROM labs GROUP BY {', '.join(LAB_KEY)})")
    rows.append({"resource": "labs", "key": " + ".join(LAB_KEY),
                 "rows": lab_rows, "distinct": lab_distinct,
                 "unique": "yes" if lab_rows == lab_distinct else "NO"})
    # What the redundant column and the tempting wrong join actually cost.
    lab_super = ctx.scalar(
        f"SELECT count(*) FROM (SELECT 1 FROM labs "
        f"GROUP BY {', '.join(LAB_SUPERKEY)})")
    trap_groups, trap_dupes = ctx.one(
        f"SELECT count(*), count(*) FILTER (WHERE c > 1) FROM ("
        f"  SELECT count(*) AS c FROM labs GROUP BY {', '.join(LAB_TRAP)})")

    vday, vdup_days, vdup_visits = ctx.one(
        "SELECT count(*), sum(CASE WHEN c > 1 THEN 1 ELSE 0 END), "
        "       sum(CASE WHEN c > 1 THEN c ELSE 0 END) FROM ("
        "  SELECT count(*) AS c FROM visits GROUP BY patient_id, age_in_days)")

    f = Finding(
        id="integrity.keys", part="3.1", title="Keys, grain, and uniqueness",
        values={"vday": vday, "vdup_days": vdup_days, "vdup_visits": vdup_visits,
                "n_declared": len(KEYS),
                "lab_key": " + ".join(f"`{c}`" for c in LAB_KEY),
                "lab_extra": f"`{LAB_SUPERKEY[1]}`",
                "lab_distinct": lab_distinct, "lab_super": lab_super,
                "trap_dupes": trap_dupes, "trap_groups": trap_groups,
                "vdup_share": 100.0 * vdup_days / vday,
                "vvisit_share": 100.0 * vdup_visits / ctx.scalar(
                    "SELECT count(*) FROM visits")},
        artifact=Artifact(
            name="A patient-day can carry more than one visit",
            kind="capture",
            scale="{vdup_days:,} patient-days holding {vdup_visits:,} visits, "
                  "the rows 3.8 finds disagreeing and four Part 4 sections "
                  "deduplicate",
            recoverable="Partly — define an explicit tie rule before ordering by age",
        ),
    )
    f.blocks = [
        Para("All {n_declared} single-column primary keys the delivery documents "
             "declare hold exactly. Labs has no declared composite key — the data "
             "dictionary gives its grain as one row per result component and names "
             "no key — so the one below is reconstructed here, and it is minimal: "
             "{lab_key} is unique on its own across all {lab_distinct:,} rows, and "
             "adding {lab_extra} changes nothing ({lab_super:,} groups either way)."),
        Para("The combination to avoid is the one an analysis reaches for instead. "
             "Joining on the order and the component *without* the line number "
             "collapses to {trap_groups:,} groups, {trap_dupes:,} of which hold more "
             "than one row, so that join multiplies rows rather than matching them. "
             "3.6 measures how far the duplicated lines disagree and what the source "
             "system says produces them."),
        Table("t-keys", "Primary keys, measured",
              [Column("resource", "resource"), Column("key", "key"),
               Column("rows", "rows", ",", align="right"),
               Column("distinct", "distinct keys", ",", align="right"),
               Column("unique", "unique")], rows,
              note="Every row compares the table's rows against its distinct key "
                   "values. The labs key is the report's own reconstruction; the "
                   "other {n_declared} come from the delivery documents."),
        Para("What is *not* a key is the combination a longitudinal analysis "
             "reaches for first. {vdup_days:,} patient-days ({vdup_share:.2f}% of "
             "{vday:,}) carry more than one visit, covering {vdup_visits:,} visit "
             "rows ({vvisit_share:.2f}% of all visits). `age_in_days` is therefore "
             "not unique within a patient."),
        Para("**Implications for analysis.** Any trajectory ordered by age alone has "
             "ties, and any window function partitioned by patient and ordered by "
             "age will resolve them arbitrarily unless you say how. Decide whether "
             "to take the first row, the mean, or the non-null value, and apply it "
             "before the analysis rather than inside it — 3.8 measures how far the "
             "two values sit apart on the days that carry two, which is what makes "
             "that choice consequential rather than arbitrary.", role="implication"),
    ]
    return [f]


@probe("integrity.links", "3.2")
def links(ctx: Context) -> list[Finding]:
    rows = []
    for table in LINKED:
        total = ctx.scalar(f"SELECT count(*) FROM {table}")
        have = ctx.scalar(f"SELECT count(visit_id) FROM {table}")
        unresolved = ctx.scalar(
            f"SELECT count(*) FROM {table} t WHERE t.visit_id IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM visits v WHERE v.visit_id = t.visit_id)")
        rows.append({
            "resource": table, "rows": total, "null_ids": total - have,
            "unresolved": unresolved,
            "unresolved_share": 100.0 * unresolved / have if have else 0.0,
        })

    # The first sentence claims the whole package, so measure the whole package
    # rather than the three resources that happen to carry a visit_id too.
    with_patient = [t for t in RESOURCES
                    if t != "patients" and "patient_id" in ctx.columns(t)]
    orphans = {t: ctx.scalar(
        f"SELECT count(*) FROM {t} t WHERE NOT EXISTS "
        "(SELECT 1 FROM patients p WHERE p.patient_id = t.patient_id)")
        for t in with_patient}
    no_visit_col = [t for t in RESOURCES
                    if t not in ("patients", "patients_augmented", "visits",
                                 "visits_augmented")
                    and "visit_id" not in ctx.columns(t)]

    # Is the unresolved share random? Medications carry the one field that makes
    # the "outside" explanation checkable, so check it rather than assert it.
    split = ctx.q("""
        SELECT med_record_type, count(*),
               count(*) FILTER (WHERE NOT EXISTS
                   (SELECT 1 FROM visits v WHERE v.visit_id = m.visit_id))
        FROM medications m GROUP BY 1 ORDER BY 1""")
    split_rows = [{"kind": k, "rows": n, "unresolved": u,
                   "share": 100.0 * u / n} for k, n, u in split]
    f = Finding(
        id="integrity.links", part="3.2",
        title="Referential integrity and cross-resource linkage",
        values={"worst": max(r["unresolved_share"] for r in rows),
                "n_checked": len(with_patient), "orphans": sum(orphans.values()),
                "no_visit": ", ".join(f"`{t}`" for t in no_visit_col),
                "ext_share": next(r["share"] for r in split_rows
                                  if r["kind"] == "External"),
                "int_share": next(r["share"] for r in split_rows
                                  if r["kind"] == "Internal"),
                "int_unres": next(r["unresolved"] for r in split_rows
                                  if r["kind"] == "Internal"),
                "labs_null": next(r["null_ids"] for r in rows
                                  if r["resource"] == "labs")},
        artifact=Artifact(
            name="Populated visit_id that resolves to no visit",
            kind="linkage",
            scale="up to {worst:.0f}% of populated values in a resource",
            recoverable="No — treat visit linkage as partial by design",
        ),
    )
    f.blocks = [
        Para("`patient_id` resolves everywhere, measured on every one of the "
             "{n_checked} resources that carry it: {orphans} rows across all of "
             "them reference a patient who is not in `patients`. `visit_id` does "
             "not, and the shortfall is large enough that treating it as a complete "
             "foreign key will quietly drop or duplicate rows."),
        Table("t-links", "Visit linkage by resource",
              [Column("resource", "resource"), Column("rows", "rows", ",", align="right"),
               Column("null_ids", "visit_id null", ",", align="right"),
               Column("unresolved", "populated but unresolved", ",", align="right"),
               Column("unresolved_share", "share of populated", ".2f", "%",
                      align="right")],
              rows,
              note="The null column is a count rather than a share, because as a "
                   "share the two cases were indistinguishable: labs carries "
                   "{labs_null:,} rows with no `visit_id` at all and medications "
                   "carries none, and at two decimal places both rounded to zero. "
                   "A null cannot be joined and does not pretend to be joinable, "
                   "which makes it the one part of this that is not silent."),
        Para("The table covers every resource carrying a `visit_id`. {no_visit} "
             "carries none, so a problem-list entry cannot be tied to an encounter "
             "under any join — not partially, as above, but not at all. That "
             "matters for anyone building a per-visit feature from diagnoses; 5.1 "
             "works from the constraint and this is where it is measured.",
             role="warning"),
        Para("This is documented behaviour rather than corruption. The data "
             "dictionary states for each of these resources that the visit link "
             "\"may not match to all\" when the order was placed or the record "
             "documented outside a visit. The trap is that the column is populated "
             "on nearly every row, so a required-looking key silently fails to "
             "join.", role="body"),
        Para("**Implications for analysis.** Join to visits with an explicit outer "
             "join and count what fails, rather than an inner join that hides the "
             "loss. Anything computed per visit — encounter type, visit-level "
             "anthropometrics — is unavailable for the unresolved share, and that "
             "share is not random. Medications carry the one field that makes the "
             "dictionary's explanation checkable, and it does not fall the way the "
             "explanation suggests: an externally documented record — 5.3's outside "
             "or historical medication — is unresolved {ext_share:.1f}% of the "
             "time, while an order placed by a practice clinician is unresolved "
             "{int_share:.1f}% of the time, {int_unres:,} rows. Whatever produces "
             "the shortfall, it lands on practice orders rather than on outside "
             "documentation, so filtering to internal records selects for the "
             "problem instead of away from it. The two are not the same "
             "distinction — an internal phone refill has no encounter either — "
             "which is why the mechanism is left as the dictionary states it and "
             "only its incidence is reported here.", role="implication"),
    ]
    return [f]


@probe("integrity.age", "3.3")
def age_axis(ctx: Context) -> list[Finding]:
    rows = []
    for label, table, bad, denom in ORDERING:
        checked = ctx.scalar(f"SELECT count(*) FROM {table} WHERE {denom}")
        violations = ctx.scalar(f"SELECT count(*) FROM {table} WHERE {denom} AND {bad}")
        rows.append({
            "check": label, "violations": ctx.suppress(violations),
            "checked": checked,
            "share": (100.0 * violations / checked) if checked and
                     ctx.suppress(violations) is not None else None,
        })
    f = Finding(
        id="integrity.age", part="3.3",
        title="Age-axis consistency and impossible sequences",
        values={"suppress": SUPPRESS_BELOW},
        artifact=Artifact(
            name="Age fields that violate their own ordering",
            kind="capture",
            scale="lab result before order, and medication start before order",
            recoverable="No — do not treat differences between them as durations",
        ),
    )
    f.blocks = [
        Para("Age in days is the only clock, so ordering violations within a "
             "resource are visible directly. Counts below {suppress} are suppressed."),
        Table("t-age", "Ordering and range checks",
              [Column("check", "check"),
               Column("violations", "violating rows", ",", align="right"),
               Column("checked", "rows checked", ",", align="right"),
               Column("share", "share", ".3f", "%", align="right")], rows,
              note="An em dash in the violating-rows column means the count is "
                   "nonzero but below the suppression threshold."),
        Para("The lab and medication violations are the substantial ones, and both "
             "are documented at source. For a historically documented medication "
             "the order date is the date the record was *written*, not when the "
             "drug was started, and a charted approximation such as a month with no "
             "day is stored as the first of that month. End dates may sit in the "
             "future while a medication is active. Lab result and order ages derive "
             "from different source timestamps.", role="body"),
        Para("**Implications for analysis.** Differences between two age fields in "
             "these resources are not reliable durations. Where you need an "
             "interval, take it from a single field across rows rather than between "
             "two fields on one row, and exclude historically documented medication "
             "records from any start-to-end calculation.", role="implication"),
    ]
    return [f]

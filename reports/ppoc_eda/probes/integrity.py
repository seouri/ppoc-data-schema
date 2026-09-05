"""Part 3.1-3.3 — keys and grain, referential integrity, and the age axis."""

from __future__ import annotations

from ..context import SUPPRESS_BELOW, Context
from ..findings import Artifact, Column, Finding, Para, Table, probe

KEYS = [
    ("patients", "patient_id"), ("patients_augmented", "patient_id"),
    ("visits", "visit_id"), ("visits_augmented", "visit_id"),
    ("medications", "med_record_id"), ("problem_list", "problem_list_id"),
    ("referrals", "referral_id"),
]
LINKED = ["labs", "medications", "referrals"]

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
    lab_groups, lab_dupes = ctx.one(
        "SELECT count(*), sum(CASE WHEN c > 1 THEN 1 ELSE 0 END) FROM ("
        "  SELECT count(*) AS c FROM labs "
        "  GROUP BY lab_order_id, result_component_name, result_line_num)")
    rows.append({"resource": "labs", "key": "lab_order_id + component + line",
                 "rows": lab_groups, "distinct": lab_groups - (lab_dupes or 0),
                 "unique": "yes" if not lab_dupes else "NO"})

    vday, vdup_days, vdup_visits = ctx.one(
        "SELECT count(*), sum(CASE WHEN c > 1 THEN 1 ELSE 0 END), "
        "       sum(CASE WHEN c > 1 THEN c ELSE 0 END) FROM ("
        "  SELECT count(*) AS c FROM visits GROUP BY patient_id, age_in_days)")

    f = Finding(
        id="integrity.keys", part="3.1", title="Keys, grain, and uniqueness",
        values={"vday": vday, "vdup_days": vdup_days, "vdup_visits": vdup_visits,
                "vdup_share": 100.0 * vdup_days / vday,
                "vvisit_share": 100.0 * vdup_visits / ctx.scalar(
                    "SELECT count(*) FROM visits")},
        artifact=Artifact(
            name="A patient-day can carry more than one visit",
            kind="capture",
            scale="{vdup_days:,} patient-days holding {vdup_visits:,} visits",
            recoverable="Partly — define an explicit tie rule before ordering by age",
        ),
    )
    f.blocks = [
        Para("Every declared primary key holds. The labs resource needs all three "
             "of its declared columns to be unique, which is worth stating because "
             "joining on order and component alone will multiply rows."),
        Table("t-keys", "Declared keys, measured",
              [Column("resource", "resource"), Column("key", "key"),
               Column("rows", "rows", ",", align="right"),
               Column("distinct", "distinct keys", ",", align="right"),
               Column("unique", "unique")], rows),
        Para("What is *not* a key is the combination a longitudinal analysis "
             "reaches for first. {vdup_days:,} patient-days ({vdup_share:.2f}% of "
             "{vday:,}) carry more than one visit, covering {vdup_visits:,} visit "
             "rows ({vvisit_share:.2f}% of all visits). `age_in_days` is therefore "
             "not unique within a patient."),
        Para("**Implications for analysis.** Any trajectory ordered by age alone has "
             "ties, and any window function partitioned by patient and ordered by "
             "age will resolve them arbitrarily unless you say how. Decide whether "
             "to take the first row, the mean, or the non-null value, and apply it "
             "before the analysis rather than inside it.", role="implication"),
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
        orphan_pat = ctx.scalar(
            f"SELECT count(*) FROM {table} t WHERE NOT EXISTS "
            "(SELECT 1 FROM patients p WHERE p.patient_id = t.patient_id)")
        rows.append({
            "resource": table, "rows": total,
            "missing": 100.0 * (total - have) / total,
            "unresolved": unresolved,
            "unresolved_share": 100.0 * unresolved / have if have else 0.0,
            "orphan_patients": orphan_pat,
        })
    f = Finding(
        id="integrity.links", part="3.2",
        title="Referential integrity and cross-resource linkage",
        values={"worst": max(r["unresolved_share"] for r in rows)},
        artifact=Artifact(
            name="Populated visit_id that resolves to no visit",
            kind="linkage",
            scale="up to {worst:.0f}% of populated values in a resource",
            recoverable="No — treat visit linkage as partial by design",
        ),
    )
    f.blocks = [
        Para("`patient_id` resolves everywhere. `visit_id` does not, and the "
             "shortfall is large enough that treating it as a complete foreign key "
             "will quietly drop or duplicate rows."),
        Table("t-links", "Visit linkage by resource",
              [Column("resource", "resource"), Column("rows", "rows", ",", align="right"),
               Column("missing", "visit_id null", ".2f", "%", align="right"),
               Column("unresolved", "populated but unresolved", ",", align="right"),
               Column("unresolved_share", "share of populated", ".2f", "%", align="right"),
               Column("orphan_patients", "unresolved patient_id", ",", align="right")],
              rows),
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
             "share is not random: it concentrates in orders placed outside "
             "encounters.", role="implication"),
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

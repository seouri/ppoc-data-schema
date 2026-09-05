"""Part 2 — the general EHR EDA checklist, mapped against this extract."""

from __future__ import annotations

from ..context import Context
from ..findings import Column, Finding, Para, Table, probe

COVERED, PARTIAL, NA = "covered", "partial", "not applicable"

# (checklist section, item, status, where or why)
ITEMS = [
    ("0 Provenance", "Extraction window", COVERED,
     "Cohort and extract dates recovered from the delivery documents — 1.4"),
    ("0 Provenance", "Inclusion/exclusion logic", COVERED,
     "The full four-step funnel — 1.4"),
    ("0 Provenance", "Vendor, version, migration events", COVERED,
     "Epic against converted legacy records — 3.7"),
    ("0 Provenance", "Data dictionary present", COVERED,
     "Committed under docs/, reconciled field by field — 1.1"),
    ("0 Provenance", "Raw vs CDM vs custom extract", COVERED,
     "A custom extract plus a derived augmentation layer — 1.3"),
    ("1 Structural", "Row and table counts", COVERED,
     "Against the manifest and the vendor's own counts — 1.1"),
    ("1 Structural", "Primary key uniqueness", COVERED, "All eight resources — 3.1"),
    ("1 Structural", "Referential integrity", COVERED, "3.2"),
    ("1 Structural", "Duplicate patient detection", NA,
     "No name, birth date, or linkage key survives de-identification — 1.5"),
    ("1 Structural", "Schema drift", COVERED,
     "Live schema against the dictionary; three documented fields absent — 1.1"),
    ("1 Structural", "Grain per table", COVERED,
     "Including that patient and age is not unique in visits — 3.1"),
    ("2 Temporal", "Timestamp semantics", COVERED, "3.3"),
    ("2 Temporal", "Impossible sequences", COVERED, "3.3"),
    ("2 Temporal", "Batch-entry clustering", NA,
     "Ages are integer days; there is no time of day — 1.5"),
    ("2 Temporal", "System downtime gaps", NA, "No calendar axis — 1.5"),
    ("2 Temporal", "Coding or vendor transition", PARTIAL,
     "Epic against converted is computable; ICD-9 to ICD-10 is not, without dates"),
    ("2 Temporal", "Age sanity", COVERED, "3.3"),
    ("3 Missingness", "Missingness per field", COVERED, "3.4 and the field index"),
    ("3 Missingness", "Missingness pattern", COVERED, "By age, sex, and encounter — 3.4"),
    ("3 Missingness", "Sentinel values", COVERED, "3.5"),
    ("3 Missingness", "Not measured vs measured negative", COVERED,
     "Two fields whose nulls carry meaning — 3.5"),
    ("3 Missingness", "Missingness by site or provider", NA,
     "No site, department, or provider column exists — 1.5"),
    ("4 Distributional", "Univariate distributions", COVERED, "4.3"),
    ("4 Distributional", "Unit inconsistencies", COVERED, "4.3 and 4.4"),
    ("4 Distributional", "Digit preference and rounding", COVERED, "4.2"),
    ("4 Distributional", "Categorical value counts", COVERED, "3.6"),
    ("4 Distributional", "Outlier detection", COVERED,
     "Bounds reported before any exclusion is recommended — 4.3"),
    ("4 Distributional", "Cross-field plausibility", COVERED,
     "Raw against augmented layers — 1.3"),
    ("5 Terminology", "Code system vintage", COVERED, "3.6"),
    ("5 Terminology", "Granularity consistency", COVERED, "3.6"),
    ("5 Terminology", "Problem list staleness", COVERED, "3.5"),
    ("5 Terminology", "Free text vs structured", COVERED,
     "Laboratory result values are semi-structured text — 3.6"),
    ("5 Terminology", "Local or custom codes", COVERED, "3.6"),
    ("6 Workflow", "Copy-forward detection", PARTIAL,
     "Detectable on measurements; no note text is included"),
    ("6 Workflow", "Template or boilerplate detection", NA, "No note text — 1.5"),
    ("6 Workflow", "Documentation timing", NA, "No timestamps — 1.5"),
    ("6 Workflow", "Order/result reconciliation", COVERED, "3.6"),
    ("7 Population", "Cohort representativeness", PARTIAL,
     ("The cohort is not representative and 1.4 says exactly how; no external "
     "benchmark ships with this repository")),
    ("7 Population", "Encounter type mix", COVERED, "3.7"),
    ("7 Population", "Follow-up time distribution", COVERED, "4.1"),
    ("7 Population", "Site or provider volume", NA, "No such field — 1.5"),
    ("8 Longitudinal", "Calendar trend breaks", NA,
     ("No calendar axis. Age-axis profiles are reported instead and are not the "
     "same thing — 1.5")),
    ("8 Longitudinal", "Guideline or policy shift", NA, "Requires calendar time — 1.5"),
    ("8 Longitudinal", "Vendor changeover effects", PARTIAL,
     "The Epic against converted contrast only"),
]


@probe("coverage.map", "2.1")
def coverage(ctx: Context) -> list[Finding]:
    counts = {s: sum(1 for *_, st, _ in ITEMS if st == s) for s in (COVERED, PARTIAL, NA)}
    rows = [{"section": sec, "item": item, "status": status, "note": note}
            for sec, item, status, note in ITEMS]
    na_rows = [r for r in rows if r["status"] == NA]
    f = Finding(
        id="coverage.map", part="2.1",
        title="The checklist, item by item",
        values={"total": len(ITEMS), "covered": counts[COVERED],
                "partial": counts[PARTIAL], "na": counts[NA]},
    )
    f.blocks = [
        Para("This part exists so that nobody has to wonder whether a standard check "
             "was skipped or was impossible. Of {total} items in the general EHR "
             "exploratory-analysis checklist, {covered} are covered here, {partial} "
             "are partially covered, and {na} cannot be run against this extract at "
             "all."),
        Table("t-coverage", "Checklist coverage",
              [Column("section", "checklist section"), Column("item", "item"),
               Column("status", "status"), Column("note", "where, or why not")], rows),
        Para("The not-applicable list is the part worth reading before you start. "
             "Every entry is a consequence of de-identification or of what the "
             "extract simply does not carry, and no amount of analysis recovers any "
             "of them."),
        Table("t-coverage-na", "Checks this extract cannot support",
              [Column("item", "check"), Column("note", "why")], na_rows),
        Para("**Implications for analysis.** Treat the second table as a design "
             "constraint rather than a gap to work around. A protocol that depends "
             "on provider variation, time-of-day effects, calendar trends, or "
             "deceased patients cannot be run on this extract, and discovering that "
             "after cohort construction is expensive.", role="implication"),
    ]
    return [f]

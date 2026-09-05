"""Part 1 — what is in the snapshot, how it was built, and what it cannot say."""

from __future__ import annotations

from ..context import COHORT_AS_OF, EXTRACT_DATE, RESOURCES, Context
from ..findings import Artifact, Column, Figure, Finding, Para, Table, probe

# Counts PPOC stated in the delivery documents committed under docs/. They are
# used as an independent reconciliation target, never as a substitute for
# measurement: every one of them is recomputed from the bundle below.
VENDOR_ROWS = {
    "patients": 250_588, "visits": 6_494_473, "problem_list": 1_709_584,
    "labs": 17_230_681, "medications": 3_823_049, "referrals": 349_827,
}
VENDOR_PATIENTS = {
    "visits": 250_588, "problem_list": 238_823, "labs": 247_271,
    "medications": 236_323, "referrals": 138_071,
}
VENDOR_LAB_ORDERS = 6_578_838

# The cohort funnel, from the extract diagram and the cohort workbook.
FUNNEL = [
    ("On the PPOC active-patient registry", 437_996, ""),
    (f"Age under 18 as of {COHORT_AS_OF}", 361_326, "76,670 excluded"),
    ("Excluding 2 practices that declined participation", 352_017, "9,309 excluded"),
    (("At least 5 growth measurements of one type on distinct dates, spanning "
      "over 1095 days, last measurement within 400 days"), 290_175, "61,842 excluded"),
    ("Carrying no rare diagnosis, medication, or lab", 250_588, "39,587 excluded"),
]
#: Short stage names for the funnel figure; the table carries the full criteria.
FUNNEL_SHORT = ("Active registry", "Age under 18", "Participating practices",
                "Growth-measurement rule", "No rare code")
RARE = [
    ("ICD-10 diagnosis codes", 30_493, 18_604),
    ("Simple generic medications", 2_503, 1_391),
    ("Lab procedures", 13_402, 9_621),
]


@probe("snapshot.identity", "1.1")
def identity(ctx: Context) -> list[Finding]:
    declared = ctx.declared_rows()
    rows, mismatches = [], 0
    for name in RESOURCES:
        actual = ctx.scalar(f"SELECT count(*) FROM {name}")
        rows.append({
            "resource": name,
            "rows": actual,
            "manifest": declared.get(name),
            "vendor": VENDOR_ROWS.get(name),
            "agrees": "yes" if actual == declared.get(name, actual)
                      and actual == VENDOR_ROWS.get(name, actual) else "NO",
        })
        mismatches += rows[-1]["agrees"] == "NO"

    lab_orders = ctx.scalar("SELECT count(DISTINCT lab_order_id) FROM labs")
    pat_rows = []
    for name, expected in VENDOR_PATIENTS.items():
        actual = ctx.scalar(f"SELECT count(DISTINCT patient_id) FROM {name}")
        pat_rows.append({"resource": name, "patients": actual, "vendor": expected,
                         "agrees": "yes" if actual == expected else "NO"})
        mismatches += actual != expected
    mismatches += lab_orders != VENDOR_LAB_ORDERS

    f = Finding(
        id="snapshot.identity", part="1.1",
        title="Package identity and integrity",
        values={
            "package": ctx.package.get("name", "unknown"),
            "version": ctx.package.get("version", "unknown"),
            "snapshot": ctx.snapshot,
            "digest": ctx.digest,
            "lab_orders": lab_orders,
            "vendor_lab_orders": VENDOR_LAB_ORDERS,
            "mismatches": mismatches,
            "extract_date": EXTRACT_DATE,
            "cohort_as_of": COHORT_AS_OF,
        },
    )
    f.blocks = [
        Para("Everything in this report was computed from the typed DuckDB bundle of "
             "package `{package}` {version}, snapshot `{snapshot}`, sha256 "
             "`{digest}`. The bundle is opened read-only and is never copied into "
             "this repository."),
        Para("Three independent sources state how large this extract should be: the "
             "bundle manifest, the PPOC delivery documents committed under `docs/`, "
             "and the data itself. They are reconciled here before any other figure "
             "is computed, so that a bundle drawn from a different extract would be "
             "visible rather than silently profiled."),
        Table("t-rowcounts", "Row counts, measured against both declared sources",
              [Column("resource", "resource"), Column("rows", "measured", ",", align="right"),
               Column("manifest", "bundle manifest", ",", align="right"),
               Column("vendor", "PPOC document", ",", align="right"),
               Column("agrees", "agrees")], rows),
        Table("t-patientcounts", "Distinct patients per resource, against the PPOC counts",
              [Column("resource", "resource"),
               Column("patients", "measured", ",", align="right"),
               Column("vendor", "PPOC document", ",", align="right"),
               Column("agrees", "agrees")], pat_rows),
        Para("The lab resource carries a second stated figure: {vendor_lab_orders:,} "
             "distinct lab orders behind the resulted components. The bundle holds "
             "{lab_orders:,}. Across every count above, {mismatches} disagree.",
             role="body"),
    ]
    return [f]


@probe("snapshot.cohort", "1.4")
def cohort(ctx: Context) -> list[Finding]:
    final = ctx.scalar("SELECT count(*) FROM patients")
    funnel_rows = [{"step": i, "criterion": c, "remaining": n, "excluded": x}
                   for i, (c, n, x) in enumerate(FUNNEL)]
    rare_rows = [{"vocabulary": v, "total": t, "rare": r, "share": 100.0 * r / t}
                 for v, t, r in RARE]

    f = Finding(
        id="snapshot.cohort", part="1.4",
        title="How this cohort was built",
        values={
            "registry": FUNNEL[0][1],
            "final": FUNNEL[-1][1],
            "measured_final": final,
            "cohort_as_of": COHORT_AS_OF,
            "extract_date": EXTRACT_DATE,
            "dx_share": 100.0 * RARE[0][2] / RARE[0][1],
            "med_share": 100.0 * RARE[1][2] / RARE[1][1],
            "lab_share": 100.0 * RARE[2][2] / RARE[2][1],
        },
        artifact=Artifact(
            name="Cohort selected on growth-measurement density and code rarity",
            kind="selection",
            scale="{registry:,} registry members reduced to {final:,}; "
                  "{dx_share:.0f}% of diagnosis codes, {med_share:.0f}% of "
                  "medications and {lab_share:.0f}% of lab procedures removed "
                  "with their patients",
            recoverable="No — the excluded patients are not in this extract",
        ),
    )
    f.blocks = [
        Para("This is the most consequential section of the report, because it "
             "describes a property of the data that no field exposes and that no "
             "amount of analysis can recover. The {final:,} patients here are what "
             "remains after four successive exclusions applied by PPOC to an "
             "active-patient registry of {registry:,}. The final count reconciles "
             "against the delivered data exactly: {measured_final:,} patient rows."),
        Figure("fig-funnel", "Cohort construction, registry to delivered extract",
               "funnel",
               {"steps": [{"label": lab, "value": n}
                          for lab, (_, n, _) in zip(FUNNEL_SHORT, FUNNEL, strict=True)]},
               alt="A funnel narrowing from 437,996 registry members to 250,588."),
        Table("t-funnel", "The four exclusions",
              [Column("step", "step", align="right"), Column("criterion", "criterion"),
               Column("excluded", "excluded"),
               Column("remaining", "remaining", ",", align="right")], funnel_rows),
        Para("\"Active\" on that registry means living status alive, not flagged as a "
             "test or inactive record, an active PPOC primary-care association, and "
             "either a visit in the last three years or one scheduled in the next "
             "fifteen months. The cohort is pinned to {cohort_as_of} and the extract "
             "was cut on {extract_date}.", role="body"),
        Para("The fourth exclusion is the one most likely to be missed, because it "
             "removed *patients* rather than codes. A diagnosis, medication, or lab "
             "occurring fewer than 11 times in the data set was classed rare, and "
             "every patient carrying one was dropped.", role="body"),
        Table("t-rare", "What the rarity exclusion removed",
              [Column("vocabulary", "vocabulary"),
               Column("total", "distinct values", ",", align="right"),
               Column("rare", "classed rare", ",", align="right"),
               Column("share", "share", ".0f", "%", align="right")], rare_rows),
        Para("**Implications for analysis.** Rare conditions, rare exposures and "
             "uncommon labs are absent by construction, not merely sparse: a study "
             "of any of them returns a confident low rate rather than an obviously "
             "missing population. {dx_share:.0f}% of diagnosis codes, "
             "{med_share:.0f}% of medications and {lab_share:.0f}% of lab procedures "
             "left with their patients. Because the registry requires living status "
             "alive, there are no deceased patients and mortality is not an "
             "available outcome. Because entry required at least five growth "
             "measurements, trajectory richness is an entry criterion and not a "
             "finding about pediatric care. And because the last measurement had to "
             "fall within 400 days of the cohort date, the panel is right-censored "
             "by design. No frequency in this extract is a population prevalence.",
             role="implication"),
        Para("Two ambiguities in the source documents are recorded rather than "
             "silently resolved. The cohort workbook describes the under-three "
             "exemption as applying to the span requirement for children who already "
             "have five measurements, while the extract diagram describes it as age "
             "under three with at least one measurement. The same two documents give "
             "the rarity threshold as \"fewer than 11 occurrences\" and \"under 10 "
             "patients\".", role="method"),
    ]
    return [f]

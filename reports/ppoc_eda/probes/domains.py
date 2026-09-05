"""Part 5 — diagnoses, labs, medications, referrals, and recorded identity.

Descriptive inventories of the clinical resources. Each is a description of what
was *recorded*, never of what was present in the children: a code is a code, a
referral is an action, and 1.4 explains why no frequency here is a prevalence.
"""

from __future__ import annotations

from ..context import Context
from ..findings import Column as C
from ..findings import Figure, Finding, Para, Table, probe
from ..listing import listing, note
from .icd import patient_codes

ENC_DIAG = ", ".join(f"enc_diag_{i}" for i in range(1, 34))
ICD_CSV = "data/icd10cm-tabular-2026.csv"
#: One description per code, so a join cannot multiply diagnosis rows.
ICD_LOOKUP = f"""
    SELECT replace(diag_name, '.', '') AS code, any_value(diag_desc) AS descr
    FROM read_csv_auto('{ICD_CSV}', header=true, sample_size=100000)
    WHERE diag_name IS NOT NULL GROUP BY 1
"""
SELECTION_NOTE = (
    "Every count here is a recorded frequency within a selected cohort. Patients "
    "carrying any code that occurred fewer than 11 times were removed before "
    "delivery (1.4), so rare entries are absent by construction and nothing in "
    "this table is a population rate."
)


@probe("domains.diagnoses", "5.1")
def diagnoses(ctx: Context) -> list[Finding]:
    enc_total, enc_pat = ctx.one(f"""
        WITH s AS (SELECT patient_id, unnest([{ENC_DIAG}]) AS code FROM visits)
        SELECT count(*), count(DISTINCT patient_id) FROM s
        WHERE code IS NOT NULL AND trim(code) <> ''""")
    with_any = ctx.scalar(
        "SELECT count(*) FROM visits WHERE enc_diag_1 IS NOT NULL")
    slots = ctx.q(f"""
        WITH s AS (SELECT visit_id, count(*) AS n FROM (
            SELECT visit_id, unnest([{ENC_DIAG}]) AS code FROM visits) t
            WHERE code IS NOT NULL AND trim(code) <> '' GROUP BY 1)
        SELECT n, count(*) FROM s GROUP BY 1 ORDER BY 1 LIMIT 12""")

    top_enc, enc_distinct, enc_complete = listing(ctx,
        f"""SELECT count(DISTINCT code) FROM (
              SELECT unnest([{ENC_DIAG}]) AS code FROM visits)
            WHERE code IS NOT NULL AND trim(code) <> ''""",
        f"""WITH s AS (SELECT patient_id, unnest([{ENC_DIAG}]) AS code FROM visits),
        f AS (SELECT code, count(*) AS slots, count(DISTINCT patient_id) AS pts
              FROM s WHERE code IS NOT NULL AND trim(code) <> ''
              GROUP BY 1 ORDER BY slots DESC {{limit}}),
        l AS ({ICD_LOOKUP})
        SELECT f.code, coalesce(l.descr, '[not in the ICD-10 lookup]'),
               f.slots, f.pts
        FROM f LEFT JOIN l ON replace(f.code, '.', '') = l.code
        ORDER BY f.slots DESC""")
    enc_covered = 100.0 * sum(r[2] for r in top_enc) / enc_total

    top_pl, pl_distinct, pl_complete = listing(ctx,
        "SELECT count(DISTINCT pl_diag) FROM problem_list WHERE pl_diag IS NOT NULL",
        f"""WITH f AS (SELECT pl_diag AS code, count(*) AS entries,
                          count(DISTINCT patient_id) AS pts
                   FROM problem_list WHERE pl_diag IS NOT NULL
                   GROUP BY 1 ORDER BY entries DESC {{limit}}),
        l AS ({ICD_LOOKUP})
        SELECT f.code, coalesce(l.descr, '[not in the ICD-10 lookup]'),
               f.entries, f.pts
        FROM f LEFT JOIN l ON replace(f.code, '.', '') = l.code
        ORDER BY f.entries DESC""")

    pc = patient_codes(ctx)
    cats, silent = ctx.one(f"""
        SELECT count(DISTINCT substr(code, 1, 3)),
               (SELECT count(*) FROM (
                   SELECT substr(code, 1, 3) AS c FROM {pc} GROUP BY 1
                   HAVING sum(CASE WHEN code = substr(code, 1, 3) THEN 1 ELSE 0 END) = 0))
        FROM {pc}""")
    roll_raw, roll_distinct, roll_complete = listing(ctx,
        f"SELECT count(DISTINCT substr(code, 1, 3)) FROM {pc}",
        f"""WITH f AS (SELECT substr(code, 1, 3) AS cat,
                          count(DISTINCT patient_id) AS n
                   FROM {pc} GROUP BY 1 ORDER BY n DESC {{limit}}),
        l AS ({ICD_LOOKUP})
        SELECT f.cat, coalesce(l.descr, '[not in the ICD-10 lookup]'), f.n
        FROM f LEFT JOIN l ON f.cat = l.code ORDER BY f.n DESC""")
    rollup = [{"category": c, "descr": d, "patients": n} for c, d, n in roll_raw]

    pl_rows, pl_pts, pl_resolved = ctx.one(
        "SELECT count(*), count(DISTINCT patient_id), "
        "count(resolved_date_age_in_days) FROM problem_list")

    f = Finding(
        id="domains.diagnoses", part="5.1", title="Diagnoses",
        values={"enc_total": enc_total, "enc_pat": enc_pat,
                "with_any": with_any,
                "with_any_share": 100.0 * with_any / ctx.scalar(
                    "SELECT count(*) FROM visits"),
                "pl_rows": pl_rows, "pl_pts": pl_pts,
                "pl_resolved_share": 100.0 * pl_resolved / pl_rows,
                "cats": cats, "silent": silent},
    )
    f.blocks = [
        Para("Diagnoses arrive two ways: up to 33 coded slots per encounter, and a "
             "problem list that is not visit-linked. {enc_total:,} encounter slots "
             "are filled across {enc_pat:,} patients, and {with_any:,} visits "
             "({with_any_share:.1f}%) carry at least a first diagnosis."),
        Figure("fig-dx-slots", "Coded diagnoses per visit", "bar",
               {"categories": [str(n) for n, _ in slots],
                "series": [{"name": "visits", "values": [c for _, c in slots]}],
                "height": 240, "title": "Diagnosis slots occupied per visit"},
               alt="Most visits carry one to three coded diagnoses."),
        Table("t-enc-dx", "Most frequently recorded encounter diagnoses",
              [C("code", "ICD-10"), C("descr", "description"),
               C("slots", "slots", ",", align="right"),
               C("pts", "patients", ",", align="right")],
              [{"code": c, "descr": d, "slots": s, "pts": p}
               for c, d, s, p in top_enc],
              note=note(enc_distinct, enc_complete, enc_covered, "filled slots")
                   + " " + SELECTION_NOTE),
        Para("The problem list holds {pl_rows:,} entries for {pl_pts:,} patients, of "
             "which {pl_resolved_share:.1f}% carry a resolved age. As 3.5 shows, the "
             "remainder are open problems rather than missing dates."),
        Table("t-pl-dx", "Most frequently recorded problem-list diagnoses",
              [C("code", "ICD-10"), C("descr", "description"),
               C("entries", "entries", ",", align="right"),
               C("pts", "patients", ",", align="right")],
              [{"code": c, "descr": d, "entries": e, "pts": p}
               for c, d, e, p in top_pl],
              note=note(pl_distinct, pl_complete,
                        100.0 * sum(r[2] for r in top_pl) / pl_rows, "entries")),
        Para("**Both tables above count literal codes**, which is the right unit "
             "for describing what gets typed but the wrong one for counting a "
             "condition. Rolling the same data up to the three-character category "
             "changes which diagnoses appear at all — see 3.9, and note that "
             "{silent:,} of the {cats:,} categories in this extract never appear as "
             "a bare code, so an exact-match query for them returns zero.",
             role="warning"),
        Table("t-dx-rollup", "The same diagnoses rolled up to their ICD-10 category",
              [C("category", "category"), C("descr", "description"),
               C("patients", "patients", ",", align="right")], rollup,
              note=note(roll_distinct, roll_complete)),
        Para("**Implications for analysis.** Encounter diagnoses and problem-list "
             "entries answer different questions and should not be pooled without "
             "saying why: the first is what was coded at a contact, the second is "
             "what the chart asserts about the child, including resolved history. "
             "Neither is an adjudicated clinical truth, and a code's absence is not "
             "evidence a condition was absent.", role="implication"),
    ]
    return [f]


@probe("domains.labs", "5.2")
def labs(ctx: Context) -> list[Finding]:
    rows, orders, pts = ctx.one(
        "SELECT count(*), count(DISTINCT lab_order_id), count(DISTINCT patient_id) "
        "FROM labs")
    top, lab_distinct, lab_complete = listing(ctx,
        "SELECT count(DISTINCT lab_procedure_name) FROM labs "
        "WHERE lab_procedure_name IS NOT NULL",
        """SELECT lab_procedure_name, count(*) AS n,
                  count(DISTINCT patient_id) AS pts
           FROM labs WHERE lab_procedure_name IS NOT NULL
           GROUP BY 1 ORDER BY n DESC {limit}""")
    no_result = ctx.scalar(
        "SELECT count(*) FROM labs WHERE result_value IS NULL "
        "OR trim(result_value) = ''")
    orphan_order = ctx.scalar("""
        WITH g AS (SELECT lab_order_id, count(result_component_name) AS c
                   FROM labs GROUP BY 1)
        SELECT count(*) FROM g WHERE c = 0""")

    f = Finding(
        id="domains.labs", part="5.2", title="Laboratory results",
        values={"rows": rows, "orders": orders, "pts": pts,
                "per_order": rows / orders,
                "no_result": no_result,
                "no_result_share": 100.0 * no_result / rows,
                "orphan_order": orphan_order,
                "orphan_share": 100.0 * orphan_order / orders},
    )
    f.blocks = [
        Para("{rows:,} resulted components across {orders:,} lab orders for "
             "{pts:,} patients — {per_order:.1f} components per order. The grain is "
             "the component, not the order, which is the single most common source "
             "of double counting in this resource."),
        Table("t-labs-top", "Most frequently ordered lab procedures",
              [C("name", "procedure"), C("n", "rows", ",", align="right"),
               C("pts", "patients", ",", align="right")],
              [{"name": n, "n": c, "pts": p} for n, c, p in top],
              note=note(lab_distinct, lab_complete,
                        100.0 * sum(r[1] for r in top) / rows, "rows")
                   + " " + SELECTION_NOTE),
        Para("{no_result:,} rows ({no_result_share:.1f}%) carry no result value at "
             "all, and {orphan_order:,} orders ({orphan_share:.1f}%) have no "
             "resulted component on any line. Both are expected rather than broken: "
             "the extract includes externally sourced labs that arrive without "
             "results. 3.6 covers how the values that do exist are shaped."),
        Para("**Implications for analysis.** Count orders when you mean tests and "
             "rows when you mean components, and never mix them in a rate. An "
             "order-with-no-result is a documented ordering event, not a missing "
             "result to impute.", role="implication"),
    ]
    return [f]


@probe("domains.medications", "5.3")
def medications(ctx: Context) -> list[Finding]:
    rows, pts = ctx.one(
        "SELECT count(*), count(DISTINCT patient_id) FROM medications")
    top, med_distinct, med_complete = listing(ctx,
        "SELECT count(DISTINCT med_simple_generic_name) FROM medications "
        "WHERE med_simple_generic_name IS NOT NULL",
        """SELECT med_simple_generic_name, count(*) AS n,
                  count(DISTINCT patient_id) AS pts
           FROM medications WHERE med_simple_generic_name IS NOT NULL
           GROUP BY 1 ORDER BY n DESC {limit}""")
    kinds = ctx.q("""
        SELECT med_record_type, count(*) AS n, count(DISTINCT patient_id) AS pts,
               100.0 * count(med_start_date_age_in_days) / count(*) AS start_pct,
               100.0 * count(med_end_date_age_in_days) / count(*) AS end_pct
        FROM medications GROUP BY 1 ORDER BY n DESC""")
    absent = ["med_therapeutic_class", "med_pharmaceutical_class",
              "med_pharmaceutical_subclass"]

    f = Finding(
        id="domains.medications", part="5.3", title="Medications",
        values={"rows": rows, "pts": pts, "n_absent": len(absent),
                "absent": ", ".join(f"`{a}`" for a in absent)},
    )
    f.blocks = [
        Para("{rows:,} medication records for {pts:,} patients. A record is an "
             "order placed by a practice clinician or a documentation of an outside "
             "or historical medication, and the two behave differently."),
        Table("t-med-type", "Record type and date completeness",
              [C("type", "record type"), C("n", "records", ",", align="right"),
               C("pts", "patients", ",", align="right"),
               C("start_pct", "start age present", ".1f", "%", align="right"),
               C("end_pct", "end age present", ".1f", "%", align="right")],
              [{"type": t, "n": n, "pts": p, "start_pct": s, "end_pct": e}
               for t, n, p, s, e in kinds]),
        Table("t-med-top", "Most frequently recorded medications",
              [C("name", "generic name"), C("n", "records", ",", align="right"),
               C("pts", "patients", ",", align="right")],
              [{"name": n, "n": c, "pts": p} for n, c, p in top],
              note=note(med_distinct, med_complete,
                        100.0 * sum(r[1] for r in top) / rows, "records")
                   + " " + SELECTION_NOTE),
        Para("**Three documented fields were never delivered.** The data dictionary "
             "describes {n_absent} medication classification columns — {absent} — "
             "and none is present in the extract. Any analysis by drug class has to "
             "map `med_simple_generic_name` itself.", role="warning"),
        Para("**Implications for analysis.** A record is not an administration and "
             "not evidence the child took the drug. Externally documented records "
             "carry a documentation date in the order-date column and approximate "
             "start dates, so exposure windows built from them are unreliable; 3.3 "
             "measures how often the dates contradict each other.", role="implication"),
    ]
    return [f]


@probe("domains.referrals", "5.4")
def referrals(ctx: Context) -> list[Finding]:
    rows, pts = ctx.one("SELECT count(*), count(DISTINCT patient_id) FROM referrals")
    top, spec_distinct, spec_complete = listing(ctx,
        "SELECT count(DISTINCT requested_specialty) FROM referrals "
        "WHERE requested_specialty IS NOT NULL AND trim(requested_specialty) <> ''",
        """SELECT requested_specialty, count(*) AS n,
                  count(DISTINCT patient_id) AS pts,
                  quantile_cont(referral_date_age_in_days, 0.5) / 365.25 AS med_age
           FROM referrals WHERE requested_specialty IS NOT NULL
             AND trim(requested_specialty) <> ''
           GROUP BY 1 ORDER BY n DESC {limit}""")
    spec_missing, visits_missing = ctx.one(
        "SELECT sum(CASE WHEN requested_specialty IS NULL "
        "         OR trim(requested_specialty) = '' THEN 1 ELSE 0 END), "
        "       sum(CASE WHEN referral_number_of_visits IS NULL THEN 1 ELSE 0 END) "
        "FROM referrals")
    age_bands = ctx.q("""
        SELECT CASE WHEN referral_date_age_in_days < 730 THEN '0-2'
                    WHEN referral_date_age_in_days < 1826 THEN '2-5'
                    WHEN referral_date_age_in_days < 3652 THEN '5-10'
                    WHEN referral_date_age_in_days < 5478 THEN '10-15'
                    ELSE '15-18' END AS band, count(*) AS n
        FROM referrals WHERE referral_date_age_in_days IS NOT NULL
        GROUP BY 1 ORDER BY min(referral_date_age_in_days)""")

    f = Finding(
        id="domains.referrals", part="5.4", title="Referrals",
        values={"rows": rows, "pts": pts,
                "spec_missing": spec_missing,
                "spec_share": 100.0 * spec_missing / rows,
                "visits_missing": visits_missing,
                "visits_share": 100.0 * visits_missing / rows},
    )
    f.blocks = [
        Para("{rows:,} referral orders for {pts:,} patients. A referral is a "
             "recorded action, not an outcome: it says a clinician placed an order, "
             "not that the child was seen."),
        Figure("fig-ref-age", "Referrals by age at order", "bar",
               {"categories": [b for b, _ in age_bands],
                "series": [{"name": "referrals", "values": [n for _, n in age_bands]}],
                "height": 240, "title": "Referral age distribution"},
               alt="Referral volume across five age bands."),
        Table("t-ref-top", "Most frequently requested specialties",
              [C("specialty", "specialty"), C("n", "referrals", ",", align="right"),
               C("pts", "patients", ",", align="right"),
               C("med_age", "median age", ".2f", " y", align="right")],
              [{"specialty": s, "n": n, "pts": p, "med_age": a}
               for s, n, p, a in top],
              note=note(spec_distinct, spec_complete,
                        100.0 * sum(r[1] for r in top) / rows, "referrals")
                   + " " + SELECTION_NOTE),
        Para("{spec_missing:,} referrals ({spec_share:.2f}%) carry no requested "
             "specialty and {visits_missing:,} ({visits_share:.1f}%) no requested "
             "visit count. The data dictionary also warns that referrals are not "
             "always documented in the source system, so absence of a referral is "
             "not evidence none was made."),
        Para("**Implications for analysis.** This resource is positive-unlabelled: "
             "recorded referrals are real, but unrecorded ones are indistinguishable "
             "from referrals that never happened. Combined with the partial visit "
             "link measured in 3.2, a referral rate computed here is a documentation "
             "rate. Treat it as such and say so.", role="implication"),
    ]
    return [f]


@probe("domains.identity", "5.5")
def identity(ctx: Context) -> list[Finding]:
    total = ctx.scalar("SELECT count(*) FROM patients")

    def dist(col: str):
        """These vocabularies are short enough to list in full."""
        return ctx.q(f"""
            SELECT coalesce(nullif(trim(CAST({col} AS VARCHAR)), ''), '[blank]') AS v,
                   count(*) AS n FROM patients GROUP BY 1 ORDER BY n DESC""")

    sex_rows = [{"category": v, "patients": n, "share": 100.0 * n / total}
                for v, n in dist("sex")]
    eth_rows = [{"category": v, "patients": n, "share": 100.0 * n / total}
                for v, n in dist("ethnicity")]
    race_rows = [{"category": v, "patients": n, "share": 100.0 * n / total}
                 for v, n in dist("race_1")]
    multi = ctx.scalar("SELECT count(*) FROM patients WHERE race_2 IS NOT NULL "
                       "AND trim(race_2) <> ''")

    vis = ctx.one("""
        SELECT quantile_cont(visits_count, 0.25), quantile_cont(visits_count, 0.5),
               quantile_cont(visits_count, 0.75), quantile_cont(visits_count, 0.95),
               avg(visits_count), max(visits_count)
        FROM patients_augmented""")
    span = ctx.one("""
        SELECT quantile_cont(visits_span_days / 365.25, 0.25),
               quantile_cont(visits_span_days / 365.25, 0.5),
               quantile_cont(visits_span_days / 365.25, 0.75),
               quantile_cont(max_visit_age_days / 365.25, 0.5)
        FROM patients_augmented WHERE visits_span_days IS NOT NULL""")

    f = Finding(
        id="domains.identity", part="5.5",
        title="Recorded identity and patient-level observation",
        values={"total": total, "multi": multi,
                "multi_share": 100.0 * multi / total,
                "v25": vis[0], "v50": vis[1], "v75": vis[2], "v95": vis[3],
                "vmean": vis[4], "vmax": vis[5],
                "s25": span[0], "s50": span[1], "s75": span[2], "last": span[3]},
    )
    f.blocks = [
        Para("Identity fields are recorded categories, not attributes of the "
             "children. Non-response is shown separately from every substantive "
             "category, because blank, unknown, and declined are not clinically "
             "equivalent to a recorded value but are all missing for the purpose of "
             "a subgroup comparison."),
        Table("t-sex", "Recorded sex",
              [C("category", "category"), C("patients", "patients", ",", align="right"),
               C("share", "share", ".1f", "%", align="right")], sex_rows),
        Table("t-eth", "Recorded ethnicity",
              [C("category", "category"), C("patients", "patients", ",", align="right"),
               C("share", "share", ".1f", "%", align="right")], eth_rows),
        Table("t-race", "First recorded race",
              [C("category", "category"), C("patients", "patients", ",", align="right"),
               C("share", "share", ".1f", "%", align="right")], race_rows,
              note="Race is a multi-select of up to eight slots; only the first is "
                   "shown. {multi:,} patients ({multi_share:.1f}%) have a second "
                   "race recorded, so this table understates multiracial identity."),
        Para("Observation per patient is dense, as the cohort rule in 1.4 requires. "
             "The median patient has {v50:,.0f} visits (quartiles {v25:,.0f} and "
             "{v75:,.0f}, 95th percentile {v95:,.0f}, maximum {vmax:,.0f}), spanning "
             "a median of {s50:.1f} years (quartiles {s25:.1f} and {s75:.1f}). The "
             "median patient's last recorded visit is at age {last:.1f} years."),
        Para("**Implications for analysis.** Identity non-response is large enough "
             "to change a subgroup contrast on its own, so report it as its own "
             "category rather than dropping it. And because entry to this cohort "
             "required both a measurement history and a recent visit, the visit "
             "distribution describes the selection as much as the care; it is a "
             "feasibility figure, not an estimate of pediatric utilisation.",
             role="implication"),
    ]
    return [f]

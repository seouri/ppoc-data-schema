"""Part 3.6-3.7 — code systems, categorical hygiene, and capture behaviour."""

from __future__ import annotations

from ..context import Context
from ..findings import Artifact, Finding, Para, Table, probe
from ..findings import Column as C
from ..listing import listing, note

ENC_DIAG = ", ".join(f"enc_diag_{i}" for i in range(1, 34))
ICD10 = r"^[A-TV-Z][0-9][0-9AB](\.?[0-9A-TV-Z]{0,4})?$"


@probe("terminology.codes", "3.6")
def codes(ctx: Context) -> list[Finding]:
    enc_filled, enc_distinct, enc_bad = ctx.one(f"""
        WITH slots AS (SELECT unnest([{ENC_DIAG}]) AS code FROM visits)
        SELECT count(*), count(DISTINCT code),
               sum(CASE WHEN NOT regexp_matches(code, '{ICD10}') THEN 1 ELSE 0 END)
        FROM slots WHERE code IS NOT NULL AND trim(code) <> ''""")
    pl_filled, pl_distinct, pl_bad = ctx.one(f"""
        SELECT count(*), count(DISTINCT pl_diag),
               sum(CASE WHEN NOT regexp_matches(pl_diag, '{ICD10}') THEN 1 ELSE 0 END)
        FROM problem_list WHERE pl_diag IS NOT NULL AND trim(pl_diag) <> ''""")
    nonconf = ctx.q(f"""
        WITH slots AS (SELECT unnest([{ENC_DIAG}]) AS code FROM visits)
        SELECT code, count(*) FROM slots
        WHERE code IS NOT NULL AND trim(code) <> ''
          AND NOT regexp_matches(code, '{ICD10}')
        GROUP BY 1 ORDER BY 2 DESC, code LIMIT 6""")

    loinc_total, loinc_have = ctx.one(
        "SELECT count(*), count(result_loinc_code) FROM labs")
    # `populated` is the denominator a cast actually faces, and `resulted` the one
    # a LOINC share should use: a row never resulted has no value to code.
    parsed, empty, populated, resulted = ctx.one(
        "SELECT count(*) FILTER (WHERE try_cast(result_value AS DOUBLE) IS NOT NULL), "
        "       count(*) FILTER (WHERE result_value IS NULL "
        "                          OR trim(result_value) = ''), "
        "       count(result_value), "
        "       count(*) FILTER (WHERE result_line_num IS NOT NULL) FROM labs")
    censored = ctx.scalar(
        "SELECT count(*) FROM labs WHERE regexp_matches(trim(result_value), '^[<>]')")

    dup_pairs, dup_disagree = ctx.one("""
        WITH g AS (SELECT lab_order_id, result_component_name,
                          count(*) AS c, count(DISTINCT result_value) AS v
                   FROM labs GROUP BY 1, 2)
        SELECT sum(CASE WHEN c > 1 THEN 1 ELSE 0 END),
               sum(CASE WHEN c > 1 AND v > 1 THEN 1 ELSE 0 END) FROM g""")

    vocab = []
    for table, col in (("labs", "lab_procedure_name"),
                       ("medications", "med_simple_generic_name"),
                       ("referrals", "requested_specialty")):
        raw, norm = ctx.one(
            f"SELECT count(DISTINCT {col}), "
            f"count(DISTINCT lower(regexp_replace(trim({col}), '\\s+', ' ', 'g'))) "
            f"FROM {table} WHERE {col} IS NOT NULL AND trim({col}) <> ''")
        vocab.append({"resource": table, "field": col, "raw": raw, "normalized": norm,
                      "collapse": raw - norm})

    f = Finding(
        id="terminology.codes", part="3.6",
        title="Code systems, free text, and categorical hygiene",
        values={
            "enc_filled": enc_filled, "enc_distinct": enc_distinct, "enc_bad": enc_bad,
            "enc_bad_share": 100.0 * enc_bad / enc_filled,
            "pl_filled": pl_filled, "pl_distinct": pl_distinct, "pl_bad": pl_bad,
            "pl_bad_share": 100.0 * pl_bad / pl_filled,
            "loinc_share": 100.0 * loinc_have / loinc_total,
            "loinc_total": loinc_total,
            "parsed": parsed, "parsed_share": 100.0 * parsed / loinc_total,
            "empty": empty, "empty_share": 100.0 * empty / loinc_total,
            "populated": populated, "resulted": resulted,
            "loinc_resulted": 100.0 * loinc_have / resulted,
            "cast_lost": populated - parsed,
            "cast_lost_share": 100.0 * (populated - parsed) / populated,
            "censored": censored,
            "dup_pairs": dup_pairs, "dup_disagree": dup_disagree,
            "dup_share": 100.0 * dup_disagree / dup_pairs if dup_pairs else 0.0,
        },
        artifact=Artifact(
            name="Laboratory results are semi-structured text",
            kind="capture",
            scale="{censored:,} comparator-prefixed values; only "
                  "{parsed_share:.1f}% of rows parse as a number",
            recoverable="Yes — parse comparators explicitly rather than casting",
        ),
    )
    f.blocks = [
        Para("Diagnosis coding is almost entirely well-formed ICD-10. Of "
             "{enc_filled:,} filled encounter-diagnosis slots across "
             "{enc_distinct:,} distinct codes, {enc_bad:,} ({enc_bad_share:.2f}%) "
             "do not match the ICD-10 shape; of {pl_filled:,} problem-list entries "
             "across {pl_distinct:,} codes, {pl_bad:,} ({pl_bad_share:.2f}%)."),
        Table("t-nonconf", "The non-conforming diagnosis values",
              [C("code", "value"), C("n", "slots", ",", align="right")],
              [{"code": c, "n": n} for c, n in nonconf],
              note="These are proprietary placeholders the source EHR emits when a "
                   "clinical term has no ICD-10 equivalent. They carry no diagnostic "
                   "meaning and should be excluded from code-based cohort "
                   "definitions rather than treated as unmapped diagnoses."),
        Para("Laboratory results are the opposite case. `result_value` is a text "
             "column: of {loinc_total:,} rows, {parsed:,} ({parsed_share:.1f}%) "
             "parse as a number and {empty:,} ({empty_share:.1f}%) hold no value at "
             "all. Those are nulls, not empty strings — 3.5 looks for the empty "
             "string and finds none, so the two sections are measuring different "
             "things and agree. Among "
             "the rest, {censored:,} are censored results carrying a comparator "
             "prefix, and the remainder are qualitative results, specimen "
             "descriptors, and administrative non-results. A LOINC code is present "
             "on {loinc_share:.1f}% of rows, or {loinc_resulted:.1f}% of the "
             "{resulted:,} that were resulted."),
        Para("The key of 3.1 holds, but {dup_pairs:,} order-and-component pairs "
             "appear on more than one result line and {dup_disagree:,} of those "
             "({dup_share:.1f}%) carry disagreeing values. The data dictionary "
             "records the cause: a result may fail to link back to its original "
             "order, which duplicates the record."),
        Table("t-vocab", "Categorical vocabularies before and after normalising "
                         "case and internal whitespace",
              [C("resource", "resource"), C("field", "field"),
               C("raw", "distinct values", ",", align="right"),
               C("normalized", "after normalising", ",", align="right"),
               C("collapse", "collapsed", ",", align="right")], vocab),
        Para("**Implications for analysis.** A naive numeric cast on `result_value` "
             "silently discards {cast_lost:,} of the {populated:,} populated values "
             "— {cast_lost_share:.1f}%, very nearly half — and turns a "
             "left-censored result into a missing one rather than a bound. Join labs "
             "on order *and* line number, which 3.1 shows is the key, rather than "
             "on order and component, or the duplicate lines will "
             "multiply rows and pick a value arbitrarily. The categorical "
             "vocabularies barely collapse under normalisation, so grouping by them "
             "is safe after trimming.", role="implication"),
    ]
    return [f]


#: Encounter types at which no one could have put a child on a scale. Naming the
#: class is what makes the implication's advice actionable: presence does not
#: discriminate — every one of these carries a weight on nearly every visit.
NO_CONTACT = ("Telephone", "Telemedicine", "Patient Message", "Letter (Out)",
              "Scanned Document", "External Contact", "Documentation", "Abstract",
              "Orders Only", "Refill", "History")
#: How close another visit has to be to count as the source of a carried value.
CARRY_DAYS = 7


@probe("terminology.capture", "3.7")
def capture(ctx: Context) -> list[Finding]:
    enc_rows, enc_distinct, enc_complete = listing(ctx,
        "SELECT count(DISTINCT encounter_type) FROM visits_augmented "
        "WHERE encounter_type IS NOT NULL",
        """SELECT encounter_type, count(*) AS n,
                  100.0 * count(weight_oz) / count(*) AS w,
                  100.0 * count(height_in) / count(*) AS h,
                  100.0 * count(enc_diag_1) / count(*) AS d
           FROM visits_augmented WHERE encounter_type IS NOT NULL
           GROUP BY 1 ORDER BY n DESC, encounter_type {limit}""")
    # A type existing is itself informative, so the row stays and only its
    # numbers are withheld when the cell is too small to show.
    rows = [{"encounter": e,
             "visits": ctx.suppress(n),
             "weight": w if ctx.suppress(n) is not None else None,
             "height": h if ctx.suppress(n) is not None else None,
             "diag": d if ctx.suppress(n) is not None else None}
            for e, n, w, h, d in enc_rows]
    suppressed = sum(1 for r in rows if r["visits"] is None)

    epic = ctx.q("""
        SELECT orig_enc_source_Epic_yn AS src, count(*) AS n,
               100.0 * count(height_in) / count(*) AS h,
               100.0 * count(enc_diag_1) / count(*) AS d
        FROM visits_augmented GROUP BY 1 ORDER BY n DESC, src""")
    epic_rows = [{"source": "Epic" if s == "Y" else "converted from a legacy system",
                  "visits": n, "height": h, "diag": d} for s, n, h, d in epic]

    tele = next((r for r in rows if r["encounter"] == "Telephone"), None)

    # One of the three explanations offered for a weight on a telephone encounter
    # is testable: if the value was carried from a nearby in-person visit it
    # should equal that visit's weight. In-person types are the control, because
    # some coincidence is expected at any encounter.
    ctx.con.execute("""
        CREATE OR REPLACE TEMP VIEW _w AS
        SELECT visit_id, patient_id, age_in_days, encounter_type, weight_oz
        FROM visits_augmented WHERE weight_oz IS NOT NULL""")
    quoted = ", ".join(f"'{t}'" for t in NO_CONTACT)

    def carried(kind: str) -> tuple[int, float]:
        n, m = ctx.one(f"""
            WITH cand AS (SELECT * FROM _w WHERE encounter_type = '{kind}')
            SELECT count(*), count(*) FILTER (WHERE EXISTS (
                SELECT 1 FROM _w o WHERE o.patient_id = cand.patient_id
                  AND o.visit_id <> cand.visit_id
                  AND o.encounter_type NOT IN ({quoted})
                  AND abs(o.age_in_days - cand.age_in_days) <= {CARRY_DAYS}
                  AND o.weight_oz = cand.weight_oz))
            FROM cand""")
        return n, 100.0 * m / n if n else 0.0

    _, tele_carry = carried("Telephone")
    _, tmed_carry = carried("Telemedicine")
    ctrl = [carried(k)[1] for k in ("Walk-In", "Weight Check", "Immunization")]
    ctrl_lo, ctrl_hi = min(ctrl), max(ctrl)
    contact_rows = [r for r in rows if r["encounter"] in NO_CONTACT
                    and r["visits"] is not None]
    contact_visits = sum(r["visits"] for r in contact_rows)
    contact_weight = min(r["weight"] for r in contact_rows)
    f = Finding(
        id="terminology.capture", part="3.7",
        title="Capture: measurement presence is not measurement occurrence",
        values={"tele_weight": tele["weight"] if tele else 0.0,
                "tele_visits": tele["visits"] if tele else 0,
                "enc_distinct": enc_distinct, "suppressed": suppressed,
                "conv_diag": min(r["diag"] for r in epic_rows),
                "n_types": len(rows),
                "tele_carry": tele_carry, "tmed_carry": tmed_carry,
                "ctrl_lo": ctrl_lo, "ctrl_hi": ctrl_hi, "carry_days": CARRY_DAYS,
                "n_contact": len(contact_rows), "contact_visits": contact_visits,
                "contact_weight": contact_weight,
                "contact_list": ", ".join(f"`{r['encounter']}`"
                                          for r in contact_rows),
                "epic_h": next(r["height"] for r in epic_rows
                               if r["source"] == "Epic"),
                "conv_h": next(r["height"] for r in epic_rows
                               if r["source"] != "Epic")},
        artifact=Artifact(
            name="Anthropometrics recorded on encounters with no physical contact",
            kind="capture",
            scale="weight present on {tele_weight:.0f}% of {tele_visits:,} "
                  "telephone encounters",
            recoverable="Partly — restrict by encounter type before counting "
                        "measurement occasions",
        ),
    )
    f.blocks = [
        Para("Completeness by age says how often a column is filled. Encounter type "
             "says whether filling it could have meant a measurement."),
        Table("t-capture", "Measurement and diagnosis presence by encounter type",
              [C("encounter", "encounter type"),
               C("visits", "visits", ",", align="right"),
               C("weight", "weight present", ".1f", "%", align="right"),
               C("height", "height present", ".1f", "%", align="right"),
               C("diag", "first diagnosis", ".1f", "%", align="right")], rows,
              note=note(enc_distinct, enc_complete)
                   + (f" {suppressed} carry too few visits to show a count."
                      if suppressed else "")),
        Para("Telephone encounters carry a weight on {tele_weight:.1f}% of "
             "{tele_visits:,} visits, and they are not alone: {n_contact} encounter "
             "types at which nobody could have put a child on a scale carry a "
             "weight on at least {contact_weight:.1f}% of their visits, "
             "{contact_visits:,} in all — {contact_list}. Presence does not "
             "discriminate between them and an office visit."),
        Para("**One of the three explanations for that is testable, and it mostly "
             "fails.** A weight recorded at a telephone encounter was reported by a "
             "caregiver, carried from a nearby in-person encounter, or attached to "
             "an encounter whose type label does not describe how the patient was "
             "seen. The middle one predicts the value will equal a real one: "
             "{tele_carry:.1f}% of telephone weights match an in-person weight for "
             "the same child within {carry_days} days exactly, against "
             "{ctrl_lo:.1f}% to {ctrl_hi:.1f}% for in-person types where the same "
             "coincidence is just coincidence. So carrying explains a few points of "
             "excess and no more; for telemedicine, at {tmed_carry:.1f}%, it "
             "explains nothing at all. The other two remain, and those this extract "
             "genuinely cannot separate."),
        Table("t-source", "Recording completeness by source system",
              [C("source", "encounter source"),
               C("visits", "visits", ",", align="right"),
               C("height", "height present", ".1f", "%", align="right"),
               C("diag", "first diagnosis", ".1f", "%", align="right")], epic_rows),
        Para("The source-system split is the migration signal. Records converted "
             "from the practice network's previous EHR carry a first diagnosis on "
             "only {conv_diag:.1f}% of encounters, which the data dictionary "
             "anticipates: converted encounters may be missing diagnosis information "
             "depending on the quality of the conversion. Height runs the other way "
             "— {conv_h:.1f}% on converted encounters against {epic_h:.1f}% on "
             "native ones — so the conversion is not uniformly lossy and the "
             "provenance field cannot be read as a quality score."),
        Para("**Implications for analysis.** A visit-level indicator that a "
             "measurement is present is not evidence that a measurement was taken at "
             "that encounter. If your design counts measurement occasions — visit "
             "density, monitoring intensity, follow-up adherence — restrict to "
             "encounter types where physical measurement is possible rather than "
             "relying on presence, and the {n_contact} types named above are the "
             "ones to drop first. And any diagnosis-based rate computed across the "
             "whole extract mixes two populations with very different coding "
             "completeness.", role="implication"),
    ]
    return [f]

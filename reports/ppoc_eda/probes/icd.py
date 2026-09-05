"""Part 3.9 — ICD-10 is a hierarchy, and counting it flat undercounts.

Shared by the diagnosis probes: `patient_codes` materialises one row per patient
and distinct code across both diagnosis resources, which several findings need
and none should build twice.
"""

from __future__ import annotations

from ..context import Context
from ..findings import Artifact, Finding, Para, Table, probe
from ..findings import Column as C

ENC_DIAG = ", ".join(f"enc_diag_{i}" for i in range(1, 34))


def patient_codes(ctx: Context) -> str:
    """Create `_patient_code` once per run and return its name."""
    if not getattr(ctx, "_pc_ready", False):
        ctx.con.execute(f"""
            CREATE TEMP TABLE _patient_code AS
            WITH e AS (SELECT patient_id, unnest([{ENC_DIAG}]) AS code FROM visits)
            SELECT DISTINCT patient_id, code FROM (
                SELECT patient_id, code FROM e
                WHERE code IS NOT NULL AND trim(code) <> ''
                UNION ALL
                SELECT patient_id, pl_diag FROM problem_list WHERE pl_diag IS NOT NULL)
        """)
        ctx._pc_ready = True
    return "_patient_code"


@probe("icd.hierarchy", "3.9")
def hierarchy(ctx: Context) -> list[Finding]:
    pc = patient_codes(ctx)
    distinct, three_char, cats = ctx.one(f"""
        SELECT count(DISTINCT code),
               count(DISTINCT CASE WHEN length(code) = 3 THEN code END),
               count(DISTINCT substr(code, 1, 3)) FROM {pc}""")
    silent = ctx.scalar(f"""
        SELECT count(*) FROM (
            SELECT substr(code, 1, 3) AS cat FROM {pc} GROUP BY 1
            HAVING sum(CASE WHEN code = substr(code, 1, 3) THEN 1 ELSE 0 END) = 0)""")

    literal = ctx.q(f"""SELECT code, count(DISTINCT patient_id) AS n FROM {pc}
                        GROUP BY 1 ORDER BY n DESC, code LIMIT 6""")
    rolled = ctx.q(f"""SELECT substr(code, 1, 3), count(DISTINCT patient_id) AS n
                       FROM {pc} GROUP BY 1 ORDER BY n DESC, 1 LIMIT 6""")
    rows = [{"rank": i + 1, "literal": lc, "literal_n": ln,
             "category": rc, "category_n": rn}
            for i, ((lc, ln), (rc, rn)) in enumerate(zip(literal, rolled, strict=True))]

    # A worked example: a category split across children, invisible when counted flat.
    ex_cat = "H66"
    ex_flat = ctx.scalar(f"SELECT count(DISTINCT patient_id) FROM {pc} "
                         f"WHERE code = '{ex_cat}'")
    ex_tree = ctx.scalar(f"SELECT count(DISTINCT patient_id) FROM {pc} "
                         f"WHERE code LIKE '{ex_cat}%'")
    ex_children = ctx.q(f"""SELECT code, count(DISTINCT patient_id) AS n FROM {pc}
                            WHERE code LIKE '{ex_cat}%' GROUP BY 1
                            ORDER BY n DESC, code LIMIT 5""")

    f = Finding(
        id="icd.hierarchy", part="3.9",
        title="Counting diagnosis codes: ICD-10 is a hierarchy",
        values={"distinct": distinct, "three_char": three_char, "cats": cats,
                "silent": silent, "silent_share": 100.0 * silent / cats,
                "ex_cat": ex_cat, "ex_flat": ex_flat, "ex_tree": ex_tree},
        artifact=Artifact(
            name="Diagnosis codes counted flat rather than as a hierarchy",
            kind="capture",
            scale="{silent:,} of {cats:,} categories never appear as a bare "
                  "three-character code",
            recoverable="Yes — match on a prefix, or roll up before counting",
        ),
    )
    f.blocks = [
        Para("ICD-10 is a tree, not a list. `E10` is type 1 diabetes and `E10.9` is "
             "type 1 diabetes without complications; a chart may carry either, and "
             "which one it carries is a coding decision rather than a clinical one. "
             "**A query that matches a code exactly therefore counts one node of the "
             "tree, not the concept.** This is the single most common way to "
             "undercount a diagnosis in this extract, and it fails silently — the "
             "query returns a number, just the wrong one."),
        Para("The extract carries {distinct:,} distinct codes across its two "
             "diagnosis resources, of which only {three_char:,} are bare "
             "three-character categories. Rolling every code up to its category "
             "gives {cats:,} categories, and **{silent:,} of those "
             "({silent_share:.1f}%) never appear as a bare code at all**. For those, "
             "an exact-match query returns zero while the condition is present."),
        Para("The effect is large enough to reorder a frequency table. Below, the "
             "six most common literal codes beside the six most common categories "
             "after rollup."),
        Table("t-icd-rollup", "The most common diagnoses, counted flat and rolled up",
              [C("rank", "rank", align="right"),
               C("literal", "literal code"),
               C("literal_n", "patients", ",", align="right"),
               C("category", "category"),
               C("category_n", "patients", ",", align="right")], rows),
        Para("`{ex_cat}` is the clearest case. Counted literally it has {ex_flat:,} "
             "patients, because clinicians code the laterality-specific children "
             "instead. Counted as a subtree it has {ex_tree:,} — enough to place it "
             "among the most common conditions in the extract, where a flat count "
             "makes it invisible."),
        Table("t-icd-example", "The children a flat count misses",
              [C("code", "code"), C("n", "patients", ",", align="right")],
              [{"code": c, "n": n} for c, n in ex_children]),
        Para("**Implications for analysis.** Match on a prefix (`code LIKE 'E10%'`) "
             "or roll up to the level you actually mean before counting, and say "
             "which level that is. Two cautions on prefixes: a code is a string, so "
             "compare against the code with its decimal point as stored, and a "
             "prefix of a prefix will over-match — `E1` is not a category. Where a "
             "frequency table is the deliverable rather than an input, report the "
             "rolled-up count and the literal one side by side, since the gap "
             "between them is itself a description of local coding practice.",
             role="implication"),
    ]
    return [f]

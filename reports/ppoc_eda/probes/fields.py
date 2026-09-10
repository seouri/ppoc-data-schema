"""Part 3.4-3.5 and Part 6 — missingness, sentinel values, and the field index.

One scan serves all three: a per-column population count for every resource,
plus range or level summaries for the columns worth them.
"""

from __future__ import annotations

from ..context import RESOURCES, Context
from ..findings import Column, Figure, Finding, Para, Table, probe
from ..listing import listing, note

#: Prefixes of repeated column families. The label is built per resource from
#: the members actually present, because the same prefix spans a different
#: number of slots in different resources: `patients` carries eight race
#: columns and `visits_augmented` carries one. A prefix with a single member is
#: not a family and keeps its own name.
FAMILY_PREFIXES = ("enc_diag_", "race_")

#: Visit fields whose availability by age is worth a picture.
HEATMAP_FIELDS = [
    ("weight_kg", "weight"), ("height_cm", "height"), ("bmi", "BMI"),
    ("head_circ_cm", "head circumference"), ("weight_z_score", "weight z"),
    ("height_z_score", "height z"), ("bmi_percentile", "BMI percentile"),
    ("height_velocity", "height velocity"), ("enc_diag_1", "first diagnosis"),
]
AGE_BANDS = [(0, 1, "0-1"), (1, 2, "1-2"), (2, 5, "2-5"), (5, 10, "5-10"),
             (10, 15, "10-15"), (15, 19, "15-18")]

#: The one `result_flag` value the data dictionary defines as normal.
NORMAL_FLAG = "(NONE)"


def _members(cols: list[str], prefix: str) -> list[int]:
    return sorted(int(c[len(prefix):]) for c in cols
                  if c.startswith(prefix) and c[len(prefix):].isdigit())


def _families(cols: list[str]) -> dict[str, str]:
    """Map each column of one resource to its family label, where it has one."""
    out: dict[str, str] = {}
    for prefix in FAMILY_PREFIXES:
        members = _members(cols, prefix)
        if len(members) < 2:
            continue
        label = f"{prefix}{members[0]}..{members[-1]}"
        for i in members:
            out[f"{prefix}{i}"] = label
    return out


def scan(ctx: Context) -> list[dict]:
    """Population and distinctness for every column of every resource."""
    out = []
    for table in RESOURCES:
        cols = ctx.columns(table)
        types = ctx.coltype(table)
        total = ctx.scalar(f"SELECT count(*) FROM {table}")
        selects = ", ".join(
            f'count("{c}") AS n_{i}, count(DISTINCT "{c}") AS d_{i}'
            for i, c in enumerate(cols)
        )
        row = ctx.one(f"SELECT {selects} FROM {table}")
        families = _families(cols)
        seen = set()
        for i, c in enumerate(cols):
            fam = families.get(c)
            if fam:
                if fam in seen:
                    continue
                seen.add(fam)
            out.append({
                "resource": table,
                "field": fam or c,
                "type": types[c],
                "rows": total,
                "present": row[2 * i],
                "missing": 100.0 * (total - row[2 * i]) / total if total else 0.0,
                "distinct": row[2 * i + 1],
            })
    return out


@probe("fields.missingness", "3.4")
def missingness(ctx: Context) -> list[Finding]:
    profile = scan(ctx)
    ctx.field_profile = profile  # reused by the field index below

    worst = sorted(profile, key=lambda r: -r["missing"])[:16]
    # Every one of them is a tracked-diagnosis age column, which makes the table
    # a list of rare codes rather than a description of missingness. Say so, and
    # name the sparsest column outside that family so the reader has a contrast.
    fam = "dx_age_years"
    worst_fam = sum(1 for r in worst if r["field"].startswith(fam))
    outside = next(r for r in sorted(profile, key=lambda r: -r["missing"])
                   if not r["field"].startswith(fam))
    n_fam = sum(1 for r in profile if r["field"].startswith(fam))

    # The section's central claim is missing-by-age, and its only evidence is a
    # figure the Markdown mirror does not render. Carry the corners in prose.
    def avail(col: str, lo: float, hi: float) -> float:
        return ctx.scalar(
            f"SELECT 100.0 * count({col}) / nullif(count(*), 0) "
            f"FROM visits_augmented WHERE age_in_years >= {lo} AND age_in_years < {hi}"
        ) or 0.0
    cells, rows = [], []
    for field, label in HEATMAP_FIELDS:
        rows.append(label)
        line = []
        for lo, hi, _ in AGE_BANDS:
            share = ctx.scalar(
                f"SELECT 100.0 * count({field}) / nullif(count(*), 0) "
                f"FROM visits_augmented WHERE age_in_years >= {lo} AND age_in_years < {hi}"
            )
            line.append(round(share or 0.0, 1))
        cells.append(line)

    f = Finding(
        id="fields.missingness", part="3.4",
        title="Missingness, by field and by age",
        values={"n_cols": len(profile),
                "n_empty": sum(1 for r in profile if r["present"] == 0),
                "worst_field": worst[0]["field"],
                "worst_present": worst[0]["present"],
                "n_shown": len(worst), "n_fam": n_fam,
                "worst_fam": (f"every one of the {len(worst)} rows belongs"
                              if worst_fam == len(worst) else
                              f"{worst_fam} of the {len(worst)} rows belong"),
                "outside_res": outside["resource"], "outside_field": outside["field"],
                "outside_missing": outside["missing"],
                "hc_infant": avail("head_circ_cm", 0, 1),
                "hc_school": avail("head_circ_cm", 5, 10),
                "bmi_infant": avail("bmi", 1, 2), "bmi_child": avail("bmi", 2, 5),
                "h_pre": avail("height_cm", 2, 5), "w_pre": avail("weight_kg", 2, 5)},
    )
    f.blocks = [
        Para("Population was measured for all {n_cols} columns in the extract, "
             "counting the repeated diagnosis and race families once each. "
             "{n_empty} columns are entirely empty. The full table is Part 6; the "
             "{n_shown} least-populated columns are below."),
        Table("t-missing-worst", "The least-populated columns",
              [Column("resource", "resource"), Column("field", "field"),
               Column("present", "populated rows", ",", align="right")], worst,
              note="A share is not shown because it would mislead: each of these "
                   "columns is populated on some rows, and every one of them rounds "
                   "to 100% missing against a quarter of a million patients, which "
                   "would read as the empty columns the sentence above says do not "
                   "exist. And {worst_fam} to one family — "
                   "the {n_fam} `dx_age_years_*` columns, one per tracked diagnosis "
                   "code, so this is a list of rare codes rather than a description "
                   "of missingness; 5.7 and 5.8 are where they mean something. The "
                   "sparsest column outside that family is "
                   "`{outside_res}.{outside_field}` at {outside_missing:.1f}% "
                   "missing."),
        Para("A single missingness rate hides the thing that matters most for a "
             "longitudinal extract: whether a field is missing *at random* or "
             "missing *by age*. For the measurement channels it is emphatically the "
             "latter, and the size of it is worth having in words as well as in the "
             "figure below. Head circumference is on {hc_infant:.1f}% of visits in "
             "the first year and {hc_school:.1f}% between 5 and 10. BMI is on "
             "{bmi_infant:.1f}% between 1 and 2 and {bmi_child:.1f}% between 2 and "
             "5, which is the age-2 floor of 1.3 rather than a change in practice. "
             "Height sits at {h_pre:.1f}% between 2 and 5 where weight sits at "
             "{w_pre:.1f}%, and that gap is the binding constraint 5.10 measures "
             "jointly."),
        Figure("fig-missing-age",
               "Share of visits carrying each measurement, by age band",
               "heatmap",
               {"rows": [label for _, label in HEATMAP_FIELDS],
                "columns": [lab for _, _, lab in AGE_BANDS],
                "cells": cells, "suffix": "%",
                "title": "Measurement availability by age"},
               alt="Availability of each measurement channel across six age bands."),
        Para("**Implications for analysis.** Head circumference is an infant "
             "measurement and effectively disappears after age 2; BMI and its "
             "percentile are withheld below age 2 by the augmentation; height is "
             "recorded far less often than weight at every age. Any cohort defined "
             "by \"has a complete measurement row\" is therefore an age-selected "
             "cohort, and any model that drops incomplete rows inherits that "
             "selection. Report availability by age band before interpreting any "
             "age-stratified contrast.", role="implication"),
    ]
    return [f]


@probe("fields.sentinels", "3.5")
def sentinels(ctx: Context) -> list[Finding]:
    checks = [
        ("visits_augmented", "height_in", "height_in = 0", "zero height"),
        ("visits_augmented", "weight_oz", "weight_oz = 0", "zero weight"),
        ("visits_augmented", "head_circ_cm", "head_circ_cm = 0", "zero head circumference"),
        ("labs", "result_value", "trim(result_value) = ''", "empty result string"),
        ("patients", "sex", "sex IS NULL OR trim(sex) = ''", "blank sex"),
        ("patients", "race_1", "race_1 IS NULL OR trim(race_1) = ''", "blank race_1"),
        ("patients", "ethnicity", "ethnicity IS NULL OR trim(ethnicity) = ''",
         "blank ethnicity"),
    ]
    rows = []
    for table, field, cond, label in checks:
        n = ctx.scalar(f"SELECT count(*) FROM {table} WHERE {cond}")
        rows.append({"resource": table, "field": field, "pattern": label,
                     "rows": ctx.suppress(n)})

    flag_raw, flag_distinct, flag_complete = listing(ctx,
        "SELECT count(*) FROM (SELECT result_flag FROM labs GROUP BY 1)",
        "SELECT result_flag, count(*) AS n FROM labs "
        "GROUP BY 1 ORDER BY n DESC, result_flag {limit}")
    # The dictionary's rule is `(NONE)` normal, everything else abnormal, and the
    # null inherits `(NONE)`'s meaning because it *is* `(NONE)`, lost in delivery.
    # Deriving the column from `v is None` alone made the literal `(NONE)` row read
    # "abnormal" two lines above the paragraph that defines it as normal.
    flag_rows = [
        {"value": v if v is not None else "null", "rows": ctx.suppress(n),
         "meaning": "normal result" if v is None or v == NORMAL_FLAG
                    else "abnormal by the dictionary rule"}
        for v, n in flag_raw
    ]
    flag_values = ctx.scalar("SELECT count(DISTINCT result_flag) FROM labs")
    flag_null = ctx.scalar("SELECT count(*) FROM labs WHERE result_flag IS NULL")
    flag_none = ctx.scalar("SELECT count(*) FROM labs WHERE result_flag = '(NONE)'")
    pl_null = ctx.scalar(
        "SELECT count(*) FROM problem_list WHERE resolved_date_age_in_days IS NULL")
    pl_total = ctx.scalar("SELECT count(*) FROM problem_list")

    f = Finding(
        id="fields.sentinels", part="3.5",
        title="Nulls that are not missing, and sentinels that are not data",
        values={"flag_null": flag_null, "flag_none": flag_none,
                "flag_groups": flag_distinct, "flag_values": flag_values,
                "flag_share": 100.0 * flag_null / ctx.scalar("SELECT count(*) FROM labs"),
                "pl_null": pl_null, "pl_total": pl_total,
                "pl_share": 100.0 * pl_null / pl_total},
    )
    f.blocks = [
        Para("Two of the largest null populations in this extract are not missing "
             "data at all, and reading them as missing throws away the majority of "
             "the signal in their columns."),
        Table("t-flags", "Laboratory result flags",
              [Column("value", "result_flag"), Column("rows", "rows", ",", align="right"),
               Column("meaning", "meaning")], flag_rows,
              note=note(flag_distinct, flag_complete) + (
                  " The null is one of them; 6.1 reports {flag_values} for this "
                  "column because `count(DISTINCT)` drops it.")),
        Para("The data dictionary defines `result_flag` as an HL7 abnormality "
             "category in which the value `(NONE)` means a normal result and "
             "anything else means abnormal. This extract contains {flag_none:,} "
             "literal `(NONE)` values and {flag_null:,} nulls — {flag_share:.1f}% of "
             "all lab rows. The sentinel became a null somewhere between the source "
             "system and delivery, so **a null flag means normal, not unknown**. "
             "The meaning column above applies that rule and nothing else: the null "
             "and the literal `(NONE)` are the normal ones, and every other value is "
             "abnormal *by the dictionary's definition* — including the literal "
             "`Normal` and `Negative`, which are result text the HL7 category does "
             "not exempt. Where that reading matters, treat those rows as an "
             "unresolved conflict between the value and its category rather than as "
             "settled either way."),
        Para("`problem_list.resolved_date_age_in_days` behaves the same way: the "
             "dictionary defines null as \"problem currently active\". {pl_null:,} "
             "of {pl_total:,} entries ({pl_share:.1f}%) are null, which is a "
             "statement about {pl_share:.0f}% of problems being open, not about "
             "missing dates."),
        Table("t-sentinels", "Zero and blank values checked as possible sentinels",
              [Column("resource", "resource"), Column("field", "field"),
               Column("pattern", "pattern"), Column("rows", "rows", ",", align="right")],
              rows),
        Para("**Implications for analysis.** Never impute or drop on `result_flag` "
             "or `resolved_date_age_in_days` nullity. An abnormal-result rate "
             "computed as \"non-null flags over non-null flags\" will read as 100%; "
             "the correct denominator is all resulted rows. A problem-list "
             "resolution rate must count nulls as unresolved rather than excluding "
             "them.", role="implication"),
    ]
    return [f]


@probe("fields.index", "6.1")
def index(ctx: Context) -> list[Finding]:
    profile = getattr(ctx, "field_profile", None) or scan(ctx)
    f = Finding(
        id="fields.index", part="6.1", title="Every column in the extract",
        values={"n": len(profile), "n_res": len(RESOURCES)},
    )
    f.blocks = [
        Para("All {n} distinct columns across the {n_res} resources, with how much "
             "of each is populated and how many values it takes. A repeated family "
             "— the encounter-diagnosis slots, the race slots — appears once, named "
             "for the span it covers in that resource and summarised on its first "
             "member. The span differs between resources: `patients` and "
             "`patients_augmented` carry eight race columns, `visits_augmented` "
             "carries one, so a row reading `race_1` is the whole of that "
             "resource's race detail and not the first of eight."),
        Para("Two sections read this index rather than describe it. 3.4 takes the "
             "least-populated columns from it, and 5.15 scores every numeric column "
             "of the augmented patient layer here against the growth label, which is "
             "where to look before treating any of them as a feature.",
             role="method"),
        Table("t-fieldindex", "Field index",
              [Column("resource", "resource"), Column("field", "field"),
               Column("type", "type"),
               Column("present", "populated", ",", align="right"),
               Column("missing", "missing", ".1f", "%", align="right"),
               Column("distinct", "distinct values", ",", align="right")],
              profile),
    ]
    return [f]

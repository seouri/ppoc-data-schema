"""Parts 5.6 to 5.8 — the derived patient layer and the growth panel.

This extract was assembled around growth: cohort entry required a growth
measurement history (1.4), and the augmentation layer carries patient-level
growth flags and a fixed panel of growth-relevant diagnosis codes. Documenting
that orientation is a description of the data, not of any downstream question.

5.7 says which codes the panel tracks and how many patients carry each; 5.8
says when those codes were first recorded. Both read the panel from
`tracked_codes`, so neither can drift from the other's idea of what is tracked.
"""

from __future__ import annotations

from ..context import Context
from ..findings import Column as C
from ..findings import Figure, Finding, Para, Table, probe
from .icd import patient_codes

ICD_CSV = "data/icd10cm-tabular-2026.csv"
ICD_LOOKUP = f"""
    SELECT replace(diag_name, '.', '') AS code, any_value(diag_desc) AS descr
    FROM read_csv_auto('{ICD_CSV}', header=true, sample_size=100000)
    WHERE diag_name IS NOT NULL GROUP BY 1
"""
FLAGS = [
    ("healthy_flag", "carries none of the tracked conditions"),
    ("chronic_dx_flag", "any chronic diagnosis"),
    ("growth_dx_flag", "any of the tracked growth-relevant diagnoses"),
    ("ever_stunting_flag", "height z below the stunting threshold at any visit"),
    ("ever_wasting_flag", "weight-for-length or -stature below the wasting threshold"),
    ("ever_underweight_flag", "BMI below the underweight threshold at any visit"),
    ("ever_obesity_flag", "BMI at or above the obesity threshold at any visit"),
]
FAMILIES = [
    ("Endocrinology", "%endocrin%"),
    ("Gastroenterology", "%gastroenter%"),
    ("Nutrition and dietetics", "%nutrition%' OR lower(requested_specialty) LIKE '%dietit%"),
    ("Nephrology", "%nephrolog%"),
    ("Genetics", "%genetic%"),
]


def tracked_codes(ctx: Context) -> list[tuple[str, str]]:
    """The tracked growth-relevant panel, as (column, ICD-10 code) pairs.

    The panel is not written down anywhere in the extract; it is recoverable
    only from the augmented layer's column names, and 5.7 and 5.8 both need
    it. The trailing underscore in the prefix is what keeps `dx_age_years` — the
    panel-wide age at first diagnosis, not a code — out of the panel, where it
    would appear as an ICD-10 code named after the column.
    """
    cols = [c for c in ctx.columns("patients_augmented")
            if c.startswith("dx_age_years_")]
    return [(c, c.replace("dx_age_years_", "").upper().replace("_", "."))
            for c in cols]


@probe("growth.flags", "5.6")
def flags(ctx: Context) -> list[Finding]:
    total = ctx.scalar("SELECT count(*) FROM patients_augmented")
    rows = []
    for col, meaning in FLAGS:
        n = ctx.scalar(f"SELECT count(*) FROM patients_augmented WHERE {col} = 1")
        rows.append({"flag": col, "meaning": meaning, "patients": n,
                     "share": 100.0 * n / total})

    dx_age = ctx.one(
        "SELECT count(dx_age_years), quantile_cont(dx_age_years, 0.5), "
        " sum(CASE WHEN dx_age_years <= 1.0 / 12 THEN 1 ELSE 0 END), "
        " sum(CASE WHEN dx_age_years < 0 THEN 1 ELSE 0 END) "
        "FROM patients_augmented WHERE growth_dx_flag = 1")
    z_summary = ctx.q("""
        SELECT 'height' AS ch, count(count_height_z_score),
               avg(mean_height_z_score), avg(std_height_z_score)
        FROM patients_augmented WHERE count_height_z_score > 1
        UNION ALL SELECT 'weight', count(count_weight_z_score),
               avg(mean_weight_z_score), avg(std_weight_z_score)
        FROM patients_augmented WHERE count_weight_z_score > 1
        UNION ALL SELECT 'BMI', count(count_bmi_z_score),
               avg(mean_bmi_z_score), avg(std_bmi_z_score)
        FROM patients_augmented WHERE count_bmi_z_score > 1""")

    growth_n = next(r["patients"] for r in rows if r["flag"] == "growth_dx_flag")
    f = Finding(
        id="growth.flags", part="5.6",
        title="Patient-level derived flags and summaries",
        values={"total": total, "growth_n": growth_n,
                "dx_observed": dx_age[0], "dx_median": dx_age[1],
                "dx_first_month": dx_age[2],
                "dx_first_share": 100.0 * dx_age[2] / dx_age[0] if dx_age[0] else 0.0,
                "dx_negative": ctx.suppress(dx_age[3]) or 0},
    )
    f.blocks = [
        Para("The augmented patient layer carries seven boolean flags and a block of "
             "per-patient z-score summaries. They are conveniences computed from the "
             "visit layer, not independent observations, and each inherits whatever "
             "the channel it summarises does — the height-z flags inherit the "
             "truncation of 4.6, the BMI flags inherit the age-2 floor of 1.3."),
        Table("t-flags", "Patient-level flags",
              [C("flag", "flag"), C("meaning", "set when the patient"),
               C("patients", "patients", ",", align="right"),
               C("share", "share of cohort", ".1f", "%", align="right")], rows),
        Figure("fig-flags", "Patients carrying each derived flag", "bar",
               {"categories": [r["flag"].replace("_flag", "").replace("ever_", "")
                               for r in rows],
                "series": [{"name": "patients", "values": [r["patients"] for r in rows]}],
                "height": 250, "title": "Derived patient flags"},
               alt="Counts of patients carrying each of the seven derived flags."),
        Para("`growth_dx_flag` marks {growth_n:,} patients. Where an age at "
             "diagnosis is observed ({dx_observed:,} patients) its median is "
             "{dx_median:.3f} years, and {dx_first_month:,} of those "
             "({dx_first_share:.1f}%) are assigned their code within the first month "
             "of life. That is a statement about when the code was recorded, not "
             "about when a condition began."),
        Table("t-zsummary", "Per-patient z-score summaries, averaged over patients "
                            "with more than one value",
              [C("ch", "channel"), C("n", "patients", ",", align="right"),
               C("mean", "mean of patient means", ".4f", align="right"),
               C("sd", "mean of patient SDs", ".4f", align="right")],
              [{"ch": c, "n": n, "mean": m, "sd": s} for c, n, m, s in z_summary]),
        Para("**Implications for analysis.** A flag is a recorded derivation, not an "
             "adjudicated clinical state, and the concentration of growth-diagnosis "
             "ages in the first month shows why: much of what the flag marks is "
             "perinatal coding rather than a growth trajectory that was observed and "
             "interpreted over years. Use the flags to describe the derived layer or "
             "to stratify descriptively; recompute from the visit layer against a "
             "stated rule if a flag is doing analytic work.", role="implication"),
    ]
    return [f]


@probe("growth.codes", "5.7")
def codes(ctx: Context) -> list[Finding]:
    pc = patient_codes(ctx)
    tracked = tracked_codes(ctx)
    values = ", ".join(f"('{icd}')" for _, icd in tracked)
    # Literal and subtree patient counts for every tracked code, in one pass.
    counted = dict(ctx.q(f"""
        WITH t(code) AS (VALUES {values})
        SELECT t.code,
               list_value(count(DISTINCT CASE WHEN pc.code = t.code
                                              THEN pc.patient_id END),
                          count(DISTINCT pc.patient_id))
        FROM t LEFT JOIN {pc} pc ON starts_with(pc.code, t.code)
        GROUP BY t.code"""))
    derived = {icd: ctx.scalar(f"SELECT count({col}) FROM patients_augmented")
               for col, icd in tracked}

    rows = []
    for _, icd in tracked:
        exact, tree = counted.get(icd, [0, 0])
        rows.append({"code": icd, "derived": derived[icd], "exact": exact,
                     "tree": tree, "extra": tree - exact})
    lookup = dict(ctx.q(f"""
        WITH t(code) AS (VALUES {values}), l AS ({ICD_LOOKUP})
        SELECT t.code, coalesce(l.descr, '[not in the ICD-10 lookup]')
        FROM t LEFT JOIN l ON replace(t.code, '.', '') = l.code"""))
    for r in rows:
        r["descr"] = lookup.get(r["code"], "[not in the ICD-10 lookup]")
    rows.sort(key=lambda r: -r["tree"])
    shown = [r for r in rows if ctx.suppress(r["tree"]) is not None]

    zero_exact = [r for r in rows if r["tree"] > 0 and r["exact"] == 0]
    has_desc = [r for r in rows if r["tree"] > r["exact"]]
    no_desc = [r for r in rows if r["tree"] == r["exact"]]
    hierarchical = sum(1 for r in rows if r["derived"] == r["tree"])
    # A flat derivation would show here: the literal count matching the derived
    # column on some code whose subtree count differs. None does.
    flat_evidence = sum(1 for r in rows
                        if r["tree"] > r["exact"] and r["derived"] == r["exact"])
    short = [r for r in rows if r["derived"] not in (r["exact"], r["tree"])]

    ref_total = ctx.scalar("SELECT count(*) FROM referrals")
    fam_rows = []
    matched = 0
    for label, pattern in FAMILIES:
        n, pts, med = ctx.one(
            "SELECT count(*), count(DISTINCT patient_id), "
            "quantile_cont(referral_date_age_in_days, 0.5) / 365.25 "
            f"FROM referrals WHERE lower(requested_specialty) LIKE '{pattern}'")
        matched += n
        fam_rows.append({"family": label, "referrals": n, "patients": pts,
                         "median_age": med, "share": 100.0 * n / ref_total})
    fam_rows.append({"family": "all other specialties",
                     "referrals": ref_total - matched, "patients": None,
                     "median_age": None,
                     "share": 100.0 * (ref_total - matched) / ref_total})

    f = Finding(
        id="growth.codes", part="5.7",
        title="The extract's growth orientation: tracked codes and referral pathways",
        values={"n_codes": len(tracked), "n_shown": len(shown),
                "ref_total": ref_total, "matched": matched,
                "matched_share": 100.0 * matched / ref_total,
                "zero_exact": len(zero_exact), "has_desc": len(has_desc),
                "no_desc": len(no_desc), "hierarchical": hierarchical,
                "flat_evidence": flat_evidence, "short": len(short),
                "short_codes": ", ".join(f"`{r['code']}`" for r in short)},
    )
    f.blocks = [
        Para("This extract was assembled around growth. Cohort entry required a "
             "growth-measurement history (1.4), and the augmentation layer records, "
             "for each patient, the age at which any of {n_codes} specific "
             "diagnosis codes was first recorded. That panel is a design choice made "
             "upstream, and knowing which codes are in it is the difference between "
             "using the derived columns and guessing at them."),
        Para("Because ICD-10 is a hierarchy (3.9), each code is counted here twice: "
             "as a literal string, and as a subtree including every descendant. The "
             "gap between the two columns is what a flat query would miss."),
        Table("t-growth-codes", "The tracked growth-relevant diagnosis codes",
              [C("code", "ICD-10"), C("descr", "description"),
               C("derived", "derived column", ",", align="right"),
               C("exact", "patients, literal code", ",", align="right"),
               C("tree", "patients, code and descendants", ",", align="right"),
               C("extra", "missed by a flat count", ",", align="right")], shown,
              note="Codes carried by fewer patients than the suppression threshold "
                   "are omitted. Counts are recorded frequencies inside a cohort "
                   "that excluded every patient with a code seen fewer than 11 "
                   "times (1.4), so this panel cannot be read as prevalence."),
        Para("**The upstream derivation is hierarchical, and the two count columns "
             "verify it.** {has_desc} of the {n_codes} tracked codes have "
             "descendants in this extract; the other {no_desc} have none, so both "
             "readings coincide and they cannot distinguish the two rules. Of the "
             "{has_desc} that can, **{flat_evidence} match the literal count** — in "
             "every case the derived column follows the subtree. The evidence is "
             "starkest because **all {zero_exact} of those codes never appear as a "
             "literal string at all**: an exact-match query returns zero patients "
             "for `E10`, `P07`, `K50` and the rest, while the derived column "
             "correctly reports hundreds or thousands."),
        Para("{short} codes ({short_codes}) sit slightly below their subtree count. "
             "The shortfall is explained rather than unexplained: those patients "
             "carry the code only on a problem-list entry with no noted date, so no "
             "age could be determined. The derived column therefore means *the "
             "patient carries the code or one of its descendants **and** an age for "
             "it can be established* — not simply that the patient carries it.",
             role="method"),
        Para("The referral resource shows the same orientation from the action side. "
             "Grouping requested specialties into the families a growth question "
             "would reach for accounts for {matched:,} of {ref_total:,} referrals "
             "({matched_share:.1f}%)."),
        Table("t-growth-spec", "Referrals by growth-relevant specialty family",
              [C("family", "specialty family"),
               C("referrals", "referrals", ",", align="right"),
               C("share", "share of all referrals", ".2f", "%", align="right"),
               C("patients", "patients", ",", align="right"),
               C("median_age", "median age", ".2f", " y", align="right")], fam_rows),
        Para("**Implications for analysis.** Use the derived columns when you want "
             "an age at first record and are content with the panel upstream chose; "
             "go to the raw diagnosis resources for anything else, and match by "
             "prefix when you do. These tables describe what the pipeline tracks, "
             "not what is clinically relevant to growth in general: a code absent "
             "from the panel may still be present in 5.1, and a specialty family "
             "here is a string match on a free-text field rather than a clinical "
             "taxonomy.", role="implication"),
    ]
    return [f]


#: Where 5.8 splits the tracked panel. A code whose median age at first record
#: falls below this was attached to the birth episode; one above it was recorded
#: when a child was seen and worked up, which is the only case where an age at
#: first record approximates an age at onset. The line is a stated choice rather
#: than a measured boundary, but it is not a fragile one: no tracked code has a
#: median anywhere near it, and the section publishes the empty band around it
#: so a reader can see that moving the line inside that band changes nothing.
PANEL_SPLIT_YEARS = 1.0

#: ICD-10 prefixes 5.8 uses to make its membership point: a karyotype is
#: established in the nursery, so these land in the birth panel, while the
#: malformation syndromes were equally present at birth and land in the other.
CHROMOSOMAL = ("Q90", "Q96", "Q98")
MALFORMATION = ("Q77", "Q78", "Q87")


@probe("growth.ages", "5.8")
def ages(ctx: Context) -> list[Finding]:
    pc = patient_codes(ctx)
    tracked = tracked_codes(ctx)
    values = ", ".join(f"('{icd}')" for _, icd in tracked)

    # One branch per code, each reading a single column of the augmented layer.
    quartets = dict(ctx.q(" UNION ALL ".join(
        f"SELECT '{icd}' AS code, list_value(count(a), min(a), "
        f"quantile_cont(a, 0.5), avg(a), max(a)) "
        f"FROM (SELECT {col} AS a FROM patients_augmented)"
        for col, icd in tracked)))
    # The patient total over the code and every descendant, as 5.7 counts it.
    tree = dict(ctx.q(f"""
        WITH t(code) AS (VALUES {values})
        SELECT t.code, count(DISTINCT pc.patient_id)
        FROM t LEFT JOIN {pc} pc ON starts_with(pc.code, t.code)
        GROUP BY t.code"""))
    lookup = dict(ctx.q(f"""
        WITH t(code) AS (VALUES {values}), l AS ({ICD_LOOKUP})
        SELECT t.code, coalesce(l.descr, '[not in the ICD-10 lookup]')
        FROM t LEFT JOIN l ON replace(t.code, '.', '') = l.code"""))

    rows = []
    for _, icd in tracked:
        n, lo, med, mean, hi = quartets[icd]
        aged = ctx.suppress(int(n))
        # The four statistics describe the patients `aged` counts, so they are
        # withheld with it rather than published over a handful of children.
        stats = (lo, med, mean, hi) if aged else (None, None, None, None)
        rows.append({"code": icd, "descr": lookup[icd],
                     "patients": ctx.suppress(tree[icd]), "aged": aged,
                     "min": stats[0], "median": stats[1],
                     "mean": stats[2], "max": stats[3]})
    rows.sort(key=lambda r: (-tree[r["code"]], r["code"]))
    shown = [r for r in rows if r["patients"] is not None]

    dated = [r for r in shown if r["median"] is not None]
    # Each panel is ordered by the statistic that assigned it, so a reader can
    # see the split and the empty band around it without recomputing anything.
    dated.sort(key=lambda r: (r["median"], r["code"]))
    birth = [r for r in dated if r["median"] < PANEL_SPLIT_YEARS]
    childhood = [r for r in dated if r["median"] >= PANEL_SPLIT_YEARS]
    # A row whose age statistics were withheld has no median to classify, so it
    # belongs to neither table. None occurs in this snapshot; the alternative to
    # carrying them separately is dropping them from the section silently.
    unclassified = [r for r in shown if r["median"] is None]
    # The empty band the split sits inside: the nearest median below the line and
    # the nearest above it. Any boundary between the two yields these same tables.
    band_lo = max(r["median"] for r in birth) if birth else 0.0
    band_hi = min(r["median"] for r in childhood) if childhood else 0.0
    # The membership claim the prose makes: chromosomal syndromes land in the
    # birth panel because a karyotype is established in the nursery, congenital
    # malformation syndromes in the childhood panel because the coding lags. Both
    # are picked by patient count so the example is the best-supported one.
    chrom = max((r for r in birth if r["code"].startswith(CHROMOSOMAL)),
                key=lambda r: (r["patients"] or 0, r["code"]), default=None)
    late_cong = max((r for r in childhood if r["code"].startswith(MALFORMATION)),
                    key=lambda r: (r["patients"] or 0, r["code"]), default=None)
    negative = [r for r in dated if r["min"] < 0]
    worst = min(negative, key=lambda r: (r["min"], r["code"])) if negative else None
    # The widest gap between mean and median: where a perinatal code also gets
    # recorded years later, the mean moves and the median does not.
    skewed = max(dated, key=lambda r: (r["mean"] - r["median"], r["code"]))
    any_n, any_min, any_med, any_mean, any_max = ctx.one(
        "SELECT count(dx_age_years), min(dx_age_years), "
        "quantile_cont(dx_age_years, 0.5), avg(dx_age_years), max(dx_age_years) "
        "FROM patients_augmented")

    f = Finding(
        id="growth.ages", part="5.8",
        title="Age at first record for each growth-relevant diagnosis code",
        values={
            "n_codes": len(tracked), "n_shown": len(shown),
            "n_birth": len(birth), "n_child": len(childhood),
            "split": PANEL_SPLIT_YEARS,
            "band_lo": band_lo, "band_hi": band_hi,
            "band_width": band_hi - band_lo,
            "n_negative": len(negative),
            "worst_code": worst["code"] if worst else "none",
            "worst_min": worst["min"] if worst else 0.0,
            "skew_code": skewed["code"], "skew_med": skewed["median"],
            "skew_mean": skewed["mean"], "skew_max": skewed["max"],
            "any_n": any_n, "any_min": any_min, "any_med": any_med,
            "any_mean": any_mean, "any_max": any_max,
        },
    )
    # A code with a patient total but no median cannot be assigned to either
    # panel, so it gets its own table rather than vanishing from the section.
    orphans = None
    if unclassified:
        orphans = Table(
            "t-growth-ages-unclassified",
            "Codes carried by enough patients to show a total, but too few with "
            "an age to show a distribution",
            [C("code", "ICD-10"), C("descr", "description"),
             C("patients", "patients, code and descendants", ",", align="right"),
             C("aged", "with an age", ",", align="right")], unclassified,
            note="These cannot be assigned to either panel above: the split is by "
                 "median age at first record, and these codes have no median to "
                 "place.")
    membership = None
    if chrom and late_cong:
        f.values |= {"chrom_code": chrom["code"],
                     "late_cong_code": late_cong["code"],
                     "late_cong_med": late_cong["median"]}
        membership = Para(
            "The membership is not what a reader would guess from the code "
            "chapters. The perinatal codes are in the first table as expected, and "
            "so are the chromosomal syndromes — `{chrom_code}` among them — "
            "because a karyotype is usually established in the nursery. The "
            "congenital *malformation* syndromes are not: they sit in the second "
            "table at medians of years, `{late_cong_code}` at {late_cong_med:.3f}. "
            "A malformation is present at birth by definition, so that figure "
            "dates the moment the coding caught up and nothing about the child. "
            "It is recording lag, measured.")
    f.blocks = [
        Para("5.7 says which codes the tracked panel carries and how many patients "
             "carry each. This section says when. For every one of the {n_codes} "
             "tracked codes, the tables below give the age at which the code was "
             "first recorded — its smallest, median, mean and largest value across "
             "the patients who carry it — beside the patient total counted over the "
             "code and all of its descendants."),
        Para("Age here is the augmented layer's `dx_age_years_` column for the code, "
             "and that column was checked rather than assumed. For all {n_codes} "
             "tracked codes, patient for patient, it reproduces exactly the earliest "
             "age at which the code or any "
             "of its descendants appears on either diagnosis resource: the minimum "
             "of `age_in_days` over prefix-matched encounter diagnoses and "
             "`noted_date_age_in_days` over prefix-matched problem-list entries, "
             "divided by 365.25 and rounded to three decimals. So the ages are "
             "already descendant-inclusive, and they are ages at first **record** — "
             "a patient whose only entry for the code is an undated problem-list "
             "row has no age at all, which is why the patient total and the aged "
             "count differ (5.7).", role="method"),
        Para("**Why this is two tables and not one.** The {n_shown} codes shown "
             "split into two groups that answer different questions, and averaging "
             "across them describes neither. In the first, the median age at first "
             "record falls inside the first year and for most of them within days "
             "of birth: the code was attached to "
             "the birth episode, so its age says when the child was born and not "
             "when anything about growth was observed. In the second, the median "
             "falls in childhood: the code was recorded when a child was brought "
             "in, measured and worked up, which is the only case where an age at "
             "first record approximates an age at onset. One table sorted by "
             "patient count interleaves the two and invites a reader to compare a "
             "birth-episode code against a worked-up one as though the two ages "
             "meant the same thing."),
        Para("The line is drawn at {split:.0f} year, and no tracked code sits near "
             "it. The highest median below the line is {band_lo:.3f} years and the "
             "lowest above it is {band_hi:.3f}, leaving an empty band "
             "{band_width:.3f} years wide: **any boundary chosen inside that band "
             "produces exactly these two tables.** So the split is a real feature "
             "of the panel rather than an artifact of where the line was put — "
             "which is the check worth making before believing any threshold in a "
             "descriptive table. {n_birth} codes fall below and {n_child} above.",
             role="method"),
        Table("t-growth-ages-birth",
              "Panel one: codes recorded at the birth episode, age at first "
              "record in years",
              [C("code", "ICD-10"), C("descr", "description"),
               C("patients", "patients, code and descendants", ",", align="right"),
               C("aged", "with an age", ",", align="right"),
               C("min", "min", ".3f", align="right"),
               C("median", "median", ".3f", align="right"),
               C("mean", "mean", ".3f", align="right"),
               C("max", "max", ".3f", align="right")], birth,
              note="Median age at first record below {split:.0f} year, ordered by that median. Codes carried by "
                   "fewer patients than the suppression threshold are omitted, and "
                   "a code whose aged count falls below it keeps its patient total "
                   "but not its four statistics. Counts are recorded frequencies "
                   "inside a cohort that excluded every patient with a code seen "
                   "fewer than 11 times (1.4), so this panel cannot be read as "
                   "prevalence."),
        membership,
        Table("t-growth-ages-childhood",
              "Panel two: codes recorded when a child was seen and worked up, "
              "age at first record in years",
              [C("code", "ICD-10"), C("descr", "description"),
               C("patients", "patients, code and descendants", ",", align="right"),
               C("aged", "with an age", ",", align="right"),
               C("min", "min", ".3f", align="right"),
               C("median", "median", ".3f", align="right"),
               C("mean", "mean", ".3f", align="right"),
               C("max", "max", ".3f", align="right")], childhood,
              note="Median age at first record at or above {split:.0f} year, ordered by that median. The same "
                   "suppression and cohort caveats apply as in the table above."),
        orphans,
        Para("**The mean and the median disagree by design, and the extremes are "
             "not clean.** `{skew_code}` is the clearest case: a median of "
             "{skew_med:.3f} years against a mean of {skew_mean:.3f} and a maximum "
             "of {skew_max:.3f}, because the same code is also recorded for older "
             "children, and one late record moves a mean that the median does not "
             "feel. The minimum is the more fragile column: it is one patient's "
             "value, and {n_negative} codes have a negative one. `{worst_code}` "
             "reaches {worst_min:.3f} years, which is a record dated before the "
             "child was born rather than a diagnosis age — 3.3 counts those "
             "directly. Read the median and the mean together; read the minimum as "
             "a data-quality probe."),
        Para("Across the whole panel, `dx_age_years` — the age at which any tracked "
             "code was first recorded — is populated for {any_n:,} patients, with a "
             "median of {any_med:.3f} years against a mean of {any_mean:.3f}, a "
             "minimum of {any_min:.3f} and a maximum of {any_max:.3f}. The gap "
             "between that median and that mean is the two panels above, summed."),
        Para("**Implications for analysis.** These are ages at first record, so they "
             "date a coding event and not an onset; the difference matters most "
             "exactly where the median is smallest. If a design needs an index date "
             "per patient, take it from this column only for codes whose median "
             "puts the record after the birth episode, and state the choice. If a "
             "design needs age at onset, this extract does not carry it. Filter "
             "negative values explicitly rather than trusting a minimum, and where "
             "a code's aged count sits below its patient total, decide whether the "
             "undated patients belong in the denominator before computing a rate "
             "over them.", role="implication"),
    ]
    f.blocks = [b for b in f.blocks if b is not None]
    return [f]

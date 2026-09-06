#!/usr/bin/env python3
"""Guard the split between the data report and the files that cite it.

Two passes.

Completeness: the data report must still carry every analysis the project
report once did. That list was verified against the project report's own text
while it still contained the measurements; the comparison now runs against the
list, so deleting a probe is caught as a regression.

Quoted-figure consistency: the overlay, the README and the dataset description
are maintained by hand and defer to the data report, so every figure they quote must still appear there.
This is what stops them drifting apart. The README's checklist counts were wrong
on their first writing, which is why they are checked rather than trusted.

Coverage is judged against the data report's prose and tables with the field
index excluded, because that index names all 254 columns and would score a topic
as covered when nothing analyses it.

    uv run python reports/audit_coverage.py
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
OVERLAY = REPO / "reports" / "growth-chart-literacy-real-data-eda.md"
README = REPO / "README.md"
DATA_DESC = REPO / "docs" / "data_description.md"
NEW_MD = REPO / "reports" / "ppoc-eda" / "ppoc-eda.md"

EXCLUDED = ("Retained in the project overlay, not the data report: "
            "project-specific by definition")

# (old section, analysis, regex proving a counterpart exists in the new report)
TOPICS: list[tuple[str, str, str | None]] = [
    ("§1", "package identity and integrity", r"sha256"),
    ("§1", "linkage and grain", r"Resource map, grain, and keys"),
    ("§2", "sex, ethnicity and race composition", r"Recorded ethnicity"),
    ("§2", "visit history per patient", r"median patient has [\d,]+ visits"),
    ("§3", "visit-level completeness by age", r"Measurement availability by age|availability by age"),
    ("§3", "encounter types", r"Measurement and diagnosis presence by encounter type"),
    ("§3", "Epic versus converted source", r"converted from a legacy"),
    ("§4", "height trajectory supply", r"Trajectory supply"),
    ("§4", "within-child dependence", r"intraclass correlation"),
    ("§4", "age- and sex-stratified growth profile", r"by age band and sex"),
    ("§4", "velocity measures", r"distributed delta and velocity fields"),
    ("§5", "robust channel distributions", r"Distributions and plausibility bounds"),
    ("§5", "review thresholds", r"outside review range"),
    ("§5", "BMI recomputed from height and weight", r"recomputing weight in kilograms"),
    ("§5", "BMI categories", r"Recorded BMI categories"),
    ("§6.1", "height z truncated at +3", r"bounded above at exactly"),
    ("§6.1", "percentile saturation at 0 and 100", r"saturated rather than measured"),
    ("§6.2", "terminal-digit heaping", r"quarter inch"),
    ("§6.3", "imperial-to-metric conversion exactness", r"disagree with .height_in. times 2\.54"),
    ("§6.3", "head circumference double conversion", r"conversion a second time"),
    ("§6.3", "head-circ z defective on plausible values", r"still produce an extreme z"),
    ("§6.4", "zero growth and apparent shrinkage", r"Apparent height loss"),
    ("§6.5", "transcription-error signatures", r"Transcription-error signatures"),
    ("§6.6", "same-day duplicate encounters", r"carry more than one visit"),
    ("§6.6", "same-day measurement disagreement", r"Same-day measurements that disagree"),
    ("§6.7", "delta and velocity reproduction", r"interval rule, inferred"),
    ("§6.8", "measurement presence is not occurrence", r"presence is not measurement occurrence"),
    ("§6.9", "cross-resource temporal integrity", r"Ordering and range checks"),
    ("§6.9", "visit linkage incompleteness", r"populated but unresolved"),
    ("§6.10", "labs as semi-structured text", r"comparator prefix"),
    ("§6.11", "vocabulary and categorical hygiene", r"normalising case and internal whitespace"),
    ("§6.12", "artifact summary", r"Artifact catalogue"),
    ("§7", "patient-level derived flags", r"growth_dx_flag"),
    ("§7", "growth-related code composition", r"tracked growth-relevant diagnosis codes"),
    ("§7", "first-listed encounter diagnoses", r"Most frequently recorded encounter diagnoses"),
    ("§7", "problem-list diagnoses", r"Most frequently recorded problem-list diagnoses"),
    ("§8", "most frequent requested specialties", r"Most frequently requested specialties"),
    ("§8", "referral age distribution", r"Referrals by age at order"),
    ("§8", "growth-relevant specialty families", r"growth-relevant specialty family"),
    ("§8", "referral record semantics and linkage", r"positive-unlabelled|not always documented"),
    ("§9", "top lab procedures", r"Most frequently ordered lab procedures"),
    ("§9", "top medications", r"Most frequently recorded medications"),
    ("§9", "medication record type", r"Record type and date completeness"),
    ("§9", "problem-list resolved-age population", r"currently active"),
    ("§10", "research implications and guardrails", None),
    ("§11", "methods and reproducibility", r"Methods, determinism"),
]

# Figures the hand-maintained files quote, with the section each cites. Every one
# must still appear in the data report; if it does not, that file has drifted.
QUOTED_FIGURES = [
    ("0.925", "4.10", "lag-1 height-z autocorrelation"),
    ("0.821", "4.10", "intraclass correlation"),
    ("1.2", "4.10", "independent observations per child in the limit"),
    ("35,907", "5.6", "patients carrying growth_dx_flag"),
    ("0.027", "5.6", "median age at growth diagnosis"),
    ("15,025", "4.7", "head circumferences outside the review range"),
    ("13,467", "4.7", "of those recoverable by one division"),
    ("1,764", "4.7", "head-circ z defective on a plausible measurement"),
    ("15,800", "4.6", "height visits expected above the +3 bound"),
    ("80.0", "4.2", "percent of heights on a quarter-inch grid"),
    ("0.663", "4.5", "long-interval decrease rate, all ages 2+"),
    ("0.083", "4.5", "the same rate restricted to ages 2-10"),
    ("99.99", "4.8", "velocity reproduction under the interval rule"),
    ("43.7", "4.8", "velocity reproduction under a naive lag"),
    ("335", "4.8", "longest minimum interval in the velocity rule"),
    # docs/data_description.md. The README used to quote these too; it now links
    # the report instead of summarising it, so nothing there needs checking.
    ("250,588", "1.4", "patients after the four cohort exclusions"),
    ("61%", "1.4", "of ICD-10 codes removed with their patients"),
    ("56%", "1.4", "of medications removed with their patients"),
    ("72%", "1.4", "of lab procedures removed with their patients"),
    ("1,204", "3.9", "categories that never appear as a bare code"),
    ("1,327", "3.9", "three-character categories after rollup"),
]


def haystack() -> str:
    md = NEW_MD.read_text(encoding="utf-8")
    start = md.index("### 6.1 Every column in the extract")
    end = md.index("### 7.1", start)
    return md[:start] + md[end:]


def main() -> int:
    if not NEW_MD.is_file():
        print("the neutral report has not been built", file=sys.stderr)
        return 2
    hay = haystack()
    quoting = "".join(f.read_text(encoding="utf-8")
                      for f in (OVERLAY, README, DATA_DESC))

    covered, excluded, missing = [], [], []
    for section, name, pattern in TOPICS:
        if pattern is None:
            excluded.append((section, name))
        elif re.search(pattern, hay, re.IGNORECASE):
            covered.append((section, name))
        else:
            missing.append((section, name, pattern))

    print(f"COVERAGE  {len(covered)} in the data report, "
          f"{len(excluded)} kept in the overlay, "
          f"{len(missing)} missing, of {len(TOPICS)} analyses\n")
    for section, name in excluded:
        print(f"  OVERLAY   {section:6s} {name}\n            -> {EXCLUDED}")
    if missing:
        print()
        for section, name, pattern in missing:
            print(f"  MISSING   {section:6s} {name}  (looked for /{pattern}/)")

    print("\nQUOTED FIGURES  (every figure the overlay or README quotes must "
          "still be in the data report)")
    bad = 0
    for value, section, label in QUOTED_FIGURES:
        quoted = value in quoting
        backed = value in hay
        ok = (not quoted) or backed
        bad += not ok
        if not quoted:
            state = "not quoted"
        elif backed:
            state = "ok"
        else:
            state = "UNBACKED"
        print(f"  {state:11s} {value:>10s}  {section:5s} {label}")

    print()
    if missing or bad:
        print(f"RESULT  {len(missing)} analyses missing, "
              f"{bad} quoted figures unbacked")
        return 1
    print("RESULT  every analysis is in the data report or the overlay; "
          "every quoted figure is backed by the data report")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

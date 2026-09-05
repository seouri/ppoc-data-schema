#!/usr/bin/env python3
"""Check that the project-neutral EDA report covers the project-specific one.

Two passes. The first asks whether each analysis in
`growth-chart-literacy-real-data-eda.md` has a counterpart in
`ppoc-eda/`; the second re-checks a sample of ported figures against the values
the older report states, so "present" cannot mean "present but different".

Coverage is judged against the new report's prose and tables with the field
index excluded, because that index names all 254 columns and would make a bare
field-name match meaningless.

    uv run python reports/audit_coverage.py
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
OLD = REPO / "reports" / "growth-chart-literacy-real-data-eda.md"
NEW_MD = REPO / "reports" / "ppoc-eda" / "ppoc-eda.md"

EXCLUDED = "Deliberately excluded: project-specific by definition"

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

# Figures the new report ported. Each must appear in the OLD report too, so a
# silent change of value shows up as a mismatch rather than as coverage.
PORTED = [
    ("250,588", "cohort size"),
    ("13,467", "head circumferences recoverable by one division"),
    ("1,764", "head-circ z defective on a plausible measurement"),
    ("15,025", "head circumferences outside the review range"),
    ("1,371", "heights recorded in whole feet"),
    ("6,494,473", "visits"),
    ("17,230,681", "lab result components"),
    ("942", "patient-days with disagreeing heights"),
    ("1,087", "nephrology-family referrals"),
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
    hay, old = haystack(), OLD.read_text(encoding="utf-8")

    covered, excluded, missing = [], [], []
    for section, name, pattern in TOPICS:
        if pattern is None:
            excluded.append((section, name))
        elif re.search(pattern, hay, re.IGNORECASE):
            covered.append((section, name))
        else:
            missing.append((section, name, pattern))

    print(f"COVERAGE  {len(covered)} covered, {len(excluded)} excluded by design, "
          f"{len(missing)} missing, of {len(TOPICS)} analyses\n")
    for section, name in excluded:
        print(f"  EXCLUDED  {section:6s} {name}\n            -> {EXCLUDED}")
    if missing:
        print()
        for section, name, pattern in missing:
            print(f"  MISSING   {section:6s} {name}  (looked for /{pattern}/)")

    print("\nPORTED FIGURES  (must match the older report exactly)")
    bad = 0
    for value, label in PORTED:
        in_new, in_old = value in hay, value in old
        ok = in_new and in_old
        bad += not ok
        state = "ok" if ok else ("NOT IN NEW" if in_old else "NOT IN OLD")
        print(f"  {state:11s} {value:>12s}  {label}")

    print()
    if missing or bad:
        print(f"RESULT  {len(missing)} analyses missing, {bad} figures unmatched")
        return 1
    print("RESULT  every analysis is covered or excluded by design; "
          "every sampled figure matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

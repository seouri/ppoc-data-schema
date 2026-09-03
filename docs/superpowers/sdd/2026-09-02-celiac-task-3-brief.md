# Celiac ancillary Task 3: documentation contract

**Files:**
- Modify: `docs/synthetic-generator.md`
- Modify: `README.md`
- Create: `tests/synthetic/test_celiac_ancillary_docs.py`

**Depends on:** celiac Task 2 commit
`095878369968fc54691992d636b436386c8913c1` and its independent review.

## Required content

Add one concise evaluator-only celiac-disease ancillary section beside the
existing ancillary sections in `docs/synthetic-generator.md`. It must name the
public projection and validator functions and every public type:
`CeliacAncillaryPolicy`, `CeliacAncillaryProjection`,
`CeliacAncillaryProjectionUnavailable`, `CeliacAncillaryValidationStatus`,
`CeliacAncillaryCheck`, and `CeliacAncillaryValidationReport`.

The section must state that the API accepts typed in-memory values only and
returns exact-schema `labs`, `medications`, `problem_list`, and `referrals`
tuples. Describe recognition/referral, workup/two-serology-lab, diagnosis/
unresolved-problem, and visible-diagnosis plus hidden treatment-start gating;
state that hidden treatment alone and treatment before a censored diagnosis do
not create medication rows. Name the exact fictional constants and values:
`SYN-CELIAC-DISEASE`, `SYN-CELIAC-TTG-IGA`, `SYN-CELIAC-TOTAL-IGA`,
`result_flag="Synthetic"`, `Synthetic Pediatric Gastroenterology`,
`Synthetic gluten-free intervention`, and `med_record_type="Internal"`.

Explicitly say the labels are fictional/nonclinical and make no ICD, LOINC, or
RxNorm claim. State that latent state remains hidden, output is deterministic,
immutable, exact-schema, and evaluator-only, and that healthy and all other
disorder kinds return empty tuples. Preserve the no-`obesity_flag` boundary.
State that runtime/package integration, prevalence/demographic calibration,
privacy/non-matchability, clinical review, release authorization, real or
held-out data, and optional Synthea conformance remain deferred and are not
ordinary-development prerequisites.

Add one concise README sentence linking the celiac plan/spec and the guide.
Preserve the established exact substring `excess-weight ancillary pathway is
a separate roadmap slice`; prior docs tests depend on that wording.

## Tests

The docs test must assert the public symbol names, exact fictional values,
in-memory/evaluator-only and exact-schema wording, treatment suppression, the
deferred boundaries, the README guide/plan/spec links, and the preserved
excess-weight phrase. It must not copy the guide body into README.

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q -p no:cacheprovider tests/synthetic/test_celiac_ancillary_docs.py
git diff --check
```

Commit only the three requested files as:

```text
docs: describe celiac ancillary fixtures
```

Write the implementation report to
`.superpowers/sdd/2026-09-02-celiac-ancillary-pathway/task-3-report.md`.

# Governed Privacy-Audit Evidence Design

**Date:** 2026-08-31
**Status:** Approved roadmap slice under the parent synthetic-fixture design
**Parent design:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)
**Prerequisite:** [Patient-disjoint held-out validation](2026-08-31-heldout-validation-design.md)

## Purpose and claim boundary

This slice adds a standalone, offline privacy auditor for a completely generated exact-schema package. It evaluates the package against a governed reference snapshot and any explicitly supplied held-out, shadow, prior-release, and control packages. It emits only aggregate evidence and a policy decision; patient rows, identifiers, candidate links, feature vectors, distances, attack examples, and secret inputs remain process-local.

The strongest automated conclusion is qualified: under the documented recipient, release context, attacker knowledge, attacks, controls, and decision rules, the generated package did not exhibit a measured linkage, membership, or attribute-inference signal above the approved tolerances. The auditor may not claim that a generated patient cannot be matched, that privacy risk is zero, that a nearest profile is the same person, or that the package is HIPAA de-identified or release-approved. A human privacy expert and data custodian remain responsible for release authorization.

The implementation is intentionally a bounded evidence layer rather than a universal anonymization proof. It uses exact-schema staging and fixed feature extraction, accepts no arbitrary SQL or caller-selected columns, and fails closed when an applicable attack lacks sufficient evidence. The normal generator and its visible package APIs do not import or consume this module.

## Goals

1. Validate the real reference, generated package, and optional control packages against the repository's exact eight-resource schema using the existing secure descriptor and resource staging rules.
2. Require zero overlap among visible real and generated identifiers and zero complete eligible longitudinal trajectory reproductions; empty or underpowered profiles are reported as unevaluable rather than safety evidence.
3. Run fixed, documented aggregate screens for nearest-neighbor proximity, record linkage, membership inference, attribute disclosure, and composition with prior synthetic releases.
4. Support independent negative and intentionally copied/overfit positive controls so the audit can detect both false alarms and known leakage.
5. Load a strict versioned policy before evaluation. The policy fixes attacker knowledge, minimum evaluable size, confidence method, subgroup handling, thresholds, required controls, and review metadata; no value learned from the package can alter it.
6. Emit deterministic machine-readable JSON and a concise human summary with aggregate metrics and uncertainty only. Underpowered cells and missing required inputs are `UNEVALUABLE`, never `PASS`.
7. Preserve the governed boundary: no report or exception contains patient/visit identifiers, paths, keys, candidate pairs, patient-level distances, raw feature values, or hidden truth.

## Non-goals

- No assertion of absolute non-matchability, zero privacy risk, formal differential-privacy guarantee, HIPAA status, clinical validity, prevalence validity, or release approval.
- No arbitrary feature/column selection, nearest-neighbor export, linkage candidate export, patient-level score, raw diagnosis, shadow membership label, or attack example in a report.
- No use of the audit result to tune, resample, calibrate, or otherwise change generation; no use of held-out or shadow rows outside the auditor process.
- No default real-data path, policy, output path, secret, or prior-release discovery; all governed inputs are explicit.
- No overwrite of an output or lifecycle directory and no publication, upload, commit, or copy outside the supplied output location.

## Threat model and fixed feature boundary

The policy names the recipient class and release context and selects from these fixed attacker-knowledge components: `demographics`, `timing`, `utilization`, `trajectory`, and `diagnosis`. Components are derived only from declared schema fields: sex, ethnicity, race selections, observation ages, visit counts, normalized anthropometric observations, and the recorded `growth_dx_flag`. The auditor never accepts a free-form column name or SQL expression.

The reference package is the governed calibration-side snapshot supplied as `--real-root`. An optional `--heldout-root` supplies a patient-disjoint real control for distribution-shift and linkage comparisons. Both descriptors must match the repository schema fingerprint and must not carry the synthetic marker. The generated package and all optional control/prior/shadow packages must carry `x-synthetic: true`; every package is staged in a separate private DuckDB connection with regular non-symlinked descriptor and resource paths.

The auditor uses a fixed internal profile representation. A trajectory observation is `(age_in_days, height_cm, weight_kg, head_circ_cm)` with finite values rounded to six decimal places; an eligible profile has at least the policy's `longitudinal_min_observations` observations containing at least one anthropometric value. Internal hashes and component tuples are never serialized. Profiles with no eligible trajectory remain in a private count and cannot improve a privacy result.

## Strict policy contract

`src/synthetic/privacy_audit.py` defines immutable `PrivacyPolicy`, `PrivacyRunConfig`, `PrivacyControlResult`, `PrivacyAuditReport`, and `PrivacyAuditResult` models plus `load_privacy_policy`, `audit_privacy`, `write_privacy_report`, and `main`.

The policy JSON has exactly these top-level keys:

```text
policy_id
policy_version
schema_fingerprint
recipient_class
release_context
accounting_unit
attacker_knowledge
confidence_method
minimum_evaluable_patients
longitudinal_min_observations
required_controls
subgroups
minimum_shadow_runs
minimum_prior_releases
review_date
approver
thresholds
```

`policy_id`, `policy_version`, `recipient_class`, `release_context`, and `approver` are aggregate-safe ASCII tokens. `schema_fingerprint` is a lowercase SHA-256 and must equal the repository fingerprint. `accounting_unit` is currently `patient`, and `confidence_method` is currently `wilson_95`. `attacker_knowledge` is a nonempty canonical list drawn from the five fixed components with no duplicates. `minimum_evaluable_patients` is at least three, `longitudinal_min_observations` is at least three, and shadow/prior minimums are nonnegative integers. `review_date` is an exact Gregorian `YYYY-MM-DD` value.

`required_controls` is a canonical subset of `identifier_overlap`, `exact_reproduction`, `nearest_neighbor`, `linkage`, `membership_inference`, `attribute_disclosure`, `composition`, `negative_control`, and `positive_control`; `identifier_overlap` and `exact_reproduction` are always required even if omitted from the JSON list. `subgroups` is a nonempty canonical subset of `overall` and `sex`; unsupported subgroup values fail closed. `thresholds` has exactly these finite values in `[0,1]`: `identifier_overlap_rate`, `exact_reproduction_rate`, `nearest_neighbor_zero_rate`, `nearest_neighbor_unique_rate`, `linkage_advantage`, `membership_inference_advantage`, `attribute_disclosure_advantage`, `composition_reproduction_rate`, `negative_control_advantage`, and `positive_control_advantage`. The first two and composition thresholds default to zero in approved policies; all numeric thresholds remain policy decisions rather than universal definitions of acceptable risk.

Unknown or missing keys, duplicate keys, nonfinite constants, booleans in numeric fields, unsafe tokens, duplicate list values, unsupported controls/components, invalid dates, schema drift, or out-of-range thresholds fail before any package rows are staged.

## Controls and decision rules

Every control returns `PASS`, `FAIL`, or `UNEVALUABLE`, aggregate metrics, and an aggregate reason code. A control's evaluated sample count and uncertainty interval appear only when its sample meets the policy minimum; undersized subgroup cells have no metrics and cannot be counted as passes. Wilson 95% intervals are deterministic and rounded to six decimal places.

1. **Identifier overlap.** Collect nonempty values from every declared primary-key and `*_id` field in the real and generated packages. Any overlap is a mandatory `FAIL`; a nonempty generated identifier set is required for evaluation. Only the overlap rate and aggregate counts are retained.
2. **Exact longitudinal reproduction.** Hash the normalized eligible trajectory tuple for each package. Any generated eligible profile whose hash occurs in the real reference is a mandatory `FAIL`; the complete-reproduction rate is compared with the zero threshold. Ineligible/empty profiles are counted separately and never count as safety evidence.
3. **Nearest-neighbor screen.** Compare generated profiles with reference profiles through fixed component-bucket Hamming proximity. Report aggregate zero-proximity rate, unique-nearest rate, and nearest-versus-second-nearest margin bins, with the held-out real package as a distribution-shift control when supplied. No pair, profile hash, or patient-level score leaves the process. A missing held-out control when this control is required is `UNEVALUABLE`.
4. **Linkage attack.** For each selected attacker-knowledge component and their fixed full combination, calculate the rate of unique exact candidate keys for generated profiles and compare it with held-out-real and deterministic permutation controls. The report retains only the maximum aggregate advantage, rate intervals, and evaluated sample counts. Proximity alone is not identity disclosure.
5. **Membership inference.** A strict private shadow manifest supplies multiple generated shadow packages and real patient membership labels. The auditor maps labels to internal trajectory hashes, evaluates a fixed exact-match score attack on untouched shadow profiles, and reports the maximum membership advantage across shadows. Fewer than `minimum_shadow_runs` valid runs or too few labeled profiles is `UNEVALUABLE`; a single calibration-versus-held-out comparison cannot satisfy this control.
6. **Attribute disclosure.** For eligible exact profile links, infer only the recorded `growth_dx_flag` and compare attack accuracy with the reference majority and held-out baseline. No diagnosis value, profile, or inferred patient attribute is exported. Missing or inconsistent sensitive labels are `UNEVALUABLE`.
7. **Composition.** Compare eligible generated trajectory hashes with every explicitly supplied prior synthetic release. Any exact reproduction above the policy threshold is `FAIL`. No prior release is discovered implicitly; a required but absent prior set is `UNEVALUABLE`.
8. **Controls.** A supplied independent negative-control package must not exceed its configured advantage threshold. A supplied copied/overfit positive-control package must exceed the configured minimum advantage, proving that the attack harness can detect leakage. Missing required controls are `UNEVALUABLE`, not `PASS`.

The global status is `FAIL` if any evaluated control fails, including either mandatory zero-risk control. Otherwise it is `UNEVALUABLE` if any required control is unevaluable; otherwise it is `PASS`. Optional controls that are not supplied are recorded as unevaluable but do not block a policy that does not require them. A pass is always the qualified policy-bound evidence described above.

## Shadow-manifest and CLI inputs

The optional shadow manifest is a strict regular JSON file with exactly `version` and `runs`. `version` is `privacy-shadow-v1`; each run has exactly `run_id`, `package_root`, and `members`, where `run_id` is an aggregate-safe token, `package_root` is an operator-supplied path, and `members` is a nonempty list of reference patient identifiers kept entirely inside the governed process. Unknown members, duplicate runs, duplicate members, symlinks, malformed JSON, and oversized files fail closed without echoing an identifier.

The command requires explicit `--real-root`, `--synthetic-root`, `--policy`, and `--output` flags. It accepts optional repeated `--prior-release-root` flags plus `--heldout-root`, `--shadow-manifest`, `--negative-control-root`, and `--positive-control-root`. The real and synthetic descriptors are discovered only beneath their supplied roots; no policy path or package path is serialized in the report.

```sh
uv run python -m synthetic.privacy_audit \
  --real-root /governed/calibration \
  --heldout-root /governed/heldout \
  --synthetic-root /fixtures/development-20260830 \
  --policy /governed/approved-risk-policy.json \
  --shadow-manifest /governed/shadow-manifest.json \
  --prior-release-root /governed/prior-release-1 \
  --output /governed/privacy-audit-report
```

The CLI returns zero only for a promoted `PASS` report, one for a promoted `FAIL` or `UNEVALUABLE` report or a redacted hard failure, and two for parser errors. Stderr contains only fixed aggregate messages. A library caller supplies a `PrivacyRunConfig` with immutable `Path` tuples and receives no live connection or row data.

## Aggregate report and lifecycle

`PrivacyAuditReport` serializes exactly these top-level keys: `report_version`, `status`, `policy`, `schema_fingerprint`, `synthetic_artifact_id`, `control_counts`, `controls`, and `decision_reasons`. The report version is `privacy-audit-report-v1`. `policy` contains only policy identity and review metadata (`policy_id`, `policy_version`, `recipient_class`, `release_context`, `accounting_unit`, `review_date`); paths, key identifiers, member labels, and policy thresholds are not copied into the report. `controls` is sorted by fixed control ID and contains only `control_id`, `status`, `metrics`, and `reason_code`.

Metrics are aggregate rates, Wilson interval endpoints, rounded distribution-bin rates, and sample counts for evaluable cells. They never contain a patient/visit identifier, source path, secret, raw category, candidate pair, profile hash, patient-level distance, attack example, or undersized cell. The model rejects unsafe metric keys and values. Canonical JSON is compact, sorted ASCII with a trailing newline; repeated approved inputs produce byte-identical report bytes.

Writing uses `RunDirectory` with a lifecycle token derived from the synthetic artifact identity and policy identity. The target, `.partial`, and `.failed` paths must not already exist. The auditor writes only `privacy-audit-report.json` and `privacy-audit-summary.txt`, fsyncs and reparses both, compares canonical bytes, and promotes without replacement. Any output failure leaves a redacted `failure.json` with `{"status":"FAILED","reason":"privacy output validation failed"}` and no report promotion.

## Testing and acceptance

Tests use only fictional exact-schema packages and test-only keys/manifests. They cover strict policy parsing, secure package staging, marker/schema/path enforcement, identifier overlap, exact trajectory copying, empty/underpowered profiles, nearest-neighbor controls, permutation linkage, shadow membership, attribute inference, prior-release composition, positive/negative controls, subgroup suppression, uncertainty, deterministic bytes, lifecycle collision, CLI exit/redaction, and the visible-generator import boundary.

The slice is complete when an intentionally copied package fails the mandatory overlap/reproduction controls, an overfit shadow fails membership, a rare copied pattern fails the configured subgroup control, an independent negative control does not falsely fail, missing evidence is `UNEVALUABLE`, and all promoted reports contain aggregate data only. Full tests, Ruff, schema validation, whitespace checks, main/origin parity, and documentation must pass before merge. The result remains privacy evidence for human review, not non-matchability proof or release authorization.

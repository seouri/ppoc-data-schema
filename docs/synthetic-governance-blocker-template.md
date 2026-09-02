# Synthetic generator governance blocker intake template

> Template only. Complete a copy in the governed review workspace; do not commit the completed form. Never place patient rows, identifiers, partition-key values, candidate links, raw control output, or other secrets in this template.

## How to use

1. Copy this file to the approved review workspace and replace every `[[PLACEHOLDER]]` with a controlled reference or an aggregate-safe description.
2. Set each blocker to `OPEN`, `IN REVIEW`, or `CLEARED`. A declaration alone does not clear a blocker; `CLEARED` requires an evidence or approval reference and a reviewer/date.
3. Record secret locations and identifiers, never secret values. Keep patient-level material inside the governed process and refer to it only by an approved aggregate report or controlled record identifier.
4. Do not run a governed command until its execution gate below is cleared. A passing report remains bounded evidence and does not by itself authorize release.

## Intake record

- Intake ID: `[[INTAKE_ID]]`
- Requested purpose: `[[APPROVED_PURPOSE]]`
- Requested scope: `[[SCOPE_OF_GENERATION_OR_EVALUATION]]`
- Source snapshot label: `[[SNAPSHOT_ID]]`
- Candidate source-root alias: `[[SOURCE_ROOT_ALIAS]]`
- Approved descriptor reference: `[[DESCRIPTOR_REFERENCE]]`
- Repository schema fingerprint: `[[SCHEMA_FINGERPRINT]]`
- Requested output alias: `[[OUTPUT_ROOT_ALIAS]]`
- Requesting operator: `[[OPERATOR_NAME_OR_CONTROLLED_ID]]`
- Data custodian: `[[DATA_CUSTODIAN_NAME_OR_CONTROLLED_ID]]`
- Privacy reviewer: `[[PRIVACY_REVIEWER_NAME_OR_CONTROLLED_ID]]`
- Clinical reviewer: `[[CLINICAL_REVIEWER_NAME_OR_CONTROLLED_ID]]`
- Legal/licensing reviewer: `[[LEGAL_REVIEWER_NAME_OR_CONTROLLED_ID]]`
- Intake opened: `[[UTC_DATE_TIME]]`
- Intake review date: `[[UTC_DATE_TIME]]`

## Blocker register

| ID | Blocker | Status | Owner | Evidence or approval reference | Review date |
| --- | --- | --- | --- | --- | --- |
| GOV-001 | Operator and purpose authorization | `[[OPEN \| IN REVIEW \| CLEARED]]` | `[[OWNER]]` | `[[REFERENCE]]` | `[[DATE]]` |
| GOV-002 | Source descriptor and snapshot binding | `[[OPEN \| IN REVIEW \| CLEARED]]` | `[[OWNER]]` | `[[REFERENCE]]` | `[[DATE]]` |
| GOV-003 | Patient-disjoint partition policy and key | `[[OPEN \| IN REVIEW \| CLEARED]]` | `[[OWNER]]` | `[[REFERENCE]]` | `[[DATE]]` |
| GOV-004 | Aggregate disclosure policy | `[[OPEN \| IN REVIEW \| CLEARED]]` | `[[OWNER]]` | `[[REFERENCE]]` | `[[DATE]]` |
| GOV-005 | Governed execution and output environment | `[[OPEN \| IN REVIEW \| CLEARED]]` | `[[OWNER]]` | `[[REFERENCE]]` | `[[DATE]]` |
| GOV-006 | Calibration artifact and report | `[[OPEN \| IN REVIEW \| CLEARED]]` | `[[OWNER]]` | `[[REFERENCE]]` | `[[DATE]]` |
| GOV-007 | Frozen held-out/prevalence fidelity policy | `[[OPEN \| IN REVIEW \| CLEARED]]` | `[[OWNER]]` | `[[REFERENCE]]` | `[[DATE]]` |
| GOV-008 | Independent multi-seed package set | `[[OPEN \| IN REVIEW \| CLEARED]]` | `[[OWNER]]` | `[[REFERENCE]]` | `[[DATE]]` |
| GOV-009 | Privacy-risk policy and control packages | `[[OPEN \| IN REVIEW \| CLEARED]]` | `[[OWNER]]` | `[[REFERENCE]]` | `[[DATE]]` |
| GOV-010 | Non-matchability claim wording | `[[OPEN \| IN REVIEW \| CLEARED]]` | `[[OWNER]]` | `[[REFERENCE]]` | `[[DATE]]` |
| GOV-011 | Derivation/reference authority | `[[OPEN \| IN REVIEW \| CLEARED]]` | `[[OWNER]]` | `[[REFERENCE]]` | `[[DATE]]` |
| GOV-012 | Clinical pathway and disorder scope | `[[OPEN \| IN REVIEW \| CLEARED]]` | `[[OWNER]]` | `[[REFERENCE]]` | `[[DATE]]` |
| GOV-013 | Temporal, task-utility, and clinical evidence | `[[OPEN \| IN REVIEW \| CLEARED]]` | `[[OWNER]]` | `[[REFERENCE]]` | `[[DATE]]` |
| GOV-014 | Optional Synthea handoff | `[[OPEN \| IN REVIEW \| CLEARED]]` | `[[OWNER]]` | `[[REFERENCE]]` | `[[DATE]]` |
| GOV-015 | Release, provenance, and licensing approval | `[[OPEN \| IN REVIEW \| CLEARED]]` | `[[OWNER]]` | `[[REFERENCE]]` | `[[DATE]]` |

## Detailed clearance records

### GOV-001 — Operator and purpose authorization

- Status: `[[OPEN | IN REVIEW | CLEARED]]`
- Custodian approval reference: `[[IRB_DUA_CUSTODIAN_APPROVAL_REFERENCE]]`
- Authorized operator or study-personnel record: `[[AUTHORIZED_OPERATOR_RECORD]]`
- Permitted purpose and recipient class: `[[PERMITTED_PURPOSE_AND_RECIPIENT_CLASS]]`
- Approved snapshot and expiry/review date: `[[SNAPSHOT_AND_EXPIRY]]`
- Data-custodian decision and date: `[[DECISION_REFERENCE_AND_DATE]]`
- Exit criterion: the custodian confirms that the named operator, purpose, snapshot, environment, and outputs are within the approved protocol and agreement.

### GOV-002 — Source descriptor and snapshot binding

- Status: `[[OPEN | IN REVIEW | CLEARED]]`
- Approved descriptor reference: `[[DESCRIPTOR_REFERENCE]]`
- Descriptor schema fingerprint: `[[SCHEMA_FINGERPRINT]]`
- Snapshot label and provenance reference: `[[SNAPSHOT_ID_AND_PROVENANCE_REFERENCE]]`
- Approved source-root identity or alias: `[[SOURCE_ROOT_IDENTITY_OR_ALIAS]]`
- Preflight result reference: `[[PREFLIGHT_REPORT_REFERENCE]]`
- Header/encoding/link validation date: `[[VALIDATION_DATE]]`
- Exit criterion: the approved root is confirmed as the declared snapshot and passes the exact eight-resource, fingerprint, path, encoding, header, and structural checks before patient-level aggregation.

### GOV-003 — Patient-disjoint partition policy and key

- Status: `[[OPEN | IN REVIEW | CLEARED]]`
- Partition-policy ID/version: `[[PARTITION_POLICY_ID_VERSION]]`
- Calibration basis points and minimum partition support: `[[BASIS_POINTS_AND_MINIMUM_SUPPORT]]`
- Key ID and controlled secret-store reference: `[[KEY_ID_AND_SECRET_REFERENCE]]`
- Key rotation/retention decision: `[[KEY_RETENTION_AND_ROTATION_DECISION]]`
- Approved partition reviewer/date: `[[REVIEW_REFERENCE_AND_DATE]]`
- Exit criterion: the HMAC key is available only to the governed process, the policy is approved, and every patient is assigned to exactly one permitted partition.

### GOV-004 — Aggregate disclosure policy

- Status: `[[OPEN | IN REVIEW | CLEARED]]`
- Disclosure-policy ID/version: `[[DISCLOSURE_POLICY_ID_VERSION]]`
- Minimum cell/support threshold: `[[MINIMUM_CELL_COUNT]]`
- Continuous rounding rule: `[[ROUNDING_RULE]]`
- Suppression and missingness rules: `[[SUPPRESSION_RULES]]`
- Approved target families and recipient class: `[[TARGET_FAMILIES_AND_RECIPIENT_CLASS]]`
- Privacy/custodian approval reference/date: `[[APPROVAL_REFERENCE_AND_DATE]]`
- Exit criterion: all released values are disclosure-controlled aggregates, suppressed cells remain unevaluable, and the policy is approved for this purpose.

### GOV-005 — Governed execution and output environment

- Status: `[[OPEN | IN REVIEW | CLEARED]]`
- Governed environment or job reference: `[[ENVIRONMENT_OR_JOB_REFERENCE]]`
- Output directory alias: `[[OUTPUT_DIRECTORY_ALIAS]]`
- Access, retention, and deletion policy: `[[ACCESS_RETENTION_POLICY]]`
- No-replace/lifecycle audit reference: `[[LIFECYCLE_AUDIT_REFERENCE]]`
- Operator and custodian sign-off/date: `[[SIGNOFF_REFERENCE_AND_DATE]]`
- Exit criterion: the run executes in the approved environment and writes only the declared aggregate outputs without overwriting or exporting secrets.

### GOV-006 — Calibration artifact and report

- Status: `[[OPEN | IN REVIEW | CLEARED]]`
- Calibration artifact ID/reference: `[[CALIBRATION_ARTIFACT_ID_REFERENCE]]`
- Calibration report ID/reference: `[[CALIBRATION_REPORT_ID_REFERENCE]]`
- Source snapshot and aggregate hash: `[[SNAPSHOT_AND_AGGREGATE_HASH_REFERENCE]]`
- Disclosure and partition-policy identities: `[[POLICY_IDENTITIES]]`
- Aggregate-only review reference/date: `[[REVIEW_REFERENCE_AND_DATE]]`
- Exit criterion: the artifact and report reparse canonically, agree on snapshot/schema/policies, contain no rows or identifiers, and are approved for downstream held-out evaluation.

### GOV-007 — Frozen held-out/prevalence fidelity policy

- Status: `[[OPEN | IN REVIEW | CLEARED]]`
- Fidelity-policy ID/version: `[[FIDELITY_POLICY_ID_VERSION]]`
- Target-registry version: `[[TARGET_REGISTRY_VERSION]]`
- Required target families: `[[REQUIRED_TARGET_FAMILIES]]`
- Age windows, tolerances, and minimum support: `[[AGE_WINDOWS_TOLERANCES_SUPPORT]]`
- Predeclared decision rule and reviewer/date: `[[DECISION_RULE_REVIEW_REFERENCE_DATE]]`
- Exit criterion: the policy is frozen before comparison and defines support, suppression, tolerance, and `PASS`/`FAIL`/`UNEVALUABLE` semantics without adaptive tuning.

### GOV-008 — Independent multi-seed package set

- Status: `[[OPEN | IN REVIEW | CLEARED]]`
- Required run count: `[[MINIMUM_RUN_COUNT]]`
- Predeclared seeds: `[[SEED_LIST]]`
- Package aliases and manifest references: `[[PACKAGE_ALIAS_AND_MANIFEST_REFERENCES]]`
- Package/manifest digest and immutability check: `[[DIGEST_CHECK_REFERENCE]]`
- Derivation classification: `[[TEST_ONLY_OR_APPROVED_NON_TEST_REFERENCE]]`
- Exit criterion: the package roots are distinct and immutable for evaluation, each has the exact schema/inventory/manifest binding, and the manifest classification satisfies the approved evidence gate.

### GOV-009 — Privacy-risk policy and control packages

- Status: `[[OPEN | IN REVIEW | CLEARED]]`
- Privacy-policy ID/version and recipient class: `[[PRIVACY_POLICY_ID_VERSION_RECIPIENT_CLASS]]`
- Required controls and thresholds: `[[REQUIRED_CONTROLS_AND_THRESHOLDS]]`
- Held-out, shadow, prior-release, and control-package aliases: `[[CONTROL_ALIASES]]`
- Minimum evaluable support and confidence method: `[[SUPPORT_AND_CONFIDENCE_RULE]]`
- Privacy-expert approval reference/date: `[[APPROVAL_REFERENCE_AND_DATE]]`
- Exit criterion: the auditor can run every required control with approved inputs and emit aggregate-only evidence; absent required evidence remains `UNEVALUABLE`.

### GOV-010 — Non-matchability claim wording

- Status: `[[OPEN | IN REVIEW | CLEARED]]`
- Approved qualified claim: `[[QUALIFIED_POLICY_BOUND_PRIVACY_CLAIM]]`
- Explicitly prohibited claims: `[[ABSOLUTE_NON_MATCHABILITY_ZERO_RISK_OR_AUTOMATIC_DEIDENTIFICATION_CLAIMS]]`
- Risk acceptance and residual-risk reference: `[[RESIDUAL_RISK_DECISION_REFERENCE]]`
- Privacy-expert and custodian review/date: `[[REVIEW_REFERENCE_AND_DATE]]`
- Exit criterion: communications use only the approved qualified wording; no finite test is represented as proof of absolute non-matchability.

### GOV-011 — Derivation/reference authority

- Status: `[[OPEN | IN REVIEW | CLEARED]]`
- Oracle identity/fingerprint/source revision: `[[ORACLE_IDENTITY_FINGERPRINT_REVISION]]`
- Reference-standard identity/fingerprint: `[[REFERENCE_STANDARD_IDENTITY_FINGERPRINT]]`
- Golden, bidirectional-parity, and synthetic-fuzz evidence references: `[[EVIDENCE_REFERENCES]]`
- Clinical/code-set review reference: `[[CLINICAL_REVIEW_REFERENCE]]`
- Derivation-binding ID/version/classification: `[[BINDING_ID_VERSION_AND_CLASSIFICATION]]`
- Exit criterion: an independently reviewed non-test binding exists before any clinical or release claim; otherwise every output remains `test_only=true`.

### GOV-012 — Clinical pathway and disorder scope

- Status: `[[OPEN | IN REVIEW | CLEARED]]`
- Included disorders/pathways: `[[INCLUDED_SCOPE]]`
- Excluded disorders/resources/pathways: `[[EXCLUDED_SCOPE]]`
- Clinical reference and review decision: `[[CLINICAL_REFERENCE_AND_DECISION]]`
- Scope statement for users: `[[USER_FACING_SCOPE_STATEMENT]]`
- Exit criterion: the supported clinical scope is either explicitly restricted to reviewed pathways or expanded with reviewed descendants and validation evidence.

### GOV-013 — Temporal, task-utility, and clinical evidence

- Status: `[[OPEN | IN REVIEW | CLEARED]]`
- Temporal-fidelity policy and report reference: `[[TEMPORAL_POLICY_REPORT_REFERENCE]]`
- Task-utility protocol, frozen model, and split: `[[TASK_PROTOCOL_MODEL_SPLIT_REFERENCE]]`
- Real-label source and approval reference: `[[LABEL_SOURCE_APPROVAL_REFERENCE]]`
- Predeclared margins and subgroup plan: `[[MARGINS_AND_SUBGROUP_PLAN]]`
- Clinical reviewer/date: `[[REVIEW_REFERENCE_AND_DATE]]`
- Exit criterion: any real-data performance or clinical-utility claim has a separately approved protocol, frozen evaluation inputs, and human review.

### GOV-014 — Optional Synthea handoff

- Status: `[[OPEN | IN REVIEW | CLEARED]]`
- Scope decision: `[[REQUIRED_OR_DEFERRED]]`
- Pinned engine revision/digest: `[[ENGINE_REVISION_AND_SHA256]]`
- Module bundle and pediatric growth extension identities: `[[MODULE_AND_GROWTH_EXTENSION_REFERENCES]]`
- Event adapter, PPOC exporter, and configuration identities: `[[ADAPTER_EXPORTER_CONFIGURATION_REFERENCES]]`
- License/attribution and conformance review references: `[[LICENSE_AND_CONFORMANCE_REFERENCES]]`
- Exit criterion: if deferred, record that the native route remains in scope; if required, complete the external pinned handoff and the same validation, privacy, clinical, and release gates.

### GOV-015 — Release, provenance, and licensing approval

- Status: `[[OPEN | IN REVIEW | CLEARED]]`
- Intended recipients and use: `[[RECIPIENTS_AND_USE]]`
- Data-custodian release decision: `[[CUSTODIAN_RELEASE_REFERENCE]]`
- Privacy release decision: `[[PRIVACY_RELEASE_REFERENCE]]`
- Clinical release decision: `[[CLINICAL_RELEASE_REFERENCE]]`
- Legal/licensing and public-source provenance decision: `[[LEGAL_LICENSE_REFERENCE]]`
- Release record, version, and date: `[[RELEASE_RECORD_VERSION_DATE]]`
- Exit criterion: all required human approvals are recorded for the exact artifact/version and intended recipient; development tests and aggregate reports are not treated as release authorization.

## Execution gates

| Action | Required cleared blockers |
| --- | --- |
| Governed calibration | `GOV-001` through `GOV-005` |
| Held-out validation | `GOV-001` through `GOV-007`, plus the generated package reference |
| Multi-run prevalence evidence | `GOV-001` through `GOV-008` |
| Privacy audit | `GOV-001`, `GOV-002`, `GOV-004`, `GOV-005`, `GOV-009`, and `GOV-010` |
| Non-test derivation or clinical claim | `GOV-011` through `GOV-013` |
| Optional Synthea comparison | `GOV-007` through `GOV-014` and the external Synthea handoff |
| Release or external distribution | All applicable blockers, including `GOV-015` |

## Final review record

- Outstanding blockers and rationale: `[[OUTSTANDING_BLOCKERS_OR_NONE]]`
- Aggregate reports reviewed: `[[REPORT_REFERENCES]]`
- Patient-level material confirmed retained in governed process only: `[[YES_NO_AND_CONTROL_REFERENCE]]`
- Final custodian decision: `[[APPROVED_REJECTED_OR_MORE_EVIDENCE_REQUIRED]]`
- Final decision reference/date: `[[FINAL_DECISION_REFERENCE_AND_DATE]]`

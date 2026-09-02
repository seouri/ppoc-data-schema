# Evaluator-Only Observed Resource Contract

**Date:** 2026-08-31
**Status:** Implementation complete; evaluator-only in-memory contract; clinical, privacy, and release gates pending
**Parent:** [Synthetic Pediatric Growth Fixture System Design](2026-08-30-synthetic-growth-fixtures-design.md)
**Prerequisite:** [Evaluator-Only Observation Frame Contract](2026-08-31-observation-frame-design.md)

## Purpose and boundary

The observation-frame slice produces a safe visible longitudinal record, but it
does not yet bridge that record to the repository's exact-schema base resources.
This slice adds an engine-neutral, in-memory resource contract that consumes one
validated fictional `ObservationFrame`, projects its selected visits and
recorded fictional event descendants into descriptor-shaped base rows, and
checks the resulting patient/visit/event relationships.

The resource contract is evaluator-only. It does not read a descriptor path,
open CSVs, write files, invoke the smoke CLI, call calibration/held-out/privacy
code, consume real data, or produce a package that can be labeled valid or
released. The caller supplies an already-loaded descriptor mapping to a pure
`ResourceShape.from_descriptor` constructor; file loading remains outside this
module. The output is an immutable in-memory bundle whose ordinary mapping
contains only visible synthetic rows and fictional clinical descendants. Its
private source frame and schema shape never appear in mappings, `repr`, reports,
or manifests.

The complete eight-resource package, augmented-resource derivation, prevalence
allocation, demographic calibration, disease-specific terminology, laboratory
and medication pathways, Synthea integration, and package-level counterfactual
worlds remain deferred. In particular, the current PPOC visits schema has no
length column. A projection fails closed with `ResourceProjectionUnavailable`
when a selected visit contains an observed `LENGTH` channel rather than
silently relabeling recumbent length as standing height. Callers can request a
resource-compatible frame by making length unavailable or selecting only
standing-height observations.

## Inputs

`project_observed_resources(frame, descriptor, demographics=None)` accepts:

1. a validated, completely fictional `ObservationFrame` from
   `synthetic.native.observations`;
2. an in-memory mapping with the current descriptor's `resources` list; and
3. optional strict `SyntheticDemographics` for the one synthetic patient.

The descriptor mapping is copied into an immutable shape containing only the six
base resources used by this evaluator bundle:

`patients`, `visits`, `labs`, `medications`, `problem_list`, and `referrals`.

Each resource must have a nonempty ordered `schema.fields` list with unique
field-name strings. Unknown descriptor metadata is ignored after shape
extraction; unknown resource names do not become output rows. Missing required
base resources, malformed field lists, duplicate names, or non-mapping inputs
fail closed. No path, file handle, reader, calibration artifact, report, seed,
or arbitrary column list is accepted by the projection API.

`SyntheticDemographics` is a frozen fictional-only value object containing the
frame patient ID, `sex` (`F`, `M`, or `U`), one descriptor-valid ethnicity, and
eight descriptor-valid race slots. If omitted, the projection uses `U` and
`Unknown` for all demographic values. These defaults are placeholders for row
shape, not a demographic distribution or calibration target.

## Immutable in-memory outputs

The module exposes the following frozen records:

- `ResourceSpec(name, field_names)`: one extracted resource name and ordered
  field tuple;
- `ResourceShape(resources)`: the six-resource shape and field-order lookup;
- `ResourceRow(resource_name, values)`: one ordered tuple of field/value pairs;
- `ClinicalDescendant(patient_id, visit_id, age_days, event_kind, code)`: a
  visible fictional recognition, workup, or diagnosis descendant linked to a
  selected synthetic visit; and
- `ObservedResourceBundle(patient_id, shape, rows, clinical_descendants,
  source_frame)`: visible base rows plus private evaluator references.

`ResourceRow.to_mapping()` and `ObservedResourceBundle.to_mapping()` preserve
the descriptor field order and use the package's empty-string missing-value
convention. The bundle mapping includes all six resource names, even when
ancillary resources are empty, and includes a separate visible
`clinical_descendants` list. It never includes `ObservationTruth`, latent
values, availability/error decisions, source events, hashes, stream identities,
descriptor paths, or hidden evaluator references. Custom `repr` methods expose
only evaluator/visible labels and not row payloads or private references.

## Projection rules

### Patients

One `patients` row is emitted. `patient_id`, `sex`, `ethnicity`, and
`race_1`–`race_8` are filled from `SyntheticDemographics`; every other declared
field is the schema missing value. No latent disorder kind, diagnosis label, or
trajectory state is written to a patient row.

### Visits and measurements

One `visits` row is emitted for each visible `ObservedVisit`, in increasing age
order. The row uses the visible synthetic patient/visit ID, age, the fictional
`Office Visit` encounter token, and `N` for the Epic-source flag. Observed
measurements map without resampling:

- `WEIGHT` kilograms to `weight_oz` with the fixed conversion `35.274`;
- `HEIGHT` centimeters to `height_in` with the fixed conversion `2.54`;
- `HEAD_CIRCUMFERENCE` centimeters to `head_circ_cm`; and
- derived `BMI` to `BMI`.

`MISSING` and `NOT_APPLICABLE` channels become empty-string fields. A visible
`LENGTH` observation is not representable in this exact base schema and causes a
`ResourceProjectionUnavailable` error. The projection never substitutes
length for height, fills a missing value from private truth, clips a value, or
independently samples BMI. Fictional event codes are placed in the first empty
`enc_diag_*` slots for their linked visit; all event codes come from the fixed
`RECORDED_EVENT_CODES` registry and are not asserted to be ICD, SNOMED, LOINC,
or clinical terminology.

### Clinical descendants and ancillary resources

Every visible recognition, workup, or diagnosis event becomes one
`ClinicalDescendant` linked to the exact visible visit determined by the
event's opportunity link. The descendant preserves its visible age and fixed
fictional code. The same code is copied into the linked visit's next available
`enc_diag_*` slot to keep the descriptor-shaped row and evaluator event view
consistent. More descendants than available diagnosis slots fail closed.

`labs`, `medications`, `problem_list`, and `referrals` are present as empty row
tuples in this slice. No disease-specific laboratory, medication, problem, or
referral pathway is implied by an empty resource. Their later contracts must
define causal timing, terminology, keys, missingness, and resource-level
counterfactual descendants before rows can be enabled.

## Validation contract

`validate_observed_resources(bundle)` returns an aggregate-only immutable report
with fixed `PASS`, `FAIL`, and `UNEVALUABLE` statuses. Its checks are:

1. `patient_identity`: one synthetic patient across all rows and descendants;
2. `schema_shape`: every row has exactly the extracted field order and all six
   base resources are present;
3. `visit_references`: unique synthetic visit IDs, increasing ages, and exact
   source-frame visit correspondence;
4. `measurements`: unit conversion, missingness, positivity, and BMI identity
   match the visible observation frame;
5. `clinical_descendants`: event code/kind, age, visit link, and one-to-one
   correspondence with visible frame events;
6. `ancillary_resources`: deferred resource rows remain empty; and
7. `evidence`: the private source frame exists and its observation validator
   does not report a failure.

Malformed or absent private source evidence is `UNEVALUABLE`. A typed visible
row, key, unit, event, or forbidden-resource violation is `FAIL`. Reports
contain only fixed check names, statuses, reason codes, and status counts. They
never contain patient IDs, ages, measurement values, row values, event payloads,
truth hashes, paths, or descriptor metadata.

## Determinism and safety

Projection performs no random draws. Replaying the same frame, descriptor
shape, and demographics yields byte-equivalent mappings. It consumes the
observation frame's already-determined synthetic IDs and recorded values and
does not resample latent physiology or measurement error. No new random stream
is introduced, so observation stream isolation remains unchanged.

The module imports only standard-library value helpers, the observation-frame
contract, and native trajectory model types needed for strict type checks. AST
boundary tests reject imports of calibration, calibration-input, held-out,
privacy-audit, CSV/package writers, and the smoke generator. Tests also assert
that no descriptor path, `Path`, `open`, `read_csv`, `datapackage.json`, or
visible resource file is touched by projection or validation.

## Supported and deferred behavior

This slice supports descriptor-shaped in-memory patients and visits,
observation-unit conversion, explicit missingness, fixed fictional event
descendants, deterministic synthetic IDs and visit links, and empty ancillary
resource placeholders. It does not implement length export, new diagnosis
terminology, labs, medications, problem-list rows, referrals, augmented
resources, exact-schema file export, package manifests, disorder prevalence,
demographic calibration, held-out validation, privacy/non-matchability
evidence, treatment/adherence resources, utilization counterfactuals,
measurement-error-removal counterfactuals, or Synthea.

## Acceptance criteria

The slice is complete when:

1. malformed descriptor shapes, demographics, rows, and bundles fail closed;
2. a compatible fictional observation frame projects deterministic patients and
   visits with the exact descriptor field order and units;
3. observed BMI remains derived and consistent, missingness is preserved, and
   unrepresentable length observations are rejected rather than relabeled;
4. recognition/workup/diagnosis descendants retain exact visible visit links,
   ages, ordering, and fixed fictional codes;
5. ancillary resources remain explicitly empty and no disease-specific clinical
   pathway is inferred;
6. aggregate validation reports only fixed statuses/reasons and never exposes
   hidden truth or descriptor paths;
7. no governed input, file I/O, package export, schema mutation, calibration,
   held-out, privacy, or CLI boundary is crossed; and
8. focused tests, the full suite, Ruff, schema validation, diff checks, and a
   broad review pass before merge.

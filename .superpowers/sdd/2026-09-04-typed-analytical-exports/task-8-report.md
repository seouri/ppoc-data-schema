# Task 8 report: complete verification and final implementation audit

Date: 2026-09-04
Worktree: `/Users/joon/src/tries/ppoc-data-schema/.worktrees/typed-analytical-exports`
Branch: `codex/typed-analytical-exports`
Spec authority: `docs/superpowers/specs/2026-09-04-typed-analytical-exports-design.md`
Review range: `f982487...HEAD`

## Status

A subsequent single final-review fix wave addressed all five Important findings
from the whole-branch review. The coordinated test-first correction is recorded
in the final addendum below; it preserves the approved public interfaces and
artifact semantics. The original Task 8 audit follows for historical evidence.

Task 8 verification and audit completed. Four substantive contract defects were found and fixed test-first:

1. Successful exports left the ISO-8859-1 labs transcode in the process-global system temporary directory until process exit. Both exporters now place the temporary transcode inside private staging and remove it immediately after DuckDB consumes it; crash residue therefore stays inside the explicit staging/recovery boundary.
2. Parquet bundle verification accepted a reordered manifest `outputs` array. Verification now requires descriptor output order.
3. Descriptor parsing accepted duplicate resource CSV paths. It now rejects them before source preflight/staging.
4. Descriptor parsing accepted a logical relationship without its required `orphanRows`. It now fails closed.

The fix is commit `e3f9f94` (`fix: harden analytical export boundary`) and modifies only:

- `scripts/typed_export.py`
- `tests/test_export_parquet.py`
- `tests/test_typed_export.py`

The focused exporter gate, dedicated two-destination smoke, schema check, diff check, and Ruff over all changed Python files pass. The complete repository suite and repository-wide Ruff command remain nonzero because of the same unrelated failures present before analytical-export implementation; they are recorded separately below and are not described as passing.

## Test-first defect evidence

### Restricted transcode lifecycle

Initial focused regression:

```text
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_export_parquet.py::test_export_parquet_bundle_leaves_no_transcoded_source_in_system_temp
F                                                                        [100%]
FAILED tests/test_export_parquet.py::test_export_parquet_bundle_leaves_no_transcoded_source_in_system_temp
1 failed in 0.47s
```

The failure showed one residual `system-temp/tmp...` file. The regression was then parameterized across both exporters. With the DuckDB correction intentionally absent, the result was:

```text
.F                                                                       [100%]
FAILED tests/test_export_parquet.py::test_export_bundle_leaves_no_transcoded_source_in_system_temp[export_duckdb_bundle-duckdb]
1 failed, 1 passed in 1.03s
```

After the shared lifecycle correction:

```text
..                                                                       [100%]
2 passed in 1.23s
```

### Manifest output order

Before the verifier correction:

```text
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_export_parquet.py::test_verify_parquet_bundle_rejects_reordered_manifest_outputs
F                                                                        [100%]
FAILED tests/test_export_parquet.py::test_verify_parquet_bundle_rejects_reordered_manifest_outputs
1 failed in 0.28s
```

The expected `LifecycleError` was not raised. After the correction, this regression plus both transcode cases produced:

```text
...                                                                      [100%]
3 passed in 1.09s
```

### Descriptor fail-closed rules

Before parser correction, the malformed-contract table showed exactly the two new failures:

```text
.F.........F.                                                            [100%]
FAILED tests/test_typed_export.py::test_load_package_contract_rejects_malformed_contract[<lambda>-duplicate resource path]
FAILED tests/test_typed_export.py::test_load_package_contract_rejects_malformed_contract[<lambda>-logical relationship count1]
2 failed, 11 passed in 0.19s
```

After correction:

```text
.............                                                            [100%]
13 passed in 0.14s
```

## Required verification commands

### Focused exporter suite

Pre-fix baseline:

```text
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_typed_export.py tests/test_export_parquet.py tests/test_build_duckdb.py tests/test_analytical_export_cli.py
........................................................................ [ 65%]
......................................                                   [100%]
110 passed in 14.18s
```

Final corrected tree:

```text
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_typed_export.py tests/test_export_parquet.py tests/test_build_duckdb.py tests/test_analytical_export_cli.py
........................................................................ [ 62%]
...........................................                              [100%]
115 passed in 14.57s
```

Exit status: 0. No core-behavior skips.

### Complete repository suite

Pre-fix baseline completed; it was not interrupted:

```text
7 failed, 3448 passed, 8 skipped in 240.60s (0:04:00)
```

Final corrected tree completed; it was not interrupted:

```text
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q
7 failed, 3453 passed, 8 skipped in 238.79s (0:03:58)
```

Exit status: 1. Exact failures:

```text
tests/synthetic/test_celiac_ancillary_docs.py::test_readme_links_the_celiac_slice_without_copying_the_guide
tests/synthetic/test_excess_weight_ancillary_docs.py::test_readme_links_the_guide_and_marks_the_pathway_as_a_roadmap_slice
tests/synthetic/test_pediatric_hypothyroidism_ancillary_docs.py::test_guide_preserves_deferred_boundaries_and_readme_links_the_slice
tests/synthetic/test_sga_ancillary_docs.py::test_readme_links_the_sga_roadmap_slice_without_copying_the_guide
tests/synthetic/test_synthea_overlay.py::test_overlay_is_self_contained_and_has_a_stable_digest
tests/synthetic/test_turner_ancillary_docs.py::test_readme_links_the_turner_roadmap_slice_without_copying_the_guide
tests/synthetic/test_undernutrition_ancillary_docs.py::test_readme_links_the_undernutrition_slice_without_copying_the_guide
```

The first, second, and fourth failures expect the missing README sentence `excess-weight ancillary pathway is a separate roadmap slice`. The hypothyroidism, Turner, and undernutrition failures expect missing roadmap links. The overlay test expected SHA-256 `074efc0db22d19a71c872012756d0a7dd86e1336f267357694e3222de56ef85e` and observed `0b7ba5505213a7b7f7cdc05c233f5256ce893dca1f48a7183c948e95f8cb27b0`.

The eight skips were seven opt-in synthetic development-scale/CLI-composition checks requiring `SYNTHETIC_RUN_SCALE=1` and one external Synthea smoke requiring `SYNTHEA_CHECKOUT`.

These failures are unrelated and pre-existing:

- `.superpowers/.../progress.md` records the implementation baseline as `3338 passed, 8 skipped, 7 pre-existing failures`, identifying the same README roadmap-link/overlay-digest checks.
- All seven failing test files and `scripts/synthea/overlay` are byte-unchanged in `f982487...HEAD`.
- The analytical-export README diff only adds exporter inventory, governance, commands, and operator-guide text; the missing synthetic roadmap text was already absent at `f982487`.

### Repository-wide Ruff

Final command:

```text
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check src scripts tests
Found 10 errors.
[*] 4 fixable with the `--fix` option (4 hidden fixes can be enabled with the `--unsafe-fixes` option).
```

Exit status: 1. Exact diagnostics:

```text
scripts/augment.py:57:1       I001  import block is unsorted or unformatted
scripts/augment.py:62:1       UP035 typing.Dict is deprecated
scripts/augment.py:136:37     UP006 use dict instead of Dict
scripts/augment.py:576:9      F841  ref_col_max assigned but unused
scripts/augment.py:653:5      SIM114 combine equivalent branches
scripts/augment.py:1397:12    PIE810 call startswith once with a tuple
scripts/augment.py:1610:18    DTZ005 datetime.now called without tz
scripts/harrall_outliers.py:1:1  I001 import block is unsorted or unformatted
scripts/harrall_outliers.py:90:5 F841 prev_measure assigned but unused
scripts/harrall_outliers.py:92:5 F841 prev_age assigned but unused
```

Both Ruff-failing files are byte-unchanged in `f982487...HEAD`. Ruff over every changed Python implementation/test file passed exactly:

```text
All checks passed!
```

### Schema freshness

```text
python3 schema/build.py --check
validated 8 resources in datapackage.json
```

Exit status: 0.

### Diff check

```text
git diff --check
```

Exit status: 0. No stdout/stderr.

### Dedicated two-destination synthetic CLI smoke

Pre-fix:

```text
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_analytical_export_cli.py::test_two_destination_cli_smoke
.                                                                        [100%]
1 passed in 2.47s
```

Final corrected tree:

```text
.                                                                        [100%]
1 passed in 2.48s
```

Exit status: 0. The test invokes each CLI at two fresh destinations; checks each manifest against its own bytes; compares source hashes, typed schemas, row counts, rows, validation results, and relationships; and does not require binary DuckDB hash equality.

## Spec-to-diff, privacy, and scope audit

| Criterion | Evidence and result |
| --- | --- |
| Exact file inventories | Parquet tests verify eight ordered `.parquet` files plus `source-datapackage.json` and `manifest.json`; DuckDB tests verify only `ppoc.duckdb` and `manifest.json`. Manifest verification now rejects reordered Parquet output entries. Pass. |
| Source immutability | All eight sources are preflighted before staging, hashed from original bytes, and stat-checked after conversion/validation. Mutation tests prevent promotion. Pass. |
| Output guards | Tests reject checkout paths, input/ancestor paths, symlinks, special files, missing/unapproved parents, collisions, and stale recovery siblings. Pass. |
| Permissions | Staging/bundle directories are explicitly `0700`; generated files are explicitly `0600`; invariant checks run before and after verifier callbacks. Pass. |
| Type mapping and missingness | Shared projection maps string/integer/number to `VARCHAR`/`BIGINT`/`DOUBLE`, preserves order, maps empty to null, enforces integer lexical/range rules and finite doubles, and does not infer/repair. Pass. |
| Labs decoding | Synthetic C1-byte regression verifies literal ISO-8859-1 decoding. The temporary UTF-8 projection is now private staging state and is removed immediately after consumption. Pass after Task 8 fix. |
| Aggregate validations | Focused tests cover row counts, requiredness, enums, numeric ranges, PK completeness/uniqueness, strict FK anti-joins, logical null/orphan counts, and exact schemas. Pass. |
| DuckDB physical boundary | Read-only verification checks exact eight `main` tables, exact four `ppoc_meta` tables, exact schemas and CHECK/NOT NULL constraints, no physical PK/FK, no indexes, views, sequences, or macros. Pass. |
| Metadata tables | Tests and fresh read-only revalidation verify complete `build`, `resources`, `descriptor`, and `validations` content and exact constraints. Pass. |
| Manifest redaction/provenance | Canonical JSON, exact keys/inventory/order, per-artifact hashes, source basenames/hashes/counts, output hashes/schemas/counts, module/Git/tool provenance, and no absolute paths are covered. Pass after Task 8 order fix. |
| Replacement restoration | Tests cover recognized-bundle replacement, post-backup restoration, post-promotion verification failure, mode rechecks, and fixed redacted callback errors. Pass. |
| Documentation | Root and schema READMEs contain copy-ready commands, canonical CSV/Frictionless authority, restricted-derivative governance, layouts, provenance, replacement/recovery, and read-only examples. Pass. |
| No real-data fixture/path | All hard-coded test identifier values are `SYN-*`; no user-specific `/Users/...` or `/home/...` path occurs in changed files. Tests clear or explicitly set `PPOC_DATA_ROOT` to pytest temporary directories. Pass. |
| No raw exception/SQL disclosure | No SQL logging exists. `str(error)` is used only inside the private conversion-token whitelist; CLI `print(str(error))` receives the redacted `ExportError` hierarchy. Pass. |
| No generated analytical files in Git | `git ls-files '*.parquet' '*.duckdb'` returned no paths. Final status has no generated or untracked artifacts. Pass. |

Changed-file privacy searches produced:

```text
user-specific absolute paths: no matches
tracked *.parquet/*.duckdb: no matches
PPOC_DATA_ROOT in changed tests: only explicit empty/temp-directory controls in tests/test_analytical_export_cli.py
hard-coded patient_id values: only SYN-P001, SYN-P002, and SYN-ORPHAN
```

## Governed real-data verification

Not run. No explicitly approved secure output root was supplied. In accordance with the brief, no destination was inferred and neither `/tmp` nor the repository was used for real-data output. The automated synthetic gate remains the implementation evidence.

## Final Git scope

After restoring tracked bytecode changed by pytest and removing the six untracked bytecode files created by this verification run:

```text
git status --short --branch
## codex/typed-analytical-exports
```

`git diff f982487...HEAD --name-status`:

```text
A .superpowers/sdd/2026-09-04-typed-analytical-exports/task-1-report.md
A .superpowers/sdd/2026-09-04-typed-analytical-exports/task-2-report.md
M README.md
A docs/superpowers/plans/2026-09-04-typed-analytical-exports.md
M schema/README.md
A scripts/build_duckdb.py
A scripts/export_parquet.py
A scripts/typed_export.py
A tests/analytical_export_fixtures.py
A tests/test_analytical_export_cli.py
A tests/test_build_duckdb.py
A tests/test_export_parquet.py
A tests/test_typed_export.py
```

This is limited to analytical-export scripts, tests, operator/repository documentation, and SDD documentation. There are no generated analytical artifacts or unrelated user files.

`git log --oneline f982487..HEAD`:

```text
e3f9f94 fix: harden analytical export boundary
b1e393a docs: add typed analytical export workflows
14e9f98 fix: verify all DuckDB metadata constraints
aab48fd fix: verify typed DuckDB bundle metadata
f037b93 feat: build typed PPOC DuckDB
dfe6731 feat: export typed Parquet resources
dd6f839 fix: close bundle promotion verification gap
4ca9fac fix: harden analytical bundle verification
a598f60 feat: add secure analytical bundle lifecycle
d80cde1 feat: validate analytical export artifacts
295d9bd fix: enforce typed export source row counts
1c72040 feat: add typed CSV ingestion
ffbbc56 fix: harden analytical export descriptor contract
1e55fb5 feat: define analytical export contracts
8518cf5 docs: plan typed analytical exports
```

## Interruptions and operational notes

- No verification command hung, timed out, or was manually interrupted. Both full-suite runs completed in approximately four minutes.
- The first `git add` and first `git restore --worktree` attempts failed immediately with the exact sandbox message `fatal: Unable to create '/Users/joon/src/tries/ppoc-data-schema/.git/worktrees/typed-analytical-exports/index.lock': Operation not permitted`. Each was rerun with linked-worktree Git-index permission and then succeeded. These were bounded Git operations, not test interruptions.
- No real-data command was attempted.

## Remaining concerns

The branch is clean and the analytical-export scope is green, but the repository as a whole is not green: the complete suite still has seven documented pre-existing synthetic failures, and repository-wide Ruff still has ten documented pre-existing findings. Therefore the full suite and full Ruff command are explicitly reported as failing, not passing.

## Final smoke-audit addendum

The final source audit found that the Task 7 two-destination smoke compared source hashes, manifest summaries, schemas, row counts, and typed rows, but did not itself reopen both destinations to check each manifest against its own output bytes or compare physical constraints and aggregate relationship records. `tests/test_analytical_export_cli.py` was intentionally strengthened and committed as `7e9b4ab` (`test: complete analytical export smoke audit`). It now:

- independently runs `verify_parquet_bundle` or `verify_duckdb_bundle` on both fresh destinations;
- verifies every manifest output size and SHA-256 against that destination's artifact bytes;
- reruns aggregate validation against each Parquet/DuckDB destination and compares complete validation records, including strict and logical relationship results;
- compares exact DuckDB physical constraint rows across destinations; and
- continues to compare typed schemas, row counts, rows, and source fingerprints without requiring binary DuckDB hash equality.

Covering evidence on the final smoke-test source:

```text
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_analytical_export_cli.py::test_two_destination_cli_smoke
.                                                                        [100%]
1 passed in 2.92s

UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q tests/test_typed_export.py tests/test_export_parquet.py tests/test_build_duckdb.py tests/test_analytical_export_cli.py
........................................................................ [ 62%]
...........................................                              [100%]
115 passed in 15.85s

UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run ruff check tests/test_analytical_export_cli.py
All checks passed!
```

A subsequent full-suite rerun on this test-only change was stopped on the user's explicit finalization instruction. It was interrupted with exit status 130 and must not be treated as passing:

```text
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! KeyboardInterrupt !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
3 failed, 2309 passed, 7 skipped in 195.55s (0:03:15)
```

The three failures observed before interruption were members of the already documented pre-existing README roadmap-link set. The earlier complete post-fix full-suite result remains `7 failed, 3453 passed, 8 skipped in 238.79s`; no completed full-suite pass is claimed.

## Single final-review fix wave addendum

### Status and scope

All five Important whole-branch findings were fixed in one coordinated wave
under the commit subject `fix: complete typed export final review`. The wave
changes only:

- `scripts/typed_export.py`
- `tests/test_typed_export.py`
- `tests/test_build_duckdb.py`
- this Task 8 report

No real-data export was run, no generated Parquet or DuckDB artifact was added,
and the eight-resource descriptor/type/validation/manifest contracts were not
broadened.

### Test-first evidence

The first regression run was intentionally red:

```text
UV_CACHE_DIR=/tmp/ppoc-uv-cache uv run pytest -q \
  tests/test_typed_export.py tests/test_build_duckdb.py \
  -k 'final_review or malformed_contract'
19 failed, 14 passed, 78 deselected in 4.13s
```

Those failures independently reproduced whole-file labs decoding, duplicate
CSV parsing during fingerprinting, implicit missing-value defaults,
cross-platform unsafe paths, duplicate JSON keys, late replacement-target
validation, raw setup exceptions, cleanup-before-close behavior, and hidden
user objects in non-approved DuckDB schemas.

After the initial implementation, the regression set was green:

```text
33 passed, 78 deselected in 3.37s
```

Cleanup ordering was then tightened to cover a DuckDB `execute` failure after
query construction. Before the correction, both format cases failed because
transcode cleanup ran while the connection was still open:

```text
FF                                                                       [100%]
2 failed in 0.27s
```

After moving all failure cleanup behind connection closure:

```text
..                                                                       [100%]
2 passed in 0.17s
```

### Corrections

1. Labs transcoding now reads bounded 1 MiB chunks and writes a mode-`0600`
   UTF-8 projection inside the export's private staging directory. ISO-8859-1
   byte-to-code-point semantics remain literal, sources are never opened for
   writing, and failed partial transcodes are removed.
2. Exact preflight still parses and counts every source before staging.
   Fingerprinting now performs only the required streaming hash pass and reuses
   the row/field counts already proven by preflight, eliminating its duplicate
   CSV parse without weakening row/count/hash guarantees.
3. Descriptor loading rejects duplicate JSON keys, missing or non-`[""]`
   `schema.missingValues`, and POSIX or Windows absolute/traversal paths using
   host-independent path semantics. Public messages remain redacted.
4. `BundleRun.start(output, artifact_type, replace)` keeps its exact
   context-free signature and verifies an existing replacement target before
   creating staging. Promotion still revalidates the target and preserves the
   existing rollback path.
5. Both stable library exporters now place parsing, preflight, safety,
   fingerprinting, provenance, staging setup, conversion, and promotion inside
   the redaction boundary. On failures, DuckDB closes before transcode, spill,
   or staging cleanup; close/cleanup failures use redacted lifecycle categories.
6. Read-only DuckDB verification compares all non-internal tables with the
   exact approved inventory, rejects extra user schemas, and rejects
   user-created indexes, views, sequences, macros, and physical PK/FK
   constraints globally while allowing internal DuckDB catalog objects.

### Final verification

Focused exporter suite:

```text
135 passed in 17.77s
```

Dedicated two-destination CLI smoke:

```text
1 passed in 3.02s
```

Changed-file Ruff:

```text
All checks passed!
```

Schema freshness:

```text
validated 8 resources in datapackage.json
```

`git diff --check` exited 0 with no output.

The complete repository suite was also allowed to finish:

```text
7 failed, 3473 passed, 8 skipped in 246.55s (0:04:06)
```

The seven failures are the same pre-existing synthetic README roadmap-link and
Synthea-overlay digest failures listed earlier in this report. No failing test
is in the analytical-export suite, and those unrelated files were not changed
by this wave. Repository-wide Ruff was not rerun; its ten previously documented
findings remain outside this fix scope, while Ruff over every changed Python
file passed.

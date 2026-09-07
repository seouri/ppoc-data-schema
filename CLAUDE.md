# Working in this repository

## Check your work locally before calling it done

There is no CI, by choice. `reports/audit.sh` is the gate and it runs on your
machine:

```sh
./reports/audit.sh            # eleven steps, about six minutes
./reports/audit.sh --quick    # the same minus the full test suite, about two
```

It exits non-zero if any step fails and prints that step's captured output, so
the failure is diagnosable from the run itself. Run it before reporting work
complete, and after any change under `reports/`, `src/`, `schema/`, or the
documents it checks.

Steps 1 to 3 rebuild the exploratory report and need the restricted DuckDB
bundle. They skip with a notice when it is absent, so the other eight still
run; point `PPOC_DUCKDB` at the bundle if it is not at the default path.

`AUDIT_RUNS` sets how many independent rebuilds step 1 compares against the
committed content. It defaults to 2. Raise it after adding probes that
introduce new aggregates: DuckDB sums in parallel, and that has produced drift
which appeared in roughly one build in six.

## Things that will bite you

- **`reports/ppoc-eda/` is generated.** Never edit its four outputs by hand.
  Change a probe under `reports/ppoc_eda/` and rebuild with
  `reports/build_ppoc_eda.py`, which rewrites them only when the findings
  change.
- **Numbers live in `findings.json`, not in prose.** A probe supplies values and
  a template; there is no code path that writes a literal figure into a
  sentence. Keep it that way.
- **`scripts/augment.py` and `scripts/harrall_outliers.py` are vendored
  byte-identical** and pinned by SHA-256 in `data/augment-runtime-manifest.json`.
  Any edit, down to a trailing comment, fails `tests/test_augment_import.py`.
  Their lint findings are exempted in `pyproject.toml` for the same reason.
- **Inode numbers are recycled on Linux and not on macOS.** The quarantine
  cleanup in `src/synthetic/native/counterfactual.py` identifies a file by
  `(st_dev, st_ino)`, so a test that unlinks a file and then creates its
  "replacement" gets the freed inode back on ext4 and tmpfs, and the replacement
  is indistinguishable from the owner. Allocate the replacement *before* freeing
  the owner; `tests/synthetic/test_counterfactual_manifest.py` does this and
  asserts the two identities differ.

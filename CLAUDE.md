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
- **The shortcut audit is coupled to 5.10's definitions.**
  `reports/ppoc_eda/probes/shortcuts.py` carries two sections: 5.13, a lift
  screen over every value of seven categorical fields, and 5.14, a rank screen
  over every numeric column of the augmented patient layer and eleven
  constructed features. It imports `WORKUP_INDEX` from `joint.py`, so changing
  what 5.10 counts as the first growth workup rewrites both sections silently.
  `INDEX_TERMS` in the same file withholds a workup lift from the values that
  *are* that index; edit the two together, or a row reports the maximum the base
  rate allows as though it had measured something. Both screens add the kind of
  aggregate the drift note above is about — a group mean per value of a field,
  and rank sums — so raise `AUDIT_RUNS` when you touch them.
- **Inode numbers are recycled on Linux and not on macOS.** The quarantine
  cleanup in `src/synthetic/native/counterfactual.py` identifies a file by
  `(st_dev, st_ino)`, so a test that unlinks a file and then creates its
  "replacement" gets the freed inode back on ext4 and tmpfs, and the replacement
  is indistinguishable from the owner. Allocate the replacement *before* freeing
  the owner; `tests/synthetic/test_counterfactual_manifest.py` does this and
  asserts the two identities differ. For the same reason that identity is only
  meaningful while something holds the inode open, cleanup refuses an identity
  passed without its still-open `owner_descriptor`. Do not add a caller that
  supplies one without the other, and note that a failing `close` still releases
  the descriptor, so pin the inode with `os.dup` before closing. The descriptor
  is necessary but not sufficient: one that yields no usable identity still
  falls through to the fail-closed branch, which quarantines the name whatever
  it now holds.

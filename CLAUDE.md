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
- **A prose-only change needs `--force`.** `findings.json` carries values,
  tables and figures, not paragraphs, so editing a sentence in a probe leaves
  the comparison in `build.py` equal and the build reports "findings unchanged"
  while the committed HTML, markdown and PDF keep the old sentence. Rebuild
  with `reports/build_ppoc_eda.py --force` after any wording change. Step 3 of
  the audit catches the omission, because it force-rebuilds and compares bytes
  against what is committed.
- **Numbers live in `findings.json`, not in prose.** A probe supplies values and
  a template. Only part of that is enforced:
  `test_no_probe_writes_a_measured_figure_into_prose` scans the probes for a
  decimal percentage, which is the detectable form, and has caught two real
  literals in one review pass — including one inside a code comment, so reword
  the comment rather than loosening the test; its docstring records an earlier
  one in 5.11. An integer literal passes, so 8.1 describes the rest as
  convention and so should you.
  A count written into a sentence is the case that keeps going wrong, because
  the structure holding the answer is usually right there. Three of them
  disagreed with the table immediately beneath: 1.2 said three resources are
  keyed off the patient and visit axes when `GRAIN` holds four, 1.5 listed seven
  foreclosed checks against Part 2's nine, and 0.1 was titled "Three ways in"
  over five `ENTRY_POINTS`. Derive the number from the structure. Where you
  cannot — a section title is not templated — drop the count instead of writing
  it down.
- **A correction in one section goes stale in another, and almost nothing
  catches it.** This is the dominant failure mode in the report's history.
  Every one of these happened: correcting the labs key in 3.1 left 3.6 advising
  a join on a superkey; restricting 3.9 to ICD-10-shaped codes left 5.1 quoting
  the old category pair from its own independent computation; separating rows
  from resulted components in 5.2 left 1.2 describing a grain that is wrong for
  13% of lab rows; changing 4.10's intraclass correlation left the
  hand-maintained overlay quoting the old value; and rewriting 4.8 left the
  overlay quoting a figure that survived only in the Part 7 catalogue row,
  whose artifact scale rounds to two decimals.
  Only some of that is guarded. `audit_coverage.py` checks each figure the
  overlay, README and `docs/data_description.md` quote **inside the section that
  cites it** — it used to search the whole report, which let a citation go stale
  where it was made and pass because another section printed the same number.
  Its completeness sentinels fire on reworded prose, not just deletion, so three
  have been repointed at durable anchors (an artifact name, a rule name, a
  claim) and the remaining fragment-style ones will keep firing on legitimate
  rewrites. Where two sections genuinely share a definition, import it rather
  than recomputing it: `PANEL_SPLIT_YEARS`, `WORKUP_INDEX`, `ICD_SHAPE` and
  `DEIDENT_CHECKS` all exist for that reason, and the last one raises if Part 2
  marks a check 1.5 does not list.
  Nothing guards an advice sentence, a grain statement, or any prose in one
  section that rests on another's measurement. After changing what a section
  measures or concludes, `grep -n "<section number>" reports/ppoc-eda/ppoc-eda.md`
  for its inbound references and read them.
- **`ctx.suppress` is not automatic.** The floor of
  `SUPPRESS_BELOW` records per cell is one shared helper, not a property of the
  renderer: a probe that reports a raw count gets no suppression at all. 5.5's
  identity tables did exactly that and published a category backed by six
  patients, in a report that states the rule in both 0.1 and 8.1. Route every
  count through `ctx.suppress`, and keep the row when the category existing is
  itself informative — 3.7 and 5.5 both do, showing the label with an em dash
  for the number.
- **`scripts/augment.py` and `scripts/harrall_outliers.py` are vendored
  byte-identical** and pinned by SHA-256 in `data/augment-runtime-manifest.json`.
  Any edit, down to a trailing comment, fails `tests/test_augment_import.py`.
  Their lint findings are exempted in `pyproject.toml` for the same reason.
- **5.7 and 5.8 share one definition of the tracked growth panel.**
  Neither the extract nor its manifest writes that panel down; it is recoverable
  only from the `dx_age_years_*` column names of `patients_augmented`, and
  `tracked_codes` in `reports/ppoc_eda/probes/growth.py` is the single place
  that reads them. The trailing underscore is load-bearing: drop it and bare
  `dx_age_years`, the panel-wide age at first diagnosis, joins the panel as an
  ICD-10 code named after its own column. 5.8 also reverse-engineered what
  those columns measure — the earliest age at which the code *or any
  descendant* appears on either diagnosis resource, at 365.25 days to the year,
  rounded to three decimals — and its prose says so, so a change upstream to
  how the age is derived makes that paragraph wrong rather than merely stale.
  Its four statistics per code are the aggregates the drift note above is
  about; raise `AUDIT_RUNS` when you touch them.
- **One constant splits two sections.** `PANEL_SPLIT_YEARS` in
  `growth.py` is 5.8's cutoff between codes recorded at the birth episode
  and codes recorded later, and `joint.py` imports it to stratify 5.9's
  labelled cohort by each patient's own diagnosis age. Changing the number
  therefore rewrites both sections, including 5.9's three-row utilization
  table and every share in its two panels. It is justified in 5.8's prose
  from the WHO/CDC reference boundary and the age-2 BMI floor of 1.3, so a
  new value needs that paragraph rewritten too, not just the constant.
- **The shortcut audit is coupled to 5.11's definitions.**
  `reports/ppoc_eda/probes/shortcuts.py` carries two sections: 5.14, a lift
  screen over every value of seven categorical fields, and 5.15, a rank screen
  over every numeric column of the augmented patient layer and eleven
  constructed features. It imports `WORKUP_INDEX` from `joint.py`, so changing
  what 5.11 counts as the first growth workup rewrites both sections silently.
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

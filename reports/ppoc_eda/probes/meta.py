"""Part 0 and Part 8 — how to read the report, and how it was made."""

from __future__ import annotations

from ..context import COHORT_AS_OF, EXTRACT_DATE, SUPPRESS_BELOW, Context
from ..findings import Column, Finding, Para, Table, probe

ENTRY_POINTS = [
    ("New to this extract", ("Read Part 1, then the not-applicable table in Part 2. "
                            "Twenty minutes, and it will save days.")),
    ("About to use a specific field", ("Find it in the Part 6 field index, then "
                                      "follow the finding it links to.")),
    ("Explaining a number that looks wrong", ("Check the Part 7 artifact catalogue "
                                             "before assuming a bug in your code.")),
    ("Planning a study", ("Part 1.4 first. The cohort selection invalidates several "
                         "whole classes of question, and it is not visible in any field.")),
]


@probe("meta.howto", "0.1")
def howto(ctx: Context) -> list[Finding]:
    f = Finding(
        id="meta.howto", part="0.1", title="Three ways in",
        values={"snapshot": ctx.snapshot, "cohort_as_of": COHORT_AS_OF,
                "extract_date": EXTRACT_DATE},
    )
    f.blocks = [
        Para("This report describes one snapshot of one pediatric primary-care EHR "
             "extract. It belongs to no project: it states what the data are, what "
             "they support, and what they cannot answer, and it leaves the research "
             "question to you."),
        Table("t-entry", "Where to start",
              [Column("if you are", "if you are"), Column("start", "start here")],
              [{"if you are": a, "start": b} for a, b in ENTRY_POINTS]),
        Para("Every number here was measured from the delivered bundle for snapshot "
             "`{snapshot}`; none is copied from another document without being "
             "recomputed. The cohort is pinned to {cohort_as_of} and the extract was "
             "cut on {extract_date}."),
        Para("**What this report is not.** It is not a clinical validation, not a "
             "registered analysis, and not a statement about any individual child. "
             "Every figure is an aggregate, and any cell resting on fewer than "
             "records is suppressed.", role="warning"),
    ]
    # The suppression threshold is a number, so it goes through values like any other.
    f.values["suppress"] = SUPPRESS_BELOW
    f.blocks[-1] = Para(
        "**What this report is not.** It is not a clinical validation, not a "
        "registered analysis, and not a statement about any individual child. Every "
        "figure is an aggregate, and any cell resting on fewer than {suppress} "
        "records is suppressed.", role="warning")
    return [f]


@probe("meta.methods", "8.1")
def methods(ctx: Context) -> list[Finding]:
    f = Finding(
        id="meta.methods", part="8.1", title="Methods, determinism, and limitations",
        values={"snapshot": ctx.snapshot, "digest": ctx.digest,
                "package": ctx.package.get("name", "unknown"),
                "version": ctx.package.get("version", "unknown"),
                "suppress": SUPPRESS_BELOW},
    )
    f.blocks = [
        Para("**Computation.** Every figure was computed with DuckDB against the "
             "typed bundle of `{package}` {version}, snapshot `{snapshot}`, sha256 "
             "`{digest}`, opened read-only. The bundle is never copied into this "
             "repository and no row-level identifier is read into any output."),
        Para("**Privacy.** Output is aggregate only. Cells backed by fewer than "
             "{suppress} records are suppressed centrally rather than probe by "
             "probe, so a new probe inherits the rule without having to remember it."),
        Para("**Reproducibility.** The generator computes the finding set once and "
             "renders every output from it, so the HTML, the PDF, the Markdown "
             "mirror, and `findings.json` cannot disagree. Prose carries templates "
             "rather than literals: a number reaches an output only by way of the "
             "finding that measured it. Outputs are rewritten only when the finding "
             "set changes, so rebuilding an unchanged snapshot leaves the committed "
             "files untouched."),
        Para("**Limitations.** Everything here is specific to this snapshot and "
             "would need recomputing for another extract. The report describes "
             "recording and derivation behaviour, not clinical truth: a value being "
             "implausible does not establish what the child actually measured, and a "
             "value being plausible does not establish that it was measured at all. "
             "Where a mechanism is inferred rather than observed the report says so "
             "and shows the evidence.", role="method"),
    ]
    return [f]

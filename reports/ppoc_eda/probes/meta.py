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
    ("Building features or a model", ("5.9 for whether the label can be predicted at "
                                     "all, then the shortcut screens in 5.14 and 5.15 "
                                     "before you fix a feature set.")),
]


@probe("meta.howto", "0.1")
def howto(ctx: Context) -> list[Finding]:
    f = Finding(
        id="meta.howto", part="0.1", title="Ways in",
        values={"snapshot": ctx.snapshot, "cohort_as_of": COHORT_AS_OF,
                "extract_date": EXTRACT_DATE},
    )
    f.blocks = [
        Para("This report describes one snapshot of one pediatric primary-care EHR "
             "extract. Through 5.8 it belongs to no project: it states what the "
             "data are, what they support, and what they cannot answer, and it "
             "leaves the research question to you. From 5.9 it stops being neutral "
             "on purpose. The extract was assembled upstream around one question — "
             "identifying abnormal growth early — and those sections work that "
             "question through, because the label it implies is already shipped in "
             "the data as `growth_dx_flag` and its shortcuts are not visible from a "
             "field-by-field description. Read them as a worked example of auditing "
             "a label, not as the report choosing your outcome."),
        Table("t-entry", "Where to start",
              [Column("if you are", "if you are"), Column("start", "start here")],
              [{"if you are": a, "start": b} for a, b in ENTRY_POINTS]),
        Para("Every number here that can be measured was measured, from the "
             "delivered bundle for snapshot `{snapshot}`. Where a delivery document "
             "also states a figure it is treated as a target rather than a source: "
             "1.1 reconciles every row count and patient count against both the "
             "bundle manifest and the PPOC documents before anything else is "
             "computed. Two sets of figures cannot be measured at all and are "
             "reported as the documents give them — 1.4's exclusion funnel and its "
             "rarity vocabularies, because the patients and codes they count are "
             "the ones the extract does not contain. Those are the only numbers in "
             "this report that rest on a document. The cohort date and the extract "
             "cut are stated once, in 1.4, and referenced from everywhere else that "
             "needs them."),
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
        "figure is an aggregate, and no cell may rest on fewer than {suppress} "
        "records — a floor held by a shared helper and by review rather than by "
        "construction, as 8.1 explains.", role="warning")
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
        Para("**Privacy.** Output is aggregate only, and no cell may rest on fewer "
             "than {suppress} records. The rule lives in one shared helper rather "
             "than in a comparison repeated through every probe, but it is a helper "
             "a probe has to call: a probe that reports a raw count does not inherit "
             "the rule, and "
             "one had to be corrected during review for exactly that — 5.5's "
             "identity tables printed a category backed by six patients. Treat the "
             "floor as enforced by that helper and by reading, not by construction."),
        Para("**Reproducibility.** The generator computes the finding set once and "
             "renders every output from it, so the HTML, the PDF, the Markdown "
             "mirror, and `findings.json` cannot disagree. Prose carries templates "
             "rather than literals, so a number reaches an output by way of the "
             "finding that measured it; a test enforces that for decimal "
             "percentages, which is the detectable form, and the rest is "
             "convention. Outputs are rewritten only when the finding set changes, "
             "so rebuilding an unchanged snapshot leaves the committed files "
             "untouched."),
        Para("**Limitations.** Everything here is specific to this snapshot and "
             "would need recomputing for another extract. The report describes "
             "recording and derivation behaviour, not clinical truth: a value being "
             "implausible does not establish what the child actually measured, and a "
             "value being plausible does not establish that it was measured at all. "
             "Where a mechanism is inferred rather than observed the report says so "
             "and shows the evidence.", role="method"),
    ]
    return [f]

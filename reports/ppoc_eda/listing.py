"""One rule for how much of a vocabulary a table shows.

Short vocabularies are listed in full, because a complete inventory answers
questions a top-N cannot: whether a category you expect exists at all, and what
the long tail is made of. Long ones are truncated, and say so — a silent cap
reads as "this is everything" when it is not.
"""

from __future__ import annotations

from .context import Context

#: A Letter page at the print stylesheet's font size holds roughly this many
#: table rows. Vocabularies at or below it are listed in full.
PAGE_ROWS = 60

#: How many to show when the vocabulary does not fit.
TOP_N = 25


def listing(ctx: Context, count_sql: str, row_sql: str) -> tuple[list, int, bool]:
    """Return (rows, distinct values, whether the listing is complete).

    `row_sql` carries a `{limit}` placeholder so the caller keeps control of the
    ordering and the columns.
    """
    distinct = ctx.scalar(count_sql)
    complete = distinct <= PAGE_ROWS
    limit = "" if complete else f"LIMIT {TOP_N}"
    rows = ctx.q(row_sql.format(limit=limit))
    # A complete listing must show exactly what it counted. The usual cause of a
    # mismatch is count(DISTINCT x) dropping a null the grouping keeps.
    if complete and len(rows) != distinct:
        raise ValueError(
            f"listing claims {distinct} distinct values but returned {len(rows)} "
            f"rows; the count and the grouping disagree"
        )
    return rows, distinct, complete


def note(distinct: int, complete: bool, covered: float | None = None,
         unit: str = "records") -> str:
    """The sentence that tells a reader whether they are seeing everything."""
    if complete:
        return f"All {distinct:,} distinct values are listed."
    tail = "" if covered is None else (
        f", covering {covered:.1f}% of {unit}; the remaining "
        f"{distinct - TOP_N:,} values hold the rest")
    return (f"The {TOP_N} most frequent of {distinct:,} distinct values{tail}."
            if covered is not None else
            f"The {TOP_N} most frequent of {distinct:,} distinct values; "
            f"{distinct - TOP_N:,} more are not shown.")

"""The checklist map is a promise that each row can be followed somewhere.

`test_coverage_map_cites_only_sections_that_exist` makes the same check against
the built report, which means it only fails after a rebuild, and a rebuild needs
the restricted bundle. These run against `ITEMS` itself, so a row citing a
section nobody wrote fails the moment it is written, on a machine with no data.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports"))

from ppoc_eda.document import load_probes
from ppoc_eda.findings import registered
from ppoc_eda.probes.coverage import COVERED, ITEMS

SECTION = re.compile(r"\b(\d+\.\d+)\b")

#: `document.build` synthesises the artifact catalogue from whatever the probes
#: declared, so 7.1 is a real section of the report with no probe registered
#: against it. Every other section is a registered probe's part.
SYNTHESISED = {"7.1"}


def _sections() -> set[str]:
    load_probes()
    parts = {fn.probe_part for fn in registered().values()} | SYNTHESISED
    assert len(parts) > 10, f"only {len(parts)} sections registered; probes did not load"
    return parts


def test_every_section_a_checklist_row_cites_exists() -> None:
    """A row pointing at a section nobody wrote destroys the map's value."""
    sections = _sections()
    cited = {(item, part) for _, item, _, note in ITEMS
             for part in SECTION.findall(note)}
    # Without this the test passes by finding nothing, which is what a change to
    # how a note is written would otherwise do.
    assert len(cited) > 20, f"only {len(cited)} citations parsed; the note format changed"
    missing = sorted({(item, part) for item, part in cited if part not in sections})
    assert not missing, f"checklist rows cite sections that do not exist: {missing}"


def test_every_covered_row_points_at_a_section() -> None:
    """Covered is a claim about where the evidence is, so it has to say where.

    A partial row may legitimately have nowhere single to point — three of them
    explain a limit instead — but a row asserting the check was done and naming
    no section leaves a reader with no way to confirm it.
    """
    orphans = [item for _, item, status, note in ITEMS
               if status == COVERED and not SECTION.findall(note)]
    assert not orphans, f"rows marked covered that cite no section: {orphans}"

"""Read-only access to the PPOC bundle, plus the policies every probe shares.

The bundle is opened read-only and is never copied into the repository. Probes
emit aggregate values only; `suppress` is the single place the small-cell rule
is applied, so no probe has to remember it.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

REPO = Path(__file__).resolve().parent.parent.parent
OUT_DIR = REPO / "reports" / "ppoc-eda"
DEFAULT_BUNDLE = os.environ.get(
    "PPOC_DUCKDB", "/Users/joon/src/tries/ppoc-duckdb-real/ppoc.duckdb"
)

#: Cells backed by fewer than this many records are not displayed.
SUPPRESS_BELOW = 10

#: The only two calendar anchors that may appear anywhere in the outputs. Any
#: other date-shaped string is treated as a disclosure leak by the audit test.
COHORT_AS_OF = "31 Dec 2024"
EXTRACT_DATE = "03 Feb 2025"

RESOURCES = (
    "patients", "patients_augmented", "visits", "visits_augmented",
    "labs", "medications", "problem_list", "referrals",
)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 22), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class Context:
    """Everything a probe is allowed to touch."""

    con: duckdb.DuckDBPyConnection
    bundle: Path
    manifest: dict[str, Any] = field(default_factory=dict)
    digest: str = ""

    # -- querying ---------------------------------------------------------
    def q(self, sql: str) -> list[tuple]:
        return self.con.execute(sql).fetchall()

    def one(self, sql: str) -> tuple:
        return self.con.execute(sql).fetchone()

    def scalar(self, sql: str) -> Any:
        return self.con.execute(sql).fetchone()[0]

    def columns(self, table: str) -> list[str]:
        return [
            r[0] for r in self.q(
                "SELECT column_name FROM information_schema.columns "
                f"WHERE table_name = '{table}' ORDER BY ordinal_position"
            )
        ]

    def coltype(self, table: str) -> dict[str, str]:
        return dict(self.q(
            "SELECT column_name, data_type FROM information_schema.columns "
            f"WHERE table_name = '{table}'"
        ))

    # -- policy -----------------------------------------------------------
    @staticmethod
    def suppress(n: int | None) -> int | None:
        """Return the count, or None when it is too small to display."""
        if n is None:
            return None
        return n if n == 0 or n >= SUPPRESS_BELOW else None

    # -- provenance -------------------------------------------------------
    @property
    def package(self) -> dict[str, Any]:
        return self.manifest.get("package", {})

    @property
    def snapshot(self) -> str:
        return self.package.get("snapshot", "unknown")

    def declared_rows(self) -> dict[str, int]:
        """Row counts the bundle manifest declares, by resource."""
        for output in self.manifest.get("outputs", []):
            if output.get("basename") == self.bundle.name:
                return {t[0]: t[1] for t in output.get("tables", [])}
        return {}


def open_context(bundle: str | Path = DEFAULT_BUNDLE) -> Context:
    path = Path(bundle).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"DuckDB bundle not found: {path}")
    manifest_path = path.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    digest = ""
    for output in manifest.get("outputs", []):
        if output.get("basename") == path.name:
            digest = output.get("sha256", "")
    con = duckdb.connect(str(path), read_only=True)
    return Context(con=con, bundle=path, manifest=manifest, digest=digest)

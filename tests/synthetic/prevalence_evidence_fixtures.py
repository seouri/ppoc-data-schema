"""Wholly fictional exact-schema packages for prevalence-evidence tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from synthetic.manifest import RunManifest
from synthetic.schema_contract import schema_fingerprint
from synthetic.validate import validate_structure
from tests.synthetic.heldout_fixtures import descriptor_for, write_synthetic_package


def write_prevalence_package(
    root: Path,
    *,
    seed: int = 101,
    profile: str = "prevalence-fixture",
    derivation_fingerprint: str = "d" * 64,
    test_only: bool = False,
) -> Path:
    """Write a complete, non-production package with a generated-style manifest."""
    package = write_synthetic_package(root, id_prefix=f"PREV{seed}")
    descriptor = dict(descriptor_for(package))
    report = validate_structure(package, descriptor)
    assert not report.errors
    (package / "validation-report.json").write_text(
        json.dumps({"errors": [], "row_counts": report.row_counts}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    hashes = {
        path.relative_to(package).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(package.rglob("*"))
        if path.is_file()
    }
    manifest = RunManifest.generated(
        profile=profile,
        seed=seed,
        schema_fingerprint=schema_fingerprint(descriptor),
        reference_time="2026-09-01T00:00:00Z",
        reference_id="fictional-prevalence-reference-v1",
        reference_sha256="a" * 64,
        configuration_sha256="b" * 64,
        software_revision="fictional-revision-v1",
        derivation_fingerprint=derivation_fingerprint,
        test_only_derivation=test_only,
        row_counts=report.row_counts,
        file_sha256=hashes,
    )
    (package / "manifest.json").write_bytes(manifest.to_json_bytes())
    return package

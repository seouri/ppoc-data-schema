from __future__ import annotations

from dataclasses import replace

import pytest

from synthetic.manifest import RunManifest
from synthetic.package_export import PackageExportMetadata


def _metadata(**changes: object) -> PackageExportMetadata:
    values: dict[str, object] = {
        "profile": "synthea-development",
        "seed": 7,
        "reference_time": "2026-09-01T00:00:00Z",
        "reference_id": "synthea-reference-v1",
        "software_revision": "synthea-backend-v1",
        "configuration_sha256": "a" * 64,
        "reference_sha256": "b" * 64,
    }
    values.update(changes)
    return PackageExportMetadata(**values)  # type: ignore[arg-type]


def _generated(*, engine: str = "native") -> RunManifest:
    metadata = _metadata(engine=engine)
    return RunManifest.generated(
        profile=metadata.profile,
        seed=metadata.seed,
        schema_fingerprint="c" * 64,
        reference_time=metadata.reference_time,
        reference_id=metadata.reference_id,
        configuration_sha256=metadata.configuration_sha256,
        software_revision=metadata.software_revision,
        derivation_fingerprint="d" * 64,
        test_only_derivation=True,
        row_counts={"patients": 1},
        file_sha256={"patients.csv": "e" * 64},
        reference_sha256=metadata.reference_sha256,
        engine=metadata.engine,
    )


def test_package_metadata_defaults_to_native_and_accepts_synthea() -> None:
    assert _metadata().engine == "native"
    assert _metadata(engine="synthea").engine == "synthea"


def test_generated_manifest_preserves_engine_identity() -> None:
    assert _generated().engine == "native"
    assert _generated(engine="synthea").engine == "synthea"


@pytest.mark.parametrize("value", ["", "Synthea", "synthea/backend", "patient", 1, True])
def test_package_metadata_rejects_unsafe_engine(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        _metadata(engine=value)


def test_existing_metadata_can_be_copied_without_engine_aliasing() -> None:
    metadata = _metadata()
    copied = replace(metadata)
    assert copied == metadata
    assert copied.engine == "native"

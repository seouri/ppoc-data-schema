from __future__ import annotations

from pathlib import Path

from synthetic.synthea_conformance import (
    SYNTHEA_CONFORMANCE_VERSION,
    SyntheaEngineManifest,
)

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "synthea-conformance.md"
README = ROOT / "README.md"
SYNTHETIC_GUIDE = ROOT / "docs" / "synthetic-generator.md"
PRODUCTION_FAILURE = (
    "No production growth reference or authoritative derivation oracle is configured"
)
MANIFEST_FIELDS = (
    "manifest_version",
    "engine_id",
    "engine_revision",
    "engine_sha256",
    "module_manifest_sha256",
    "growth_extension_id",
    "growth_extension_sha256",
    "event_adapter_id",
    "event_adapter_sha256",
    "ppoc_exporter_id",
    "ppoc_exporter_sha256",
    "configuration_sha256",
    "license_notice_id",
    "review_status",
    "test_only",
)


def _guide_text() -> str:
    assert GUIDE.is_file(), "optional Synthea conformance guide is missing"
    return GUIDE.read_text(encoding="utf-8")


def test_guide_names_the_fixed_declaration_and_every_manifest_identity() -> None:
    """Breaks if the future handoff loses a declared aggregate identity."""
    guide = _guide_text()

    assert "SyntheaEngineManifest" in guide
    assert SYNTHEA_CONFORMANCE_VERSION == "synthea-conformance-v1"
    assert 'SYNTHEA_CONFORMANCE_VERSION = "synthea-conformance-v1"' in guide
    assert 'engine_id="synthea"' in guide
    assert tuple(SyntheaEngineManifest.__dataclass_fields__) == MANIFEST_FIELDS
    for field in MANIFEST_FIELDS:
        assert f"`{field}`" in guide


def test_guide_keeps_the_external_handoff_and_non_authority_explicit() -> None:
    """Breaks if declaration metadata is presented as runtime or evidence."""
    guide = _guide_text()
    lowered = guide.lower()

    for label in ("optional", "future", "development-only"):
        assert label in lowered
    for requirement in (
        "externally pinned engine revision",
        "license/attribution review",
        "review_status=\"PENDING\"",
        "test_only=True",
        "derivation binding",
        "counterfactual",
        "task utility",
        "reproducibility",
        "privacy",
        "clinical review",
        "release gates",
    ):
        assert requirement in guide
    for unavailable in (
        "no Synthea implementation",
        "no Java runtime",
        "no conformance result",
        "no patient data",
        "no network access",
        "no release authorization",
    ):
        assert unavailable in guide
    assert "cannot authorize execution" in guide
    assert "cannot imply Synthea conformance" in guide


def test_guide_has_a_fictional_copy_pasteable_aggregate_manifest_example() -> None:
    """Breaks if the example stops showing declaration-only serialization."""
    guide = _guide_text()

    for required in (
        "from synthetic.synthea_conformance import",
        "SyntheaEngineManifest(",
        'engine_revision="revision-20260901"',
        'growth_extension_id="growth-extension-v1"',
        'event_adapter_id="event-adapter-v1"',
        'ppoc_exporter_id="ppoc-exporter-v1"',
        'license_notice_id="apache-notice-v1"',
        "review_status=\"PENDING\"",
        "test_only=True",
        "manifest.to_json_bytes()",
        "fictional",
        "aggregate identities",
    ):
        assert required in guide


def test_cross_document_links_preserve_native_release_one_and_fail_closed_cli() -> None:
    """Breaks if optional metadata is wired into the current production route."""
    readme = README.read_text(encoding="utf-8")
    synthetic_guide = SYNTHETIC_GUIDE.read_text(encoding="utf-8")
    guide = _guide_text()

    assert "[optional Synthea engine-conformance guide](docs/synthea-conformance.md)" in readme
    assert "[optional Synthea engine-conformance guide](synthea-conformance.md)" in synthetic_guide
    assert PRODUCTION_FAILURE in readme
    assert PRODUCTION_FAILURE in synthetic_guide
    assert "native generator remains the release-one route" in readme
    assert "native generator remains the release-one route" in synthetic_guide
    assert "not imported automatically by generation, export, or evaluator code" in readme
    assert "not imported automatically by generation, export, or evaluator code" in synthetic_guide
    assert "synthetic-growth-fixtures-design.md" in guide
    assert "synthetic-generator.md" in guide
    assert "augment-import.md" in guide

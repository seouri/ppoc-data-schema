from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_GUIDE = ROOT / "docs" / "synthea-backend.md"
SYNTHETIC_GUIDE = ROOT / "docs" / "synthetic-generator.md"
CONFORMANCE_GUIDE = ROOT / "docs" / "synthea-conformance.md"


def test_backend_guide_has_the_executable_command_and_pinned_toolchain() -> None:
    text = BACKEND_GUIDE.read_text(encoding="utf-8")
    for required in (
        "scripts/synthea_backend.py",
        "d9d07a6eef91ee5144293b42ab64224d84d124f8",
        "Java 17",
        "Gradle 9.2.1",
        "--synthea-root",
        "--patients 1000",
        "--seed 20260901",
        "--allow-gradle-network",
        "engine=\"synthea\"",
        "test_only_derivation=true",
        "synthea-growth-overlay-v1",
        "0.143291",
        "synthea backend unavailable",
    ):
        assert required in text


def test_backend_guide_keeps_content_and_claim_boundaries_explicit() -> None:
    text = BACKEND_GUIDE.read_text(encoding="utf-8").lower()
    for required in (
        "fresh deterministic",
        "raw fhir",
        "hidden disorder state",
        "never overwritten",
        "not evidence",
        "prevalence",
        "non-matchability",
        "does not vendor synthea",
        "default/no-profile cli continues to fail closed",
    ):
        assert required in text


def test_existing_guides_link_to_the_implemented_backend_without_wiring_it_in() -> None:
    synthetic = SYNTHETIC_GUIDE.read_text(encoding="utf-8")
    conformance = CONFORMANCE_GUIDE.read_text(encoding="utf-8")
    assert "[Synthea backend guide](synthea-backend.md)" in synthetic
    assert "[the Synthea backend guide](synthea-backend.md)" in conformance
    assert "native generator remains the release-one route" in synthetic
    assert "No production growth reference or authoritative derivation oracle is configured" in synthetic
    assert "not a conformance result" in conformance

from __future__ import annotations

from pathlib import Path

from synthetic.augmenter_oracle import (
    AUGMENTER_ORACLE_ID,
    AUGMENTER_RUNTIME_MANIFEST_SHA256,
)

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "augmenter-oracle.md"
README = ROOT / "README.md"
SYNTHETIC_GUIDE = ROOT / "docs" / "synthetic-generator.md"


def _guide_text() -> str:
    assert GUIDE.is_file(), "candidate augmenter-oracle guide is missing"
    return GUIDE.read_text(encoding="utf-8")


def test_candidate_guide_states_the_runtime_and_export_contract() -> None:
    """Breaks if the candidate guide obscures execution or package-export boundaries."""
    guide = _guide_text()

    for required in (
        "SourceMatchedAugmenterOracle",
        AUGMENTER_ORACLE_ID,
        AUGMENTER_RUNTIME_MANIFEST_SHA256,
        "export_exact_schema_package",
        "derivation_oracle=candidate_oracle",
        "derivation_binding=candidate_test_binding",
        "staged package",
        "private temporary runtime snapshot",
        "`-E -s`",
        "exactly two",
        "visits_augmented-YYYYMMDDHHMMSS.csv",
        "patients_augmented-YYYYMMDDHHMMSS.csv",
        "CSV only",
    ):
        assert required in guide


def test_candidate_guide_keeps_test_only_safety_and_evidence_limits_explicit() -> None:
    """Breaks if a source-matched runtime is documented as approved evidence."""
    guide = _guide_text()

    for required in (
        "wholly synthetic",
        "test-only",
        "non-authoritative",
        "Do not use real or governed patient data",
        "does not prove clinical validity",
        "prevalence",
        "demographic fidelity",
        "privacy",
        "non-matchability",
        "release readiness",
        "Synthea conformance",
        "No production growth reference or authoritative derivation oracle is configured",
        "parity",
        "golden",
        "clinical review",
        "release",
    ):
        assert required in guide


def test_candidate_guide_is_linked_without_enabling_the_production_cli() -> None:
    """Breaks if handoff docs lose the candidate guide or imply production authority."""
    readme = README.read_text(encoding="utf-8")
    synthetic_guide = SYNTHETIC_GUIDE.read_text(encoding="utf-8")
    combined = f"{readme}\n{synthetic_guide}"

    assert "[synthetic generator guide](docs/synthetic-generator.md)" in readme
    assert "[candidate augmenter-oracle guide](augmenter-oracle.md)" in synthetic_guide
    assert "production command has no configured authoritative oracle" in combined
    assert "No production growth reference or authoritative derivation oracle is configured" in combined
    assert "synthetic.generate" in combined

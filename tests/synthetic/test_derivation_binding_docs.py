from __future__ import annotations

from pathlib import Path

from synthetic.derivation_binding import (
    DERIVATION_BINDING_VERSION,
    REQUIRED_GOLDEN_CATEGORIES,
)

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "synthetic-generator.md"
README = ROOT / "README.md"


def test_documentation_states_the_derivation_binding_contract_and_boundaries() -> None:
    """Breaks if handoff guidance stops requiring the aggregate binding boundary."""
    guide = GUIDE.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    combined = f"{guide}\n{readme}"

    assert "## Authoritative derivation binding" in guide
    assert DERIVATION_BINDING_VERSION == "derivation-binding-v1"
    assert 'DERIVATION_BINDING_VERSION = "derivation-binding-v1"' in guide
    for category in REQUIRED_GOLDEN_CATEGORIES:
        assert f"`{category}`" in guide
    assert "test-only binding" in combined
    assert "approved non-test binding" in combined
    assert "aggregate-only" in combined
    assert "no rows, paths, or secrets" in combined
    assert "FAIL > UNEVALUABLE > PASS" in combined
    assert "`derivation_binding`" in guide
    assert "does not execute an external harness" in combined
    assert "fails closed" in combined
    for boundary in (
        "clinical validity",
        "privacy",
        "prevalence",
        "Synthea",
        "release authorization",
    ):
        assert boundary in combined
    assert "Synthea remains an optional later engine-conformance route." in combined


def test_documentation_uses_a_fictional_binding_and_explicit_exporter_argument() -> None:
    """Breaks if examples reintroduce unbound trust metadata or real evidence inputs."""
    guide = GUIDE.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    combined = f"{guide}\n{readme}"

    assert "DerivationBinding.from_mapping(" in guide
    assert '"test_only": True' in guide
    assert "derivation_binding=test_binding" in guide
    assert "IdentityPreservingTestDerivationOracle" in guide
    assert "explicitly test-only" in guide
    assert "golden inputs/outputs, fuzz rows, and parity report bytes" in guide
    assert "only safe IDs/digests are recorded in the repository" in guide
    assert "trusted_derivation_fingerprint" not in combined
    assert "trusted_derivation_test_only" not in combined

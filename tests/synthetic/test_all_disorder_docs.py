"""Documentation contracts for the explicit all-disorder development route."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALL_DISORDER_COMMAND = (
    "uv run python -m synthetic.generate --profile development-all-disorders "
    "--output /tmp/ppoc-development-all-disorders --patients 1000 --seed 20260901"
)
ALL_DISORDER_PROFILES = (
    "development-smoke",
    "development-cohort",
    "development-realistic",
    "development-all-disorders",
)


def test_synthetic_guide_documents_all_disorder_coverage_route() -> None:
    guide = (ROOT / "docs" / "synthetic-generator.md").read_text()

    assert ALL_DISORDER_COMMAND in guide
    assert "development-all-disorders-v1" in guide
    assert "snapshot-shaped demographics" in guide
    assert "fictional coverage" in guide
    assert "prevalence estimate" in guide
    assert "Turner" in guide
    assert "F-reference-only" in guide
    assert "E23.0" in guide
    assert "exact eight-resource" in guide
    assert "hidden truth" in guide
    assert "No production growth reference or authoritative derivation oracle is configured" in guide

    for target in (
        "growth-hormone deficiency",
        "pediatric hypothyroidism",
        "celiac",
        "small-for-gestational-age",
        "Turner syndrome",
        "undernutrition",
        "excess weight",
    ):
        assert target in guide


def test_readme_links_roadmap_without_copying_the_guide() -> None:
    readme = (ROOT / "README.md").read_text()

    assert "docs/synthetic-generator.md" in readme
    assert "docs/superpowers/specs/2026-09-03-all-disorder-development-profile-design.md" in readme
    assert "docs/superpowers/plans/2026-09-03-all-disorder-coverage-profile.md" in readme
    assert ALL_DISORDER_COMMAND not in readme
    assert "development-all-disorders-v1" not in readme


def test_augmenter_guides_list_every_explicit_development_profile() -> None:
    for relative_path in ("docs/augment-import.md", "docs/augmenter-oracle.md"):
        document = (ROOT / relative_path).read_text()
        for profile in ALL_DISORDER_PROFILES:
            assert profile in document
        assert "fail-closed" in document
        assert "No production growth reference or authoritative derivation oracle is configured" in document


def test_parent_cli_and_fixture_designs_reconcile_follow_on_profile() -> None:
    documents = (
        ROOT / "docs/superpowers/specs/2026-09-01-development-authority-generator-cli-design.md",
        ROOT / "docs/superpowers/plans/2026-09-01-development-authority-generator-cli.md",
        ROOT / "docs/superpowers/specs/2026-08-30-synthetic-growth-fixtures-design.md",
    )

    for path in documents:
        document = path.read_text()
        assert "development-all-disorders" in document
        assert "historical three-profile" in document
        assert "healthy/GHD" in document or "healthy-plus-GHD" in document
        assert "GHD-only" in document or "GHD ancillary" in document

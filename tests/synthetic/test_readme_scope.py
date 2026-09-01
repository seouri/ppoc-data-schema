from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
GUIDE = ROOT / "docs" / "synthetic-generator.md"


def test_readme_points_to_the_dedicated_synthetic_generator_guide() -> None:
    readme = README.read_text(encoding="utf-8")
    guide = GUIDE.read_text(encoding="utf-8")

    heading = "## Synthetic generator\n"
    assert heading in readme
    section = readme.split(heading, maxsplit=1)[1].split("\n## ", maxsplit=1)[0]
    assert section == (
        "\nSee the [synthetic generator guide](docs/synthetic-generator.md) for "
        "development-only synthetic fixture generation, validation, and governance boundaries.\n"
    )

    for detailed_heading in (
        "## Evaluator-only augmented-derivation parity gate",
        "## Authoritative derivation binding",
        "### Development-only native calibrated cohort",
        "## Evaluator-only synthetic task-utility evaluation",
        "## Aggregate calibration artifacts (development boundary)",
        "## Patient-disjoint held-out validation",
        "## Governed multi-run prevalence evidence",
        "## Evaluator-only trajectory counterfactual validation",
        "## Evaluator-only observation frame",
        "## Evaluator-only observed resource bundles",
        "## Pair-aware exact-schema counterfactual package export",
        "## Governed privacy-audit evidence",
    ):
        assert detailed_heading not in readme
        assert detailed_heading in guide

    assert (
        "[synthetic growth fixture specification]("
        "superpowers/specs/2026-08-30-synthetic-growth-fixtures-design.md)"
        in guide
    )

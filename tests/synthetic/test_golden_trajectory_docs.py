from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from synthetic.golden_trajectories import GOLDEN_CASE_IDS, GOLDEN_TRAJECTORY_VERSION

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "golden-trajectories.md"
README = ROOT / "README.md"
SYNTHETIC_GUIDE = ROOT / "docs" / "synthetic-generator.md"
PRODUCTION_FAILURE = (
    "No production growth reference or authoritative derivation oracle is configured"
)


def _guide_text() -> str:
    assert GUIDE.is_file(), "golden trajectory guide is missing"
    return GUIDE.read_text(encoding="utf-8")


def _python_example(document: str) -> str:
    blocks = document.split("```python\n")
    assert len(blocks) == 2, "guide must contain exactly one Python example"
    return blocks[1].split("\n```", maxsplit=1)[0]


def test_guide_names_the_fixed_catalog_regimes_and_directional_patterns() -> None:
    """Breaks if the guide stops identifying the exact forced-coverage contract."""
    guide = _guide_text()

    assert GOLDEN_TRAJECTORY_VERSION == "growth-golden-v1"
    assert "`growth-golden-v1`" in guide
    for case_id in GOLDEN_CASE_IDS:
        assert f"`{case_id}`" in guide
    for regime in ("infancy", "transition", "childhood", "puberty", "adolescence"):
        assert f"`{regime}`" in guide
    for pattern in (
        "zero",
        "constant_negative",
        "delayed_recovery",
        "progression_response",
        "positive_after_onset",
        "birth_catch_up",
    ):
        assert f"`{pattern}`" in guide


def test_guide_example_executes_with_the_fictional_reference_and_safe_report() -> None:
    """Breaks if the documented repository-root example is no longer executable."""
    example = _python_example(_guide_text())

    completed = subprocess.run(
        [sys.executable, "-c", example],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    mapping = json.loads(completed.stdout)
    assert mapping["report_version"] == "growth-golden-v1"
    assert mapping["status"] == "PASS"
    assert [result["case_id"] for result in mapping["case_results"]] == list(GOLDEN_CASE_IDS)
    assert all(
        set(result) == {"case_id", "status", "reason_codes"} for result in mapping["case_results"]
    )
    assert "RegimeLinearTestReference" in example
    assert "run_golden_trajectory_suite(reference, cases=DEFAULT_GOLDEN_CASES)" in example
    assert "report.to_json_bytes()" in example


def test_guide_documents_aggregate_report_failure_and_hidden_state_boundary() -> None:
    """Breaks if the evaluator guide implies that hidden trajectory truth is visible."""
    guide = _guide_text()

    for field in ("report_version", "status", "case_results", "case_id", "reason_codes"):
        assert f"`{field}`" in guide
    assert 'GoldenTrajectoryUnavailable("golden trajectory suite unavailable")' in guide
    assert "without exception chaining" in guide
    for boundary in (
        "evaluator-only",
        "in-memory",
        "forced coverage",
        "hidden explicit states",
        "aggregate-only",
        "does not generate a package",
    ):
        assert boundary in guide


def test_guide_documents_unobserved_probe_ages_and_disorder_sequences() -> None:
    """Breaks if sampled ages and directional probes are presented as interchangeable."""
    guide = _guide_text()

    assert "Pattern probes may be unobserved ages between trajectory samples" in guide
    assert "`(4380, 4740, 5470)`" in guide
    assert "`(3000, 3510, 3875, 5000)`" in guide
    assert "`(2190, 2640, 3005, 3500)`" in guide
    assert "`(0, 365, 730, 1825)`" in guide
    assert "weight/BMI-first decline" in guide
    assert "delayed height decline" in guide
    assert "BMI channel is monotone toward zero" in guide
    assert "height channel either reaches zero by day 1825 or remains constant and negative" in guide
    for semantic in (
        "zero at onset",
        "negative at treatment",
        "strict improvement during the active response interval",
        "no later regression at the post-response probe",
        "plateau is allowed after response completion",
    ):
        assert semantic in guide


def test_guide_explicitly_disclaims_every_deferred_evidence_gate() -> None:
    """Breaks if forced scenarios are presented as representative or release evidence."""
    guide = _guide_text()

    for non_claim in (
        "prevalence",
        "demographic fidelity",
        "clinical validity",
        "task utility",
        "privacy/non-matchability",
        "held-out",
        "scale",
        "Synthea",
        "release evidence",
    ):
        assert non_claim in guide
    for separate_gate in ("schema", "export", "derivation", "calibration", "clinical review"):
        assert separate_gate in guide


def test_cross_document_links_preserve_native_release_one_and_fail_closed_cli() -> None:
    """Breaks if the evaluator-only catalog is coupled to the production command."""
    readme = README.read_text(encoding="utf-8")
    synthetic_guide = SYNTHETIC_GUIDE.read_text(encoding="utf-8")
    guide = _guide_text()

    assert "[synthetic generator guide](docs/synthetic-generator.md)" in readme
    assert "[golden trajectory guide](golden-trajectories.md)" in synthetic_guide
    assert PRODUCTION_FAILURE in synthetic_guide
    assert "native generator remains the release-one route" in synthetic_guide
    assert "synthetic-growth-fixtures-design.md" in guide
    assert "synthetic-generator.md#development-only-age-regime-smoke-example" in guide
    assert "synthea-conformance.md" in guide

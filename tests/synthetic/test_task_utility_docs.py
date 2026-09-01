from __future__ import annotations

import json
from pathlib import Path

from synthetic.task_utility import evaluate_task_utility
from tests.synthetic.task_utility_fixtures import (
    balanced_task_cohort,
    scored_task_predictions,
    task_policy,
)

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "synthetic-generator.md"
README = ROOT / "README.md"

_METRICS = (
    "sensitivity",
    "specificity",
    "precision",
    "balanced_accuracy",
    "auroc",
    "brier_score",
    "false_positive_count",
    "false_negative_count",
)
_NON_CLAIMS = (
    "clinical utility",
    "real-data performance",
    "generalization",
    "prevalence evidence",
    "privacy/non-matchability",
    "release readiness",
    "Synthea conformance",
)


def _task_section(document: str, heading: str) -> str:
    return document.split(heading, maxsplit=1)[1].split("\n## ", maxsplit=1)[0]


def _nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key
            for nested in value.values()
            for key in _nested_keys(nested)
        }
    if isinstance(value, list):
        return {
            key
            for nested in value
            for key in _nested_keys(nested)
        }
    return set()


def test_guide_documents_exact_task_evaluator_api_and_ordered_adapter() -> None:
    guide = GUIDE.read_text(encoding="utf-8")
    section = _task_section(
        guide,
        "## Evaluator-only synthetic task-utility evaluation\n",
    )

    for name in (
        "TaskPrediction",
        "TaskUtilityPolicy",
        "TaskUtilityStatus",
        "evaluate_task_utility",
    ):
        assert name in section
    assert "predictions = tuple(" in section
    assert "for member in cohort.members" in section
    assert "report = evaluate_task_utility(cohort, predictions, policy)" in section
    assert "stable cohort order" in section


def test_guide_documents_metrics_statuses_scopes_and_optional_scores() -> None:
    guide = GUIDE.read_text(encoding="utf-8")
    section = _task_section(
        guide,
        "## Evaluator-only synthetic task-utility evaluation\n",
    )

    for metric in _METRICS:
        assert metric in section
    for status in ("PASS", "FAIL", "UNEVALUABLE"):
        assert status in section
    for scope in ("overall", "sex:F", "sex:M", "sex:U"):
        assert scope in section
    assert "require_probability_scores=False" in section
    assert "UNEVALUABLE/MISSING_SCORE" in section
    assert "minimum_class_support" in section
    assert "minimum_sensitivity" in section
    assert "maximum_brier_score" in section
    assert "aggregate-only" in section
    assert "hidden truth" in section


def test_guide_states_every_task_utility_nonclaim_and_readme_links_the_guide() -> None:
    guide = GUIDE.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    section = _task_section(
        guide,
        "## Evaluator-only synthetic task-utility evaluation\n",
    )

    for boundary in _NON_CLAIMS:
        assert boundary in section
    assert "[synthetic generator guide](docs/synthetic-generator.md)" in readme


def test_ordinary_mappings_remain_free_of_private_task_truth() -> None:
    cohort = balanced_task_cohort()
    report = evaluate_task_utility(
        cohort,
        scored_task_predictions(),
        task_policy(),
    )
    mappings = (
        cohort.to_mapping(),
        cohort.members[0].to_mapping(),
        cohort.members[0].frame.to_mapping(),
        report.to_mapping(),
    )
    forbidden_keys = {
        "disorder",
        "latent_trajectory",
        "risk_score",
        "trajectory",
        "truth",
    }

    for mapping in mappings:
        assert not forbidden_keys & _nested_keys(mapping)
        serialized = json.dumps(mapping, sort_keys=True)
        assert "growth_hormone_deficiency" not in serialized

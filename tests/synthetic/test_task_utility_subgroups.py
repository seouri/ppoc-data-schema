from __future__ import annotations

import dataclasses

import pytest

from synthetic.cohort import CohortMember
from synthetic.models import DisorderKind
from synthetic.task_utility import (
    TASK_METRICS,
    TaskPrediction,
    TaskUtilityPolicy,
    TaskUtilityStatus,
    evaluate_task_utility,
)
from tests.synthetic.task_utility_fixtures import (
    balanced_task_cohort,
    scored_task_predictions,
    task_cohort,
    task_member,
    task_policy,
)


def _subgroup_policy(**changes: object) -> TaskUtilityPolicy:
    return task_policy(
        subgroup_dimensions=("sex",),
        minimum_sensitivity=0.0,
        minimum_specificity=0.0,
        minimum_auroc=0.0,
        maximum_brier_score=1.0,
        **changes,
    )


def _cell(report: object, scope: str) -> object:
    return next(
        cell
        for cell in report.cells  # type: ignore[attr-defined]
        if cell.scope == scope
    )


def _assert_static_fallback(report: object, hostile_value: object) -> None:
    mapping = report.to_mapping()  # type: ignore[attr-defined]
    assert mapping["status"] == "FAIL"
    assert mapping["reason_code"] == "STRUCTURAL_INVALID"
    assert mapping["policy_id"] == "unavailable"
    assert mapping["cohort_profile"] == "unavailable"
    assert mapping["cohort_seed"] == 0
    assert mapping["cohort_size"] == 0
    assert str(hostile_value) not in report.canonical_json()  # type: ignore[attr-defined]


def test_empty_subgroup_policy_emits_only_overall_cell() -> None:
    report = evaluate_task_utility(
        balanced_task_cohort(),
        scored_task_predictions(),
        task_policy(),
    )

    assert tuple(cell.scope for cell in report.cells) == ("overall",)
    assert report.metric_counts == {name: 1 for name in TASK_METRICS}


def test_requested_sex_subgroups_use_fixed_observed_category_order() -> None:
    cohort = task_cohort(
        *balanced_task_cohort().members,
        task_member(5, DisorderKind.GROWTH_HORMONE_DEFICIENCY, sex="U"),
        task_member(6, DisorderKind.HEALTHY, sex="U"),
    )
    predictions = (
        *scored_task_predictions()[:3],
        TaskPrediction(True, 0.25),
        TaskPrediction(True, 0.8),
        TaskPrediction(False, 0.2),
    )

    report = evaluate_task_utility(cohort, predictions, _subgroup_policy())

    assert tuple(cell.scope for cell in report.cells) == (
        "overall",
        "sex:F",
        "sex:M",
        "sex:U",
    )
    assert report.status is TaskUtilityStatus.PASS
    assert report.status_counts == {"PASS": 4, "FAIL": 0, "UNEVALUABLE": 0}
    assert report.metric_counts == {name: 4 for name in TASK_METRICS}


def test_absent_sex_categories_are_omitted() -> None:
    report = evaluate_task_utility(
        balanced_task_cohort(),
        scored_task_predictions(),
        _subgroup_policy(),
    )

    assert tuple(cell.scope for cell in report.cells) == (
        "overall",
        "sex:F",
        "sex:M",
    )
    assert report.metric_counts == {name: 3 for name in TASK_METRICS}


def test_present_subgroups_below_class_support_block_and_are_redacted() -> None:
    report = evaluate_task_utility(
        balanced_task_cohort(),
        scored_task_predictions(),
        _subgroup_policy(minimum_class_support=2),
    )

    assert report.status is TaskUtilityStatus.UNEVALUABLE
    assert report.reason_code == "INSUFFICIENT_SUPPORT"
    assert report.status_counts == {"PASS": 1, "FAIL": 0, "UNEVALUABLE": 2}
    for scope in ("sex:F", "sex:M"):
        cell = _cell(report, scope)
        assert cell.status is TaskUtilityStatus.UNEVALUABLE
        assert cell.reason_code == "INSUFFICIENT_SUPPORT"
        assert (
            cell.positive_count,
            cell.negative_count,
            cell.true_positive,
            cell.true_negative,
            cell.false_positive,
            cell.false_negative,
        ) == (None, None, None, None, None, None)
        assert all(
            metric.status is TaskUtilityStatus.UNEVALUABLE
            and metric.observed is None
            and metric.target is None
            and metric.support_count is None
            for metric in cell.metrics
        )


def test_one_subgroup_threshold_failure_blocks_passing_overall() -> None:
    predictions = (
        TaskPrediction(True, 0.9),
        TaskPrediction(False, 0.2),
        TaskPrediction(False, 0.1),
        TaskPrediction(False, 0.1),
    )
    report = evaluate_task_utility(
        balanced_task_cohort(),
        predictions,
        task_policy(subgroup_dimensions=("sex",)),
    )

    assert _cell(report, "overall").status is TaskUtilityStatus.PASS
    assert _cell(report, "sex:F").status is TaskUtilityStatus.PASS
    assert _cell(report, "sex:M").status is TaskUtilityStatus.FAIL
    assert report.status is TaskUtilityStatus.FAIL
    assert report.reason_code == "OUTSIDE_BOUND"
    assert report.status_counts == {"PASS": 2, "FAIL": 1, "UNEVALUABLE": 0}


def test_missing_prediction_in_subgroup_blocks_overall_allowance() -> None:
    predictions = (
        TaskPrediction(True, 0.75),
        TaskPrediction(False, 0.5),
        TaskPrediction(None),
        TaskPrediction(False, 0.25),
    )
    report = evaluate_task_utility(
        balanced_task_cohort(),
        predictions,
        _subgroup_policy(maximum_unevaluable_members=1),
    )

    assert _cell(report, "overall").reason_code == "MISSING_PREDICTION"
    subgroup = _cell(report, "sex:F")
    assert subgroup.status is TaskUtilityStatus.UNEVALUABLE
    assert subgroup.reason_code == "MISSING_PREDICTION"
    assert all(
        metric.status is TaskUtilityStatus.UNEVALUABLE
        and metric.observed is None
        and metric.target is None
        and metric.support_count is None
        for metric in subgroup.metrics
    )
    assert report.status is TaskUtilityStatus.UNEVALUABLE
    assert report.reason_code == "MISSING_PREDICTION"


def test_subgroup_failure_mode_counts_match_overall_aggregates() -> None:
    predictions = (
        *scored_task_predictions()[:3],
        TaskPrediction(True, 0.25),
    )
    report = evaluate_task_utility(
        balanced_task_cohort(),
        predictions,
        _subgroup_policy(),
    )

    overall = _cell(report, "overall")
    female = _cell(report, "sex:F")
    male = _cell(report, "sex:M")
    assert (overall.false_positive, overall.false_negative) == (2, 1)
    assert (female.false_positive, female.false_negative) == (1, 0)
    assert (male.false_positive, male.false_negative) == (1, 1)
    assert female.false_positive + male.false_positive == overall.false_positive
    assert female.false_negative + male.false_negative == overall.false_negative


def test_nonsex_subgroup_dimensions_are_not_caller_defined() -> None:
    with pytest.raises(ValueError, match="subgroup_dimensions"):
        task_policy(subgroup_dimensions=("ethnicity",))
    with pytest.raises(ValueError, match="subgroup_dimensions"):
        task_policy(subgroup_dimensions=("sex", "sex"))


def test_subgroup_report_ignores_demographics_beyond_fixed_sex() -> None:
    baseline = balanced_task_cohort()
    member = baseline.members[0]
    demographics = dataclasses.replace(
        member.demographics,
        ethnicity="Hispanic or Latino",
        races=("White",) * 8,
    )
    changed_member = CohortMember(
        demographics,
        member.trajectory,
        member.frame,
        member.bundle,
    )
    changed = dataclasses.replace(
        baseline,
        members=(changed_member, *baseline.members[1:]),
    )

    first = evaluate_task_utility(
        baseline,
        scored_task_predictions(),
        _subgroup_policy(),
    )
    second = evaluate_task_utility(
        changed,
        scored_task_predictions(),
        _subgroup_policy(),
    )

    assert first.to_json_bytes() == second.to_json_bytes()
    assert "ethnicity" not in first.canonical_json()
    assert "race" not in first.canonical_json()


@pytest.mark.parametrize(
    ("target", "field", "hostile_value"),
    (
        ("demographics", "sex", "patient-secret-sex"),
        ("disorder", "kind", "patient-secret-latent-kind"),
    ),
)
def test_malformed_subgroup_evidence_returns_static_fallback(
    target: str,
    field: str,
    hostile_value: object,
) -> None:
    cohort = balanced_task_cohort()
    targets = {
        "demographics": cohort.members[0].demographics,
        "disorder": cohort.members[0].trajectory.disorder,
    }
    object.__setattr__(targets[target], field, hostile_value)

    report = evaluate_task_utility(
        cohort,
        scored_task_predictions(),
        _subgroup_policy(),
    )

    _assert_static_fallback(report, hostile_value)


def test_subgroup_mapping_contains_no_member_identity_or_private_values() -> None:
    cohort = balanced_task_cohort()
    predictions = (
        TaskPrediction(True, 0.91),
        TaskPrediction(False, 0.81),
        TaskPrediction(True, 0.61),
        TaskPrediction(False, 0.11),
    )
    report = evaluate_task_utility(cohort, predictions, _subgroup_policy())
    serialized = report.canonical_json()

    assert all(member.demographics.patient_id not in serialized for member in cohort.members)
    assert not {
        "patient_id",
        "visit_id",
        "truth",
        "risk_score",
        "ethnicity",
        "races",
    } & set(report.to_mapping())

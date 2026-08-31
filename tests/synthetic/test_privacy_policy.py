from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from synthetic.privacy_audit import (
    PrivacyAuditReport,
    PrivacyAuditResult,
    PrivacyControlResult,
    PrivacyPolicy,
    PrivacyRunConfig,
    load_privacy_policy,
)
from tests.synthetic.privacy_fixtures import policy_mapping, write_policy


def _passing_controls() -> tuple[PrivacyControlResult, ...]:
    return (
        PrivacyControlResult(
            control_id="exact_reproduction",
            status="PASS",
            metrics={"exact_reproduction_rate": 0.0, "evaluated_count": 3},
            reason_code="no_reproduction",
        ),
        PrivacyControlResult(
            control_id="identifier_overlap",
            status="PASS",
            metrics={"overlap_rate": 0.0, "evaluated_count": 3},
            reason_code="no_overlap",
        ),
    )


def _control_counts(controls: tuple[PrivacyControlResult, ...]) -> dict[str, int]:
    return {status: sum(control.status == status for control in controls) for status in ("PASS", "FAIL", "UNEVALUABLE")}


def test_load_privacy_policy_accepts_only_the_complete_approved_contract(tmp_path: Path) -> None:
    policy = load_privacy_policy(write_policy(tmp_path / "policy.json"))

    assert policy == PrivacyPolicy.from_mapping(policy_mapping())
    assert policy.required_controls == ("exact_reproduction", "identifier_overlap")
    assert policy.attacker_knowledge == (
        "demographics",
        "diagnosis",
        "timing",
        "trajectory",
        "utilization",
    )


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda value: value.__setitem__("unexpected", "x"), "policy keys"),
        (lambda value: value.pop("approver"), "policy keys"),
        (lambda value: value.__setitem__("minimum_evaluable_patients", True), "integer"),
        (lambda value: value.__setitem__("attacker_knowledge", ["timing", "timing"]), "duplicate"),
        (lambda value: value.__setitem__("attacker_knowledge", ["freeform"]), "component"),
        (lambda value: value.__setitem__("required_controls", ["freeform"]), "control"),
        (lambda value: value.__setitem__("review_date", "2026-02-30"), "review_date"),
        (lambda value: value.__setitem__("schema_fingerprint", "0" * 64), "fingerprint"),
        (lambda value: value.__setitem__("policy_id", "unsafe value"), "token"),
        (lambda value: value["thresholds"].__setitem__("linkage_advantage", 1.01), "threshold"),
        (
            lambda value: (
                value.__setitem__(
                    "required_controls",
                    ["exact_reproduction", "identifier_overlap", "positive_control"],
                ),
                value["thresholds"].__setitem__("positive_control_advantage", 0),
            ),
            "positive_control_advantage",
        ),
    ],
)
def test_privacy_policy_rejects_unapproved_or_unsafe_values(
    tmp_path: Path, mutate: object, expected: str
) -> None:
    value = policy_mapping()
    mutate(value)  # type: ignore[operator]
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(ValueError, match=expected):
        load_privacy_policy(path)


@pytest.mark.parametrize(
    "payload",
    [
        '{"policy_id":"one","policy_id":"two"}',
        '{"policy_id":NaN}',
    ],
)
def test_load_privacy_policy_rejects_duplicate_or_nonfinite_json_without_echoing_payload(
    tmp_path: Path, payload: str
) -> None:
    path = tmp_path / "policy.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError) as error:
        load_privacy_policy(path)

    assert payload not in str(error.value)


def test_run_config_is_immutable_and_contains_only_explicit_paths(tmp_path: Path) -> None:
    config = PrivacyRunConfig(
        real_root=tmp_path / "real",
        synthetic_root=tmp_path / "generated",
        policy=tmp_path / "policy.json",
        output=tmp_path / "output",
        prior_release_roots=(tmp_path / "prior",),
    )

    assert config.prior_release_roots == (tmp_path / "prior",)
    with pytest.raises(ValueError):
        replace(config, real_root="not-a-path")


def test_aggregate_report_is_canonical_and_rejects_unsafe_metrics() -> None:
    policy = PrivacyPolicy.from_mapping(policy_mapping())
    controls = _passing_controls()
    report = PrivacyAuditReport(
        status="PASS",
        policy=policy,
        schema_fingerprint=policy.schema_fingerprint,
        synthetic_artifact_id="generated-v1",
        control_counts=_control_counts(controls),
        controls=controls,
        decision_reasons=("all_required_controls_passed",),
    )

    assert json.loads(report.canonical_json_bytes()) == report.to_mapping()
    assert report.canonical_json_bytes().endswith(b"\n")
    assert list(report.to_mapping()) == [
        "report_version", "status", "policy", "schema_fingerprint", "synthetic_artifact_id",
        "control_counts", "controls", "decision_reasons",
    ]
    assert PrivacyAuditResult(report).report is report
    with pytest.raises(ValueError, match="metric"):
        PrivacyControlResult("linkage", "PASS", {"patient_id": 1}, "safe")


def test_aggregate_report_rejects_missing_required_controls_and_inconsistent_status() -> None:
    policy = PrivacyPolicy.from_mapping(policy_mapping())
    controls = _passing_controls()
    report_inputs = {
        "policy": policy,
        "schema_fingerprint": policy.schema_fingerprint,
        "synthetic_artifact_id": "generated-v1",
        "decision_reasons": ("all_required_controls_passed",),
    }

    with pytest.raises(ValueError, match="required control coverage"):
        PrivacyAuditReport(
            status="PASS",
            control_counts=_control_counts(controls[1:]),
            controls=controls[1:],
            **report_inputs,
        )
    with pytest.raises(ValueError, match="status"):
        PrivacyAuditReport(
            status="FAIL",
            control_counts=_control_counts(controls),
            controls=controls,
            **report_inputs,
        )


def test_aggregate_report_derives_fail_and_unevaluable_from_controls() -> None:
    policy = PrivacyPolicy.from_mapping(policy_mapping())
    report_inputs = {
        "policy": policy,
        "schema_fingerprint": policy.schema_fingerprint,
        "synthetic_artifact_id": "generated-v1",
        "decision_reasons": ("review_required",),
    }
    required_unevaluable = (
        PrivacyControlResult("exact_reproduction", "UNEVALUABLE", {}, "insufficient_evidence"),
        _passing_controls()[1],
    )
    optional_failure = _passing_controls() + (
        PrivacyControlResult(
            "linkage", "FAIL", {"evaluated_count": 3, "linkage_advantage": 0.5}, "threshold_exceeded"
        ),
    )

    with pytest.raises(ValueError, match="status"):
        PrivacyAuditReport(
            status="PASS",
            control_counts=_control_counts(required_unevaluable),
            controls=required_unevaluable,
            **report_inputs,
        )
    with pytest.raises(ValueError, match="status"):
        PrivacyAuditReport(
            status="PASS",
            control_counts=_control_counts(optional_failure),
            controls=optional_failure,
            **report_inputs,
        )


@pytest.mark.parametrize(
    "metrics",
    [
        {"overlap_rate": 0.0},
        {"overlap_rate": 0.0, "evaluated_count": 2},
        {"overlap_rate": 0.0, "evaluated_count": True},
    ],
)
def test_aggregate_report_requires_policy_minimum_evidence_for_evaluated_controls(
    metrics: dict[str, object],
) -> None:
    policy = PrivacyPolicy.from_mapping(policy_mapping())
    if metrics.get("evaluated_count") is True:
        with pytest.raises(ValueError, match="numeric"):
            PrivacyControlResult("identifier_overlap", "PASS", metrics, "no_overlap")  # type: ignore[arg-type]
        return
    controls = (
        _passing_controls()[0],
        PrivacyControlResult("identifier_overlap", "PASS", metrics, "no_overlap"),
    )

    with pytest.raises(ValueError, match="evaluated_count"):
        PrivacyAuditReport(
            status="PASS",
            policy=policy,
            schema_fingerprint=policy.schema_fingerprint,
            synthetic_artifact_id="generated-v1",
            control_counts=_control_counts(controls),
            controls=controls,
            decision_reasons=("all_required_controls_passed",),
        )


def test_aggregate_report_canonicalizes_decision_reason_order_and_duplicates() -> None:
    policy = PrivacyPolicy.from_mapping(policy_mapping())
    controls = _passing_controls()
    shared = {
        "status": "PASS",
        "policy": policy,
        "schema_fingerprint": policy.schema_fingerprint,
        "synthetic_artifact_id": "generated-v1",
        "control_counts": _control_counts(controls),
        "controls": controls,
    }
    first = PrivacyAuditReport(decision_reasons=("z_reason", "a_reason", "z_reason"), **shared)
    second = PrivacyAuditReport(decision_reasons=("a_reason", "z_reason"), **shared)

    assert first.decision_reasons == ("a_reason", "z_reason")
    assert first.canonical_json_bytes() == second.canonical_json_bytes()

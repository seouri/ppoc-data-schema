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
    control = PrivacyControlResult(
        control_id="identifier_overlap",
        status="PASS",
        metrics={"overlap_rate": 0.0, "evaluated_count": 3},
        reason_code="no_overlap",
    )
    report = PrivacyAuditReport(
        status="PASS",
        policy=policy,
        schema_fingerprint=policy.schema_fingerprint,
        synthetic_artifact_id="generated-v1",
        control_counts={"PASS": 1, "FAIL": 0, "UNEVALUABLE": 0},
        controls=(control,),
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

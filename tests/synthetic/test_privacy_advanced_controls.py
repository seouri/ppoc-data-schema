"""Aggregate-only tests for bounded advanced privacy controls."""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType

import pytest

from synthetic.privacy_audit import (
    PrivacyPolicy,
    _evaluate_attribute_disclosure_control,
    _evaluate_composition_control,
    _evaluate_membership_inference_control,
    _evaluate_negative_control,
    _evaluate_positive_control,
    _load_private_package,
    _load_private_shadow_runs,
    _PrivatePackage,
    _PrivatePatientProfile,
    _PrivateShadowRun,
)
from tests.synthetic.privacy_fixtures import (
    policy_mapping,
    write_generated_package,
    write_real_package,
    write_shadow_manifest,
)


def _policy(**changes: object) -> PrivacyPolicy:
    required = [
        "attribute_disclosure",
        "composition",
        "exact_reproduction",
        "identifier_overlap",
        "membership_inference",
        "negative_control",
        "positive_control",
    ]
    return PrivacyPolicy.from_mapping(
        policy_mapping(**({"required_controls": required, "minimum_shadow_runs": 2} | changes))
    )


def _profile(label: str, diagnosis: str | None, *, copied: bool = False) -> _PrivatePatientProfile:
    del copied
    signature = f"trajectory-{label}"
    return _PrivatePatientProfile(
        _patient_id=f"private-{label}",
        _demographics=("F", f"demographics-{label}"),
        _ages=(100, 800, 3500),
        _visit_count=3,
        _trajectory=((100, 1.0, 1.0, 1.0),) * 3,
        _growth_dx_flag=diagnosis,
        _trajectory_signature=signature,
        _profile_signature=f"profile-{label}",
        _component_buckets=MappingProxyType(
            {
                "demographics": f"demographics-{label}",
                "timing": f"timing-{label}",
                "utilization": f"utilization-{label}",
                "trajectory": signature,
                "diagnosis": diagnosis,
            }
        ),
    )


def _package(*profiles: _PrivatePatientProfile) -> _PrivatePackage:
    return _PrivatePackage(
        patient_count=len(profiles),
        _identifier_values=frozenset(f"private-id-{index}" for index in range(len(profiles))),
        _profiles=profiles,
        _trajectory_signatures=frozenset(profile._trajectory_signature for profile in profiles),
        _profile_signatures=frozenset(profile._profile_signature for profile in profiles),
        _ineligible_profile_count=0,
    )


def test_shadow_manifest_is_strict_and_does_not_echo_private_members(tmp_path: Path) -> None:
    """Catches accepting unknown, duplicate, or unversioned shadow labels."""
    reference_root = write_real_package(tmp_path / "reference")
    shadow_root = write_generated_package(tmp_path / "shadow")
    reference = _load_private_package(
        reference_root, synthetic=False, longitudinal_minimum=3
    )
    manifest = write_shadow_manifest(
        tmp_path / "shadows.json",
        [{"run_id": "shadow-1", "package_root": str(shadow_root), "members": ["REAL-P-001"]}],
    )

    runs = _load_private_shadow_runs(manifest, reference, _policy(minimum_shadow_runs=1))

    assert len(runs) == 1
    assert "REAL-P-001" not in repr(runs)
    bad_manifest = tmp_path / "bad-shadows.json"
    bad_manifest.write_text(
        json.dumps({"version": "privacy-shadow-v1", "runs": [{"run_id": "shadow-1", "package_root": str(shadow_root), "members": ["unknown-private-member"]}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as error:
        _load_private_shadow_runs(bad_manifest, reference, _policy(minimum_shadow_runs=1))
    assert "unknown-private-member" not in str(error.value)


def test_membership_requires_all_shadow_runs_and_reports_only_maximum_aggregate_signal() -> None:
    """Catches treating one shadow or an individual label as sufficient membership evidence."""
    policy = _policy()
    reference = _package(
        _profile("one", "0"),
        _profile("two", "0"),
        _profile("three", "1"),
        _profile("four", "0"),
        _profile("five", "0"),
        _profile("six", "1"),
    )
    copied_one = _package(
        _profile("one", "0", copied=True),
        _profile("two", "0", copied=True),
        _profile("three", "1", copied=True),
    )
    copied_two = _package(
        _profile("four", "0", copied=True),
        _profile("five", "0", copied=True),
        _profile("six", "1", copied=True),
    )
    runs = (
        _PrivateShadowRun(
            "shadow-1", copied_one, frozenset({"trajectory-one", "trajectory-two", "trajectory-three"})
        ),
        _PrivateShadowRun(
            "shadow-2", copied_two, frozenset({"trajectory-four", "trajectory-five", "trajectory-six"})
        ),
    )

    result = _evaluate_membership_inference_control(policy, reference, runs)
    underpowered = _evaluate_membership_inference_control(policy, reference, runs[:1])

    assert result.status == "FAIL"
    assert result.metrics["membership_inference_advantage"] == 1.0
    assert result.metrics["shadow_run_count"] == 2
    assert 0 <= result.metrics["advantage_ci_lower"] <= result.metrics["advantage_ci_upper"] <= 1
    assert underpowered.status == "UNEVALUABLE"
    assert underpowered.metrics == {}
    assert "trajectory-one" not in repr(result)


def test_membership_suppresses_duplicate_runs_and_undersized_labels() -> None:
    """Catches treating duplicate shadows or too-small member/nonmember groups as privacy evidence."""
    policy = _policy()
    reference = _package(
        _profile("one", "0"), _profile("two", "0"), _profile("three", "1"),
        _profile("four", "0"), _profile("five", "0"), _profile("six", "1"),
    )
    shadow = _package(_profile("one", "0"), _profile("two", "0"), _profile("three", "1"))
    duplicate = _PrivateShadowRun(
        "same-run", shadow, frozenset({"trajectory-one", "trajectory-two", "trajectory-three"})
    )
    undersized = (
        _PrivateShadowRun("small-one", shadow, frozenset({"trajectory-one", "trajectory-two"})),
        _PrivateShadowRun("small-two", shadow, frozenset({"trajectory-one", "trajectory-two"})),
    )

    duplicate_result = _evaluate_membership_inference_control(policy, reference, (duplicate, duplicate))
    undersized_result = _evaluate_membership_inference_control(policy, reference, undersized)

    assert duplicate_result.status == "UNEVALUABLE"
    assert undersized_result.status == "UNEVALUABLE"
    assert duplicate_result.metrics == undersized_result.metrics == {}


def test_attribute_and_composition_controls_use_private_labels_and_explicit_prior_packages() -> None:
    """Catches reporting diagnosis values or passing a required control without its baseline/prior evidence."""
    policy = _policy(minimum_prior_releases=1)
    reference = _package(_profile("one", "0"), _profile("two", "0"), _profile("three", "1"))
    generated = _package(
        _profile("one", "0", copied=True), _profile("two", "0", copied=True), _profile("three", "1", copied=True)
    )
    heldout = _package(_profile("held-one", "0"), _profile("held-two", "0"), _profile("held-three", "1"))

    attribute = _evaluate_attribute_disclosure_control(policy, reference, generated, heldout=heldout)
    generated_without_diagnoses = _package(
        _profile("one", None, copied=True), _profile("two", None, copied=True), _profile("three", None, copied=True)
    )
    unchanged_attribute = _evaluate_attribute_disclosure_control(
        policy, reference, generated_without_diagnoses, heldout=heldout
    )
    composition = _evaluate_composition_control(policy, generated, (generated,))
    missing_prior = _evaluate_composition_control(policy, generated, ())

    assert attribute.status == "FAIL"
    assert attribute.metrics["attribute_disclosure_advantage"] > 0
    assert unchanged_attribute == attribute
    assert composition.status == "FAIL"
    assert composition.metrics["composition_reproduction_rate"] == 1.0
    assert missing_prior.status == "UNEVALUABLE"
    for result in (attribute, composition):
        assert "trajectory-one" not in repr(result)
        assert "diagnosis" not in repr(result).lower()


def test_negative_and_positive_controls_distinguish_independent_from_copied_packages() -> None:
    """Catches a harness that cannot detect copied leakage or treats a missing baseline as a failure."""
    policy = _policy()
    reference = _package(_profile("one", "0"), _profile("two", "0"), _profile("three", "1"))
    independent = _package(_profile("ind-one", "0"), _profile("ind-two", "0"), _profile("ind-three", "1"))
    copied = _package(
        _profile("one", "0", copied=True), _profile("two", "0", copied=True), _profile("three", "1", copied=True)
    )
    heldout = _package(_profile("held-one", "0"), _profile("held-two", "0"), _profile("held-three", "1"))

    negative = _evaluate_negative_control(policy, reference, independent, heldout=heldout)
    positive = _evaluate_positive_control(policy, reference, copied, heldout=heldout)
    missing = _evaluate_positive_control(policy, reference, None, heldout=heldout)

    assert negative.status == "PASS"
    assert positive.status == "PASS"
    assert positive.metrics["positive_control_advantage"] == 1.0
    assert missing.status == "UNEVALUABLE"
    assert "private-one" not in repr(positive)


def test_control_threshold_equality_is_conservative_for_negative_and_detects_positive() -> None:
    """Catches reversing either threshold's specified equality boundary."""
    thresholds = policy_mapping()["thresholds"]
    assert isinstance(thresholds, dict)
    policy = _policy(thresholds=thresholds | {"negative_control_advantage": 0, "positive_control_advantage": 1})
    reference = _package(_profile("one", "0"), _profile("two", "0"), _profile("three", "1"))
    independent = _package(_profile("ind-one", "0"), _profile("ind-two", "0"), _profile("ind-three", "1"))
    copied = _package(_profile("one", "0"), _profile("two", "0"), _profile("three", "1"))
    heldout = _package(_profile("held-one", "0"), _profile("held-two", "0"), _profile("held-three", "1"))

    negative = _evaluate_negative_control(policy, reference, independent, heldout=heldout)
    positive = _evaluate_positive_control(policy, reference, copied, heldout=heldout)

    assert negative.metrics["negative_control_advantage"] == 0
    assert negative.status == "FAIL"
    assert positive.metrics["positive_control_advantage"] == 1
    assert positive.status == "PASS"

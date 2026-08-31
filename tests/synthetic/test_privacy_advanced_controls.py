"""Aggregate-only tests for bounded advanced privacy controls."""

from __future__ import annotations

import json
import traceback
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import pytest

from synthetic.privacy_audit import (
    PrivacyPolicy,
    PrivacyRunConfig,
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
    audit_privacy,
)
from tests.synthetic.privacy_fixtures import (
    copy_growth_trajectory,
    exception_graph,
    offset_growth_trajectories,
    policy_mapping,
    retain_eligible_growth_profiles,
    set_first_growth_value,
    write_generated_package,
    write_policy,
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


@pytest.mark.parametrize(
    "failure", ["unknown_member", "missing_manifest", "missing_package", "bad_row"]
)
def test_shadow_manifest_failures_detach_private_exception_graph(
    tmp_path: Path, failure: str
) -> None:
    """Catches private member or path values surviving in chained loader exceptions."""
    reference = _load_private_package(
        write_real_package(tmp_path / "reference"), synthetic=False, longitudinal_minimum=3
    )
    shadow = write_generated_package(tmp_path / "shadow")
    sentinel = f"PRIVATE-{failure.upper()}-SENTINEL"
    if failure == "missing_manifest":
        manifest = tmp_path / sentinel / "shadows.json"
    else:
        if failure == "bad_row":
            set_first_growth_value(shadow, sentinel)
        manifest = write_shadow_manifest(
            tmp_path / "shadows.json",
            [
                {
                    "run_id": "shadow-one",
                    "package_root": str(tmp_path / sentinel) if failure == "missing_package" else str(shadow),
                    "members": [sentinel] if failure == "unknown_member" else ["REAL-P-001"],
                }
            ],
        )

    with pytest.raises(ValueError, match="^privacy shadow manifest is invalid$") as error:
        _load_private_shadow_runs(manifest, reference, _policy(minimum_shadow_runs=1))

    formatted = "".join(traceback.format_exception(error.value))
    graph = exception_graph(error.value)
    assert graph == (error.value,)
    assert sentinel not in formatted
    assert all(sentinel not in repr(item) for item in graph)


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
    assert result.metrics["membership_true_positive_rate"] == 1.0
    assert result.metrics["membership_false_positive_rate"] == 0.0
    assert result.metrics["membership_true_positive_count"] == 3
    assert result.metrics["membership_false_positive_count"] == 0
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


def test_membership_requires_shadow_profiles_and_unambiguous_reference_labels() -> None:
    """Catches empty shadows or signature collisions becoming membership evidence."""
    policy = _policy(minimum_shadow_runs=1)
    reference = _package(
        _profile("one", "0"), _profile("two", "0"), _profile("three", "1"),
        replace(_profile("four", "0"), _trajectory_signature="trajectory-one"),
        _profile("five", "0"), _profile("six", "1"), _profile("seven", "0"),
    )
    labels = frozenset({"trajectory-one", "trajectory-two", "trajectory-three"})
    empty = _PrivateShadowRun("empty", _package(), labels)
    underpowered = _PrivateShadowRun(
        "underpowered", _package(_profile("one", "0"), _profile("two", "0")), labels
    )
    ambiguous = _PrivateShadowRun(
        "ambiguous",
        _package(_profile("one", "0"), _profile("two", "0"), _profile("three", "1")),
        labels,
    )

    results = tuple(
        _evaluate_membership_inference_control(policy, reference, (run,))
        for run in (empty, underpowered, ambiguous)
    )

    assert all(result.status == "UNEVALUABLE" for result in results)
    assert all(result.metrics == {} for result in results)


def test_composition_does_not_count_the_same_private_package_twice() -> None:
    """Catches duplicate in-memory prior evidence satisfying the release minimum."""
    policy = _policy(minimum_prior_releases=2)
    generated = _package(_profile("one", "0"), _profile("two", "0"), _profile("three", "1"))

    result = _evaluate_composition_control(policy, generated, (generated, generated))

    assert result.status == "UNEVALUABLE"
    assert result.metrics == {}


@pytest.mark.parametrize("eligible_count", [0, 2])
def test_audit_rejects_empty_or_underpowered_shadow_package_evidence(
    tmp_path: Path, eligible_count: int
) -> None:
    """Catches an insufficient shadow artifact producing aggregate membership metrics."""
    thresholds = policy_mapping()["thresholds"]
    assert isinstance(thresholds, dict)
    reference = write_real_package(tmp_path / "reference")
    generated = offset_growth_trajectories(
        write_generated_package(tmp_path / "generated"), 100.0
    )
    shadow = retain_eligible_growth_profiles(
        write_generated_package(tmp_path / "shadow", id_prefix="SHD"),
        {f"SHD-P-{index:03d}" for index in range(1, eligible_count + 1)},
    )
    manifest = write_shadow_manifest(
        tmp_path / "shadows.json",
        [
            {
                "run_id": "shadow-one",
                "package_root": str(shadow),
                "members": ["REAL-P-001", "REAL-P-002", "REAL-P-003"],
            }
        ],
    )
    policy = write_policy(
        tmp_path / "policy.json",
        minimum_shadow_runs=1,
        required_controls=["exact_reproduction", "identifier_overlap", "membership_inference"],
        thresholds=thresholds | {"linkage_advantage": 1.0, "nearest_neighbor_unique_rate": 1.0},
    )

    result = audit_privacy(
        PrivacyRunConfig(reference, generated, policy, tmp_path / "output", shadow_manifest=manifest)
    )
    membership = next(
        control for control in result.report.controls if control.control_id == "membership_inference"
    )

    assert membership.status == "UNEVALUABLE"
    assert membership.metrics == {}
    assert result.report.status == "UNEVALUABLE"


def test_audit_rejects_ambiguous_shadow_membership_labels(tmp_path: Path) -> None:
    """Catches one member signature silently relabelling a nonmember reference patient."""
    thresholds = policy_mapping()["thresholds"]
    assert isinstance(thresholds, dict)
    reference = copy_growth_trajectory(
        write_real_package(tmp_path / "reference"), "REAL-P-001", "REAL-P-004"
    )
    generated = offset_growth_trajectories(
        write_generated_package(tmp_path / "generated"), 100.0
    )
    shadow = write_generated_package(tmp_path / "shadow", id_prefix="SHD")
    manifest = write_shadow_manifest(
        tmp_path / "shadows.json",
        [
            {
                "run_id": "shadow-one",
                "package_root": str(shadow),
                "members": ["REAL-P-001", "REAL-P-002", "REAL-P-003"],
            }
        ],
    )
    policy = write_policy(
        tmp_path / "policy.json",
        minimum_shadow_runs=1,
        required_controls=["exact_reproduction", "identifier_overlap", "membership_inference"],
        thresholds=thresholds | {"linkage_advantage": 1.0, "nearest_neighbor_unique_rate": 1.0},
    )

    result = audit_privacy(
        PrivacyRunConfig(reference, generated, policy, tmp_path / "output", shadow_manifest=manifest)
    )
    membership = next(
        control for control in result.report.controls if control.control_id == "membership_inference"
    )

    assert membership.status == "UNEVALUABLE"
    assert membership.metrics == {}
    assert result.report.status == "UNEVALUABLE"


def test_shadow_manifest_rejects_equivalent_package_roots(tmp_path: Path) -> None:
    """Catches a symlink alias counting one shadow package as two independent runs."""
    reference = _load_private_package(
        write_real_package(tmp_path / "reference"), synthetic=False, longitudinal_minimum=3
    )
    shadow = write_generated_package(tmp_path / "shadow")
    alias = tmp_path / "shadow-alias"
    alias.symlink_to(shadow, target_is_directory=True)
    manifest = write_shadow_manifest(
        tmp_path / "shadows.json",
        [
            {"run_id": "shadow-one", "package_root": str(shadow), "members": ["REAL-P-001"]},
            {"run_id": "shadow-two", "package_root": str(alias), "members": ["REAL-P-002"]},
        ],
    )

    with pytest.raises(ValueError, match="^privacy shadow manifest is invalid$"):
        _load_private_shadow_runs(manifest, reference, _policy())


@pytest.mark.parametrize("evidence", ["shadow", "prior"])
def test_repeated_evidence_roots_cannot_satisfy_required_privacy_controls(
    tmp_path: Path, evidence: str
) -> None:
    """Catches repeated roots promoting required shadow or prior-release controls."""
    thresholds = policy_mapping()["thresholds"]
    assert isinstance(thresholds, dict)
    reference = write_real_package(tmp_path / "reference")
    generated = offset_growth_trajectories(
        write_generated_package(tmp_path / "generated"), 100.0
    )
    required = ["exact_reproduction", "identifier_overlap"]
    config_changes: dict[str, object] = {}
    policy_changes: dict[str, object] = {
        "thresholds": thresholds | {"linkage_advantage": 1.0, "nearest_neighbor_unique_rate": 1.0}
    }
    if evidence == "shadow":
        package = write_generated_package(tmp_path / "shadow", id_prefix="SHD")
        config_changes["shadow_manifest"] = write_shadow_manifest(
            tmp_path / "shadows.json",
            [
                {
                    "run_id": "shadow-one",
                    "package_root": str(package),
                    "members": ["REAL-P-001", "REAL-P-002", "REAL-P-003"],
                },
                {
                    "run_id": "shadow-two",
                    "package_root": str(package),
                    "members": ["REAL-P-004", "REAL-P-005", "REAL-P-006"],
                },
            ],
        )
        required.append("membership_inference")
        policy_changes["minimum_shadow_runs"] = 2
        control_id = "membership_inference"
    else:
        package = offset_growth_trajectories(
            write_generated_package(tmp_path / "prior", id_prefix="PRIOR"), 200.0
        )
        config_changes["prior_release_roots"] = (package, package)
        required.append("composition")
        required.sort()
        policy_changes["minimum_prior_releases"] = 2
        control_id = "composition"
    policy_changes["required_controls"] = required
    policy = write_policy(tmp_path / "policy.json", **policy_changes)

    result = audit_privacy(
        PrivacyRunConfig(
            reference,
            generated,
            policy,
            tmp_path / "output",
            **config_changes,
        )
    )
    control = next(item for item in result.report.controls if item.control_id == control_id)

    assert control.status == "UNEVALUABLE"
    assert control.metrics == {}
    assert result.report.status == "UNEVALUABLE"


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

    assert attribute.status == "UNEVALUABLE"
    assert attribute.metrics == {}
    assert unchanged_attribute == attribute
    assert composition.status == "FAIL"
    assert composition.metrics["composition_reproduction_rate"] == 1.0
    assert missing_prior.status == "UNEVALUABLE"
    for result in (attribute, composition):
        assert "trajectory-one" not in repr(result)
        assert "diagnosis" not in repr(result).lower()


def test_attribute_attack_uses_non_target_features_and_not_generated_diagnosis() -> None:
    """Catches circularly predicting a linked reference label with that same reference label."""
    policy = _policy(
        required_controls=["exact_reproduction", "identifier_overlap"],
        attacker_knowledge=["demographics"],
    )
    reference = _package(
        _profile("a", "0"), _profile("b", "1"),
        replace(_profile("c", "1"), _trajectory_signature="trajectory-b"),
        _profile("d", "1"), _profile("e", "0"), _profile("f", "0"),
        _profile("g", "1"), _profile("h", "0"),
    )
    generated = _package(
        _profile("b", "0"), _profile("d", "0"), _profile("f", "1"), _profile("h", "1")
    )
    changed_generated_labels = _package(
        _profile("b", "1"), _profile("d", "1"), _profile("f", "0"), _profile("h", "0")
    )

    result = _evaluate_attribute_disclosure_control(policy, reference, generated, heldout=None)
    changed = _evaluate_attribute_disclosure_control(
        policy, reference, changed_generated_labels, heldout=None
    )

    assert result == changed
    assert result.metrics["attribute_attack_accuracy"] == 0.333333
    assert result.metrics["evaluated_count"] == 3
    assert result.metrics["attribute_attack_accuracy"] < 1.0
    assert "diagnosis" not in repr(result).lower()


def test_attribute_attack_is_unevaluable_without_non_target_attacker_knowledge() -> None:
    """Catches using diagnosis as an attribute-attack feature when policy selected no other knowledge."""
    policy = _policy(
        required_controls=["exact_reproduction", "identifier_overlap"],
        attacker_knowledge=["diagnosis"],
    )
    reference = _package(
        _profile("a", "0"), _profile("b", "1"), _profile("c", "1"),
        _profile("d", "1"), _profile("e", "0"), _profile("f", "0"),
    )
    generated = _package(_profile("b", "0"), _profile("d", "0"), _profile("f", "1"))

    result = _evaluate_attribute_disclosure_control(policy, reference, generated, heldout=None)

    assert result.status == "UNEVALUABLE"
    assert result.reason_code == "no_non_target_attacker_knowledge"
    assert result.metrics == {}


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
    independent_positive = _evaluate_positive_control(policy, reference, independent, heldout=heldout)
    positive = _evaluate_positive_control(policy, reference, copied, heldout=heldout)
    missing = _evaluate_positive_control(policy, reference, None, heldout=heldout)

    assert negative.status == "PASS"
    assert independent_positive.status == "FAIL"
    assert positive.status == "PASS"
    assert positive.metrics["positive_control_advantage"] == 1.0
    for result in (negative, independent_positive, positive):
        assert {
            "harness_unique_candidate_rate",
            "harness_permutation_unique_rate",
            "reproduction_rate",
        } <= set(result.metrics)
    assert missing.status == "UNEVALUABLE"
    assert "private-one" not in repr(positive)


def test_control_harness_heldout_baseline_cannot_reduce_its_advantage() -> None:
    """Catches a high held-out linkage rate masking a reference/permutation harness signal."""
    thresholds = policy_mapping()["thresholds"]
    assert isinstance(thresholds, dict)
    policy = _policy(
        attacker_knowledge=["demographics", "timing"],
        thresholds=thresholds
        | {"negative_control_advantage": 0.1, "positive_control_advantage": 0.1},
    )

    def profile(label: str, demographics: str, timing: str) -> _PrivatePatientProfile:
        base = _profile(label, "0")
        buckets = dict(base._component_buckets)
        buckets.update({"demographics": demographics, "timing": timing})
        return replace(
            base,
            _demographics=("F", demographics),
            _component_buckets=MappingProxyType(buckets),
        )

    feature_pairs = (("A", "one"), ("A", "two"), ("B", "three"), ("B", "one"))
    reference = _package(*(profile(f"reference-{index}", *pair) for index, pair in enumerate(feature_pairs)))
    control = _package(*(profile(f"control-{index}", *pair) for index, pair in enumerate(feature_pairs)))
    heldout = _package(*(profile(f"heldout-{index}", *pair) for index, pair in enumerate(feature_pairs)))

    negative = _evaluate_negative_control(policy, reference, control, heldout=heldout)
    positive = _evaluate_positive_control(policy, reference, control, heldout=heldout)

    assert negative.metrics["harness_heldout_unique_candidate_rate"] == 1.0
    assert negative.metrics["negative_control_advantage"] > 0.1
    assert negative.status == "FAIL"
    assert positive.status == "PASS"


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

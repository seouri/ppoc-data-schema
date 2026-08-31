from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from synthetic.privacy_audit import (
    PrivacyAuditResult,
    PrivacyRunConfig,
    _validate_evaluated_metrics,
    audit_privacy,
    write_privacy_report,
)
from synthetic.schema_contract import load_descriptor, resource_spec
from tests.synthetic.privacy_fixtures import (
    policy_mapping,
    write_generated_package,
    write_policy,
    write_real_package,
    write_shadow_manifest,
)


def _independent_generated(root: Path, *, id_prefix: str = "GEN") -> Path:
    package = write_generated_package(root, id_prefix=id_prefix)
    descriptor = load_descriptor(package / "datapackage.json")
    path = package / resource_spec(descriptor, "visits_augmented")["path"]
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        fields = tuple(rows[0])
    for row in rows:
        for field in ("height_cm", "weight_kg", "head_circ_cm"):
            if row[field]:
                row[field] = str(float(row[field]) + 100.0)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return package


def _config(tmp_path: Path, **changes: object) -> PrivacyRunConfig:
    thresholds = policy_mapping()["thresholds"]
    assert isinstance(thresholds, dict)
    values: dict[str, object] = {
        "real_root": write_real_package(tmp_path / "real", id_prefix="REAL"),
        "synthetic_root": _independent_generated(tmp_path / "generated", id_prefix="GEN"),
        "policy": write_policy(
            tmp_path / "policy.json",
            thresholds=thresholds
            | {"linkage_advantage": 1.0, "nearest_neighbor_unique_rate": 1.0},
        ),
        "output": tmp_path / "privacy-output",
    }
    values.update(changes)
    return PrivacyRunConfig(**values)  # type: ignore[arg-type]


def test_audit_passes_independent_package_and_records_optional_missing_controls(tmp_path: Path) -> None:
    """Catches omitting optional controls or blocking a policy that does not require them."""
    result = audit_privacy(_config(tmp_path))

    controls = {control.control_id: control for control in result.report.controls}
    assert [control.control_id for control in result.report.controls] == [
        "attribute_disclosure",
        "composition",
        "exact_reproduction",
        "identifier_overlap",
        "linkage",
        "membership_inference",
        "nearest_neighbor",
        "negative_control",
        "positive_control",
    ]
    assert result.report.status == "PASS"
    assert controls["identifier_overlap"].status == "PASS"
    assert controls["exact_reproduction"].status == "PASS"
    assert controls["membership_inference"].status == "UNEVALUABLE"
    assert controls["composition"].status == "UNEVALUABLE"
    serialized = result.report.canonical_json_bytes().decode("ascii")
    assert "REAL-P-001" not in serialized
    assert "GEN-P-001" not in serialized
    assert str(tmp_path) not in serialized


def test_privacy_report_rejects_a_removed_optional_control(tmp_path: Path) -> None:
    """Catches a forged report eliding an unevaluable optional fixed control."""
    result = audit_privacy(_config(tmp_path))
    controls = tuple(
        item for item in result.report.controls if item.control_id != "membership_inference"
    )
    counts = {name: sum(item.status == name for item in controls) for name in ("PASS", "FAIL", "UNEVALUABLE")}

    with pytest.raises(ValueError, match="every fixed control"):
        replace(result.report, controls=controls, control_counts=counts)


def test_optional_nearest_neighbor_screen_can_fail_without_heldout_evidence(tmp_path: Path) -> None:
    """Catches skipping an applicable optional screen merely because held-out input is absent."""
    thresholds = policy_mapping()["thresholds"]
    assert isinstance(thresholds, dict)
    policy = write_policy(
        tmp_path / "policy.json",
        thresholds=thresholds
        | {"linkage_advantage": 1.0, "nearest_neighbor_unique_rate": 0.1},
    )

    result = audit_privacy(_config(tmp_path / "audit", policy=policy))

    controls = {control.control_id: control for control in result.report.controls}
    assert result.report.status == "FAIL"
    assert controls["nearest_neighbor"].status == "FAIL"
    assert controls["nearest_neighbor"].reason_code == "unique_nearest_threshold_exceeded"


def test_audit_is_byte_deterministic_and_suppresses_undersized_subgroups(tmp_path: Path) -> None:
    """Catches stateful aggregate output or a subgroup cell becoming reportable below policy minimum."""
    thresholds = policy_mapping()["thresholds"]
    assert isinstance(thresholds, dict)
    policy = write_policy(
        tmp_path / "policy.json",
        minimum_evaluable_patients=5,
        required_controls=["exact_reproduction", "identifier_overlap", "linkage"],
        thresholds=thresholds | {"linkage_advantage": 1.0, "nearest_neighbor_unique_rate": 1.0},
    )
    config = _config(
        tmp_path / "audit",
        policy=policy,
        heldout_root=write_real_package(tmp_path / "heldout", id_prefix="HLD"),
    )

    first = audit_privacy(config)
    second = audit_privacy(config)

    assert first.report.canonical_json_bytes() == second.report.canonical_json_bytes()
    linkage = {control.control_id: control for control in first.report.controls}["linkage"]
    assert first.report.status == linkage.status == "UNEVALUABLE"
    assert linkage.reason_code == "insufficient_evidence"
    assert linkage.metrics == {}
    assert "sex" not in repr(linkage).lower()


def test_malformed_heldout_evidence_suppresses_dependent_control_packages(tmp_path: Path) -> None:
    """Catches negative/positive controls silently dropping an explicitly invalid held-out baseline."""
    config = _config(
        tmp_path,
        heldout_root=tmp_path / "not-a-heldout-package",
        negative_control_root=_independent_generated(tmp_path / "negative", id_prefix="NEG"),
        positive_control_root=write_generated_package(tmp_path / "positive", id_prefix="POS"),
    )

    result = audit_privacy(config)

    controls = {control.control_id: control for control in result.report.controls}
    assert controls["negative_control"].status == "UNEVALUABLE"
    assert controls["positive_control"].status == "UNEVALUABLE"


def test_overlapping_explicit_heldout_package_is_unevaluable_and_cannot_pass(tmp_path: Path) -> None:
    """Catches accepting the reference package itself as a patient-disjoint held-out baseline."""
    thresholds = policy_mapping()["thresholds"]
    assert isinstance(thresholds, dict)
    real_root = write_real_package(tmp_path / "real", id_prefix="REAL")
    policy = write_policy(
        tmp_path / "policy.json",
        required_controls=["exact_reproduction", "identifier_overlap", "nearest_neighbor"],
        thresholds=thresholds | {"nearest_neighbor_unique_rate": 1.0},
    )
    result = audit_privacy(
        PrivacyRunConfig(
            real_root=real_root,
            heldout_root=real_root,
            synthetic_root=_independent_generated(tmp_path / "generated"),
            policy=policy,
            output=tmp_path / "output",
        )
    )

    control = {item.control_id: item for item in result.report.controls}["nearest_neighbor"]
    assert result.report.status == "UNEVALUABLE"
    assert control.status == "UNEVALUABLE"
    assert control.reason_code == "heldout_not_patient_disjoint"


@pytest.mark.parametrize("optional", ["negative", "shadow"])
def test_malformed_optional_packages_never_abort_the_primary_audit(
    tmp_path: Path, optional: str
) -> None:
    """Catches a KeyError from a malformed optional descriptor becoming a hard audit failure."""
    package = write_generated_package(tmp_path / optional, id_prefix="OPT")
    descriptor = package / "datapackage.json"
    payload = json.loads(descriptor.read_text(encoding="utf-8"))
    payload["resources"][0].pop("schema")
    descriptor.write_text(json.dumps(payload), encoding="utf-8")
    kwargs: dict[str, object]
    if optional == "negative":
        kwargs = {"negative_control_root": package}
    else:
        manifest = write_shadow_manifest(
            tmp_path / "shadows.json",
            [{"run_id": "bad-shadow", "package_root": str(package), "members": ["REAL-P-001"]}],
        )
        kwargs = {"shadow_manifest": manifest}

    result = audit_privacy(_config(tmp_path / "audit", **kwargs))

    control_id = f"{optional}_control" if optional == "negative" else "membership_inference"
    control = {item.control_id: item for item in result.report.controls}[control_id]
    assert control.status == "UNEVALUABLE"
    if optional == "shadow":
        assert control.reason_code == "insufficient_shadow_runs"


@pytest.mark.parametrize("use_alias", [False, True])
def test_audit_rejects_one_package_serving_as_both_control_roles_without_leaking_identity(
    tmp_path: Path, use_alias: bool
) -> None:
    """Catches one filesystem identity satisfying both independent control roles."""
    package = _independent_generated(tmp_path / "shared-control", id_prefix="SHARED")
    positive_root = package
    if use_alias:
        positive_root = tmp_path / "shared-control-alias"
        positive_root.symlink_to(package, target_is_directory=True)

    with pytest.raises(ValueError) as error:
        audit_privacy(
            _config(
                tmp_path / "audit",
                negative_control_root=package,
                positive_control_root=positive_root,
            )
        )

    assert str(error.value) == "privacy audit inputs invalid"
    assert str(package) not in str(error.value)
    assert "SHARED-P-001" not in str(error.value)


def test_report_writer_rejects_forged_control_pass_metrics(tmp_path: Path) -> None:
    """Catches promoting caller-supplied PASS statuses that conflict with policy thresholds."""
    result = audit_privacy(_config(tmp_path))
    controls = tuple(
        replace(
            item,
            metrics={
                **item.metrics,
                "identifier_count": 1,
                "overlap_count": 1,
                "overlap_rate": 1.0,
                "rate_ci_lower": 1.0,
                "rate_ci_upper": 1.0,
            },
        )
        if item.control_id == "identifier_overlap"
        else item
        for item in result.report.controls
    )
    forged = PrivacyAuditResult(replace(result.report, controls=controls))

    with pytest.raises(ValueError, match="could not be promoted"):
        write_privacy_report(forged, tmp_path / "forged")


def test_report_writer_rejects_forged_linkage_advantage(tmp_path: Path) -> None:
    """Catches trusting a caller-supplied linkage advantage that conflicts with its rates."""
    result = audit_privacy(_config(tmp_path))
    controls = tuple(
        replace(
            item,
            metrics={
                **item.metrics,
                "unique_candidate_rate": 1.0,
                "permutation_unique_rate": 0.0,
                "linkage_advantage": 0.0,
            },
        )
        if item.control_id == "linkage"
        else item
        for item in result.report.controls
    )
    forged = PrivacyAuditResult(replace(result.report, controls=controls))

    with pytest.raises(ValueError, match="could not be promoted"):
        write_privacy_report(forged, tmp_path / "forged-linkage")


def test_report_writer_rejects_subgroup_linkage_reason_without_a_subgroup_cell(tmp_path: Path) -> None:
    """Catches a caller claiming an unreported subgroup caused an overall-only linkage failure."""
    thresholds = policy_mapping()["thresholds"]
    assert isinstance(thresholds, dict)
    policy = write_policy(
        tmp_path / "policy.json",
        subgroups=["overall"],
        thresholds=thresholds | {"linkage_advantage": 0.1, "nearest_neighbor_unique_rate": 1.0},
    )
    result = audit_privacy(_config(tmp_path, policy=policy))
    controls = tuple(
        replace(item, reason_code="subgroup_linkage_threshold_exceeded")
        if item.control_id == "linkage"
        else item
        for item in result.report.controls
    )
    forged = PrivacyAuditResult(replace(result.report, controls=controls))

    with pytest.raises(ValueError, match="could not be promoted"):
        write_privacy_report(forged, tmp_path / "forged-subgroup-linkage-reason")


def test_report_validation_rejects_incomplete_heldout_nearest_metrics(tmp_path: Path) -> None:
    """Catches an orphan held-out nearest rate from reducing a generated nearest-neighbor failure."""
    result = audit_privacy(_config(tmp_path))
    nearest = next(item for item in result.report.controls if item.control_id == "nearest_neighbor")
    forged = replace(
        nearest,
        metrics={
            **nearest.metrics,
            "heldout_count": nearest.metrics["evaluated_count"],
            "heldout_zero_proximity_rate": nearest.metrics["zero_proximity_rate"],
        },
    )

    with pytest.raises(ValueError, match="held-out metrics are incomplete"):
        _validate_evaluated_metrics(forged, result.report.policy)


@pytest.mark.parametrize(
    ("control_id", "denominator"),
    [
        ("attribute_disclosure", "heldout_count"),
        ("linkage", "heldout_count"),
        ("nearest_neighbor", "heldout_count"),
        ("positive_control", "harness_heldout_count"),
    ],
)
def test_report_validation_rejects_underpowered_heldout_rate_cells(
    tmp_path: Path, control_id: str, denominator: str
) -> None:
    """Catches an undersized held-out aggregate being promoted as evaluated evidence."""
    result = audit_privacy(
        _config(
            tmp_path / "audit",
            synthetic_root=write_generated_package(tmp_path / "copied", id_prefix="GEN"),
            heldout_root=write_real_package(tmp_path / "heldout", id_prefix="HLD"),
            positive_control_root=write_generated_package(
                tmp_path / "positive", id_prefix="POS"
            ),
        )
    )
    control = next(item for item in result.report.controls if item.control_id == control_id)
    assert control.status != "UNEVALUABLE"
    forged = replace(
        control,
        metrics={**control.metrics, denominator: result.report.policy.minimum_evaluable_patients - 1},
    )

    with pytest.raises(ValueError, match="held-out evidence is underpowered") as error:
        _validate_evaluated_metrics(forged, result.report.policy)

    assert str(result.report.policy.minimum_evaluable_patients - 1) not in str(error.value)


def test_report_writer_rejects_heldout_baseline_that_hides_raw_nearest_signal(tmp_path: Path) -> None:
    """Catches injecting a complete held-out baseline to turn a generated nearest-neighbor failure into PASS."""
    thresholds = policy_mapping()["thresholds"]
    assert isinstance(thresholds, dict)
    policy = write_policy(
        tmp_path / "policy.json",
        thresholds=thresholds
        | {"linkage_advantage": 1.0, "nearest_neighbor_unique_rate": 0.1},
    )
    result = audit_privacy(_config(tmp_path / "audit", policy=policy))
    nearest = next(item for item in result.report.controls if item.control_id == "nearest_neighbor")
    assert nearest.status == result.report.status == "FAIL"
    controls = tuple(
        replace(
            item,
            status="PASS",
            metrics={
                **item.metrics,
                "heldout_count": item.metrics["evaluated_count"],
                "heldout_zero_proximity_rate": item.metrics["zero_proximity_rate"],
                "heldout_unique_nearest_rate": item.metrics["unique_nearest_rate"],
            },
        )
        if item.control_id == "nearest_neighbor"
        else item
        for item in result.report.controls
    )
    forged = PrivacyAuditResult(
        replace(
            result.report,
            status="PASS",
            controls=controls,
            control_counts={name: sum(item.status == name for item in controls) for name in ("PASS", "FAIL", "UNEVALUABLE")},
            decision_reasons=("all_required_controls_passed",),
        )
    )

    with pytest.raises(ValueError, match="could not be promoted"):
        write_privacy_report(forged, tmp_path / "forged-heldout")


@pytest.mark.parametrize(
    ("control_id", "copied_trajectories"),
    [
        ("nearest_neighbor", False),
        ("linkage", False),
        ("attribute_disclosure", True),
    ],
)
def test_report_writer_rejects_required_heldout_dependent_pass_without_heldout_evidence(
    tmp_path: Path, control_id: str, copied_trajectories: bool
) -> None:
    """Catches policy promotion making a reference-only PASS satisfy a required control."""
    changes: dict[str, object] = {}
    if copied_trajectories:
        changes["synthetic_root"] = write_generated_package(
            tmp_path / "copied", id_prefix="GEN"
        )
    result = audit_privacy(_config(tmp_path / "audit", **changes))
    control = next(item for item in result.report.controls if item.control_id == control_id)
    assert control.status == "PASS"
    assert "heldout_count" not in control.metrics
    required_policy = replace(
        result.report.policy,
        required_controls=tuple(
            sorted(set(result.report.policy.required_controls) | {control_id})
        ),
    )
    forged = PrivacyAuditResult(replace(result.report, policy=required_policy))
    output = tmp_path / f"forged-required-{control_id}"

    with pytest.raises(ValueError, match="could not be promoted"):
        write_privacy_report(forged, output)

    assert not output.exists()


def test_report_writer_rejects_required_composition_pass_below_prior_release_minimum(
    tmp_path: Path,
) -> None:
    """Catches a required composition PASS supported by too few prior releases."""
    thresholds = policy_mapping()["thresholds"]
    assert isinstance(thresholds, dict)
    policy = write_policy(
        tmp_path / "policy.json",
        minimum_prior_releases=2,
        required_controls=["composition", "exact_reproduction", "identifier_overlap"],
        thresholds=thresholds
        | {
            "composition_reproduction_rate": 1.0,
            "linkage_advantage": 1.0,
            "nearest_neighbor_unique_rate": 1.0,
        },
    )
    result = audit_privacy(
        _config(
            tmp_path / "audit",
            policy=policy,
            prior_release_roots=(
                _independent_generated(tmp_path / "prior-one", id_prefix="PRIOR-A"),
                _independent_generated(tmp_path / "prior-two", id_prefix="PRIOR-B"),
            ),
        )
    )
    composition = next(
        item for item in result.report.controls if item.control_id == "composition"
    )
    assert composition.status == "PASS"
    assert composition.metrics["prior_release_count"] == 2
    controls = tuple(
        replace(item, metrics={**item.metrics, "prior_release_count": 1})
        if item.control_id == "composition"
        else item
        for item in result.report.controls
    )
    forged = PrivacyAuditResult(replace(result.report, controls=controls))
    output = tmp_path / "forged-composition-minimum"

    with pytest.raises(ValueError, match="could not be promoted"):
        write_privacy_report(forged, output)

    assert not output.exists()


@pytest.mark.parametrize(
    ("control_id", "metrics"),
    [
        (
            "identifier_overlap",
            {
                "identifier_count": 1,
                "overlap_count": 0,
                "overlap_rate": 0.0,
            },
        ),
        (
            "exact_reproduction",
            {
                "reproduction_count": 0,
                "exact_reproduction_rate": 0.0,
            },
        ),
    ],
)
def test_report_writer_rejects_forged_mandatory_wilson_interval(
    tmp_path: Path, control_id: str, metrics: dict[str, int | float]
) -> None:
    """Catches arbitrary Wilson endpoints on an otherwise passing mandatory aggregate."""
    result = audit_privacy(_config(tmp_path))
    controls = tuple(
        replace(
            item,
            metrics={
                **item.metrics,
                **metrics,
                "rate_ci_lower": 1.0,
                "rate_ci_upper": 1.0,
            },
        )
        if item.control_id == control_id
        else item
        for item in result.report.controls
    )
    forged = PrivacyAuditResult(replace(result.report, controls=controls))

    with pytest.raises(ValueError, match="could not be promoted"):
        write_privacy_report(forged, tmp_path / f"forged-{control_id}-interval")


def _replace_report_control(
    result: PrivacyAuditResult, control_id: str, *, status: str, metric_name: str, value: float
) -> PrivacyAuditResult:
    controls = tuple(
        replace(item, status=status, metrics={**item.metrics, metric_name: value})
        if item.control_id == control_id
        else item
        for item in result.report.controls
    )
    control_counts = {name: sum(item.status == name for item in controls) for name in ("PASS", "FAIL", "UNEVALUABLE")}
    return PrivacyAuditResult(
        replace(
            result.report,
            status="FAIL",
            controls=controls,
            control_counts=control_counts,
            decision_reasons=("evaluated_control_failed",),
        )
    )


def test_report_writer_rejects_forged_membership_advantage(tmp_path: Path) -> None:
    """Catches a forged membership advantage and failure status despite unchanged component rates."""
    shadow = _independent_generated(tmp_path / "shadow", id_prefix="SHD")
    manifest = write_shadow_manifest(
        tmp_path / "shadows.json",
        [{"run_id": "shadow-one", "package_root": str(shadow), "members": ["REAL-P-001", "REAL-P-002", "REAL-P-003"]}],
    )
    result = audit_privacy(_config(tmp_path, shadow_manifest=manifest))
    forged = _replace_report_control(
        result,
        "membership_inference",
        status="FAIL",
        metric_name="membership_inference_advantage",
        value=1.0,
    )

    with pytest.raises(ValueError, match="could not be promoted"):
        write_privacy_report(forged, tmp_path / "forged-membership")


def test_report_writer_rejects_forged_positive_control_advantage(tmp_path: Path) -> None:
    """Catches a forged control-harness advantage and status despite unchanged component rates."""
    result = audit_privacy(
        _config(
            tmp_path,
            positive_control_root=write_generated_package(tmp_path / "positive", id_prefix="POS"),
        )
    )
    forged = _replace_report_control(
        result,
        "positive_control",
        status="FAIL",
        metric_name="positive_control_advantage",
        value=0.0,
    )

    with pytest.raises(ValueError, match="could not be promoted"):
        write_privacy_report(forged, tmp_path / "forged-positive")


@pytest.mark.parametrize("field", ["undersized", "interval"])
def test_report_writer_rejects_forged_membership_evidence(tmp_path: Path, field: str) -> None:
    """Catches undersized membership partitions and arbitrary advantage intervals in a PASS report."""
    shadow = _independent_generated(tmp_path / "shadow", id_prefix="SHD")
    manifest = write_shadow_manifest(
        tmp_path / "shadows.json",
        [{"run_id": "shadow-one", "package_root": str(shadow), "members": ["REAL-P-001", "REAL-P-002", "REAL-P-003"]}],
    )
    result = audit_privacy(_config(tmp_path, shadow_manifest=manifest))
    metrics = {
        **next(item.metrics for item in result.report.controls if item.control_id == "membership_inference"),
        "membership_positive_count": 1,
        "membership_negative_count": 11,
        "shadow_run_count": 0,
    }
    if field == "interval":
        metrics |= {"advantage_ci_lower": 1.0, "advantage_ci_upper": 1.0}
    controls = tuple(
        replace(item, metrics=metrics) if item.control_id == "membership_inference" else item
        for item in result.report.controls
    )
    forged = PrivacyAuditResult(replace(result.report, controls=controls))

    with pytest.raises(ValueError, match="could not be promoted"):
        write_privacy_report(forged, tmp_path / f"forged-membership-{field}")


@pytest.mark.parametrize("forgery", ["decision", "control", "optional_unevaluable"])
def test_report_writer_rejects_forged_reasons(tmp_path: Path, forgery: str) -> None:
    """Catches caller-supplied decision or control reasons that do not match aggregate semantics."""
    result = audit_privacy(_config(tmp_path))
    if forgery == "decision":
        forged = PrivacyAuditResult(replace(result.report, decision_reasons=("evaluated_control_failed",)))
    elif forgery == "optional_unevaluable":
        controls = tuple(
            replace(item, status="UNEVALUABLE", metrics={}, reason_code="heldout_required")
            if item.control_id == "nearest_neighbor"
            else item
            for item in result.report.controls
        )
        forged = PrivacyAuditResult(
            replace(
                result.report,
                controls=controls,
                control_counts={name: sum(item.status == name for item in controls) for name in ("PASS", "FAIL", "UNEVALUABLE")},
            )
        )
    else:
        controls = tuple(
            replace(item, reason_code="forged_reason") if item.control_id == "identifier_overlap" else item
            for item in result.report.controls
        )
        forged = PrivacyAuditResult(replace(result.report, controls=controls))

    with pytest.raises(ValueError, match="could not be promoted"):
        write_privacy_report(forged, tmp_path / f"forged-reason-{forgery}")


def test_audit_copied_package_fails_mandatory_controls_and_promotes_only_aggregate_files(tmp_path: Path) -> None:
    """Catches a copied package escaping either mandatory global-fail gate."""
    real_root = write_real_package(tmp_path / "real", id_prefix="COPY")
    config = PrivacyRunConfig(
        real_root=real_root,
        synthetic_root=write_generated_package(tmp_path / "generated", id_prefix="COPY"),
        policy=write_policy(tmp_path / "policy.json"),
        output=tmp_path / "privacy-output",
    )

    result = audit_privacy(config)
    write_privacy_report(result, config.output)

    assert result.report.status == "FAIL"
    assert {control.control_id for control in result.report.controls if control.status == "FAIL"} >= {
        "identifier_overlap",
        "exact_reproduction",
    }
    assert sorted(path.name for path in config.output.iterdir()) == [
        "privacy-audit-report.json",
        "privacy-audit-summary.txt",
    ]
    assert (config.output / "privacy-audit-report.json").read_bytes() == result.report.canonical_json_bytes()


def test_audit_required_missing_or_malformed_optional_evidence_is_unevaluable_not_a_hard_failure(tmp_path: Path) -> None:
    """Catches treating missing required evidence as pass or aborting on optional package failures."""
    policy = write_policy(
        tmp_path / "policy.json",
        required_controls=["composition", "exact_reproduction", "identifier_overlap"],
        minimum_prior_releases=1,
        thresholds=policy_mapping()["thresholds"]
        | {"linkage_advantage": 1.0, "nearest_neighbor_unique_rate": 1.0},
    )
    required_missing = audit_privacy(_config(tmp_path / "required", policy=policy))
    assert required_missing.report.status == "UNEVALUABLE"

    optional_bad = audit_privacy(_config(tmp_path / "optional", negative_control_root=tmp_path / "not-a-package"))
    controls = {control.control_id: control for control in optional_bad.report.controls}
    assert optional_bad.report.status == "PASS"
    assert controls["negative_control"].status == "UNEVALUABLE"


@pytest.mark.parametrize("suffix", ["partial", "failed"])
def test_report_writer_refuses_lifecycle_collisions(tmp_path: Path, suffix: str) -> None:
    """Catches replacing a stale lifecycle path for the same artifact and policy."""
    config = _config(tmp_path)
    result = audit_privacy(config)
    identity = f"{result.report.synthetic_artifact_id}:{result.report.policy.policy_id}:{result.report.policy.policy_version}"
    lifecycle_id = hashlib.sha256(identity.encode("ascii")).hexdigest()
    (config.output.parent / f".{config.output.name}.{lifecycle_id}.{suffix}").mkdir()

    with pytest.raises(FileExistsError):
        write_privacy_report(result, config.output)


def test_report_writer_archives_a_fixed_redacted_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Catches promotion after output validation failure or leakage through the failure artifact."""
    config = _config(tmp_path)
    result = audit_privacy(config)
    import synthetic.privacy_audit as module

    monkeypatch.setattr(module, "_reparse_written_privacy_report", lambda *_args: (_ for _ in ()).throw(ValueError("REAL-P-001")))

    with pytest.raises(ValueError, match="could not be promoted"):
        write_privacy_report(result, config.output)

    lifecycle_id = hashlib.sha256(
        f"{result.report.synthetic_artifact_id}:{result.report.policy.policy_id}:{result.report.policy.policy_version}".encode("ascii")
    ).hexdigest()
    failure = config.output.parent / f".{config.output.name}.{lifecycle_id}.failed" / "failure.json"
    assert json.loads(failure.read_text(encoding="utf-8")) == {
        "status": "FAILED",
        "reason": "privacy output validation failed",
    }


def test_report_writer_archives_partial_write_failure_and_refuses_dangling_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catches leaking partial reports or resolving a dangling target symlink into a new target."""
    config = _config(tmp_path)
    result = audit_privacy(config)
    import synthetic.privacy_audit as module

    monkeypatch.setattr(module, "_write_exclusive_fsynced", lambda *_args: (_ for _ in ()).throw(OSError("GEN-P-001")))
    with pytest.raises(ValueError, match="could not be promoted") as failure:
        write_privacy_report(result, config.output)
    assert "GEN-P-001" not in str(failure.value)
    lifecycle_id = hashlib.sha256(
        f"{result.report.synthetic_artifact_id}:{result.report.policy.policy_id}:{result.report.policy.policy_version}".encode("ascii")
    ).hexdigest()
    assert sorted((config.output.parent / f".{config.output.name}.{lifecycle_id}.failed").iterdir()) == [
        config.output.parent / f".{config.output.name}.{lifecycle_id}.failed" / "failure.json"
    ]

    symlink_config = _config(tmp_path / "symlink")
    symlink_config.output.symlink_to("missing-privacy-output")
    with pytest.raises(FileExistsError) as collision:
        write_privacy_report(audit_privacy(symlink_config), symlink_config.output)
    assert "missing-privacy-output" not in str(collision.value)


def test_library_input_failures_are_redacted(tmp_path: Path) -> None:
    """Catches a governed root or raw identifier escaping a public library exception."""
    config = _config(tmp_path, real_root=tmp_path / "governed-REAL-P-001")

    with pytest.raises(ValueError) as error:
        audit_privacy(config)

    assert str(error.value) == "privacy audit inputs invalid"


def test_library_primary_descriptor_malformation_is_redacted(tmp_path: Path) -> None:
    """Catches a raw descriptor KeyError escaping the public audit input boundary."""
    config = _config(tmp_path)
    descriptor = config.real_root / "datapackage.json"
    payload = json.loads(descriptor.read_text(encoding="utf-8"))
    payload["resources"][0].pop("schema")
    descriptor.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError) as error:
        audit_privacy(config)

    assert str(error.value) == "privacy audit inputs invalid"
    assert "schema" not in str(error.value)
    assert str(config.real_root) not in str(error.value)

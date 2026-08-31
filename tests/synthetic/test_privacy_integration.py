from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from synthetic.privacy_audit import PrivacyRunConfig, audit_privacy, write_privacy_report
from synthetic.schema_contract import load_descriptor, resource_spec
from tests.synthetic.privacy_fixtures import (
    policy_mapping,
    write_generated_package,
    write_policy,
    write_real_package,
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
            thresholds=thresholds | {"nearest_neighbor_unique_rate": 1.0},
        ),
        "output": tmp_path / "privacy-output",
    }
    values.update(changes)
    return PrivacyRunConfig(**values)  # type: ignore[arg-type]


def test_audit_passes_independent_package_and_records_optional_missing_controls(tmp_path: Path) -> None:
    """Catches omitting optional controls or blocking a policy that does not require them."""
    result = audit_privacy(_config(tmp_path))

    controls = {control.control_id: control for control in result.report.controls}
    assert result.report.status == "PASS"
    assert controls["identifier_overlap"].status == "PASS"
    assert controls["exact_reproduction"].status == "PASS"
    assert controls["membership_inference"].status == "UNEVALUABLE"
    assert controls["composition"].status == "UNEVALUABLE"
    serialized = result.report.canonical_json_bytes().decode("ascii")
    assert "REAL-P-001" not in serialized
    assert "GEN-P-001" not in serialized
    assert str(tmp_path) not in serialized


def test_optional_nearest_neighbor_screen_can_fail_without_heldout_evidence(tmp_path: Path) -> None:
    """Catches skipping an applicable optional screen merely because held-out input is absent."""
    thresholds = policy_mapping()["thresholds"]
    assert isinstance(thresholds, dict)
    policy = write_policy(
        tmp_path / "policy.json",
        thresholds=thresholds | {"nearest_neighbor_unique_rate": 0.1},
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
    assert linkage.status == "PASS"
    assert linkage.metrics["evaluated_count"] == 12
    assert "sex" not in linkage.metrics


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
        thresholds=policy_mapping()["thresholds"] | {"nearest_neighbor_unique_rate": 1.0},
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

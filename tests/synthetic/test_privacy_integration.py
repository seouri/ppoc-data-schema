from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from synthetic.privacy_audit import PrivacyRunConfig, audit_privacy, write_privacy_report
from synthetic.schema_contract import load_descriptor, resource_spec
from tests.synthetic.privacy_fixtures import (
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
    values: dict[str, object] = {
        "real_root": write_real_package(tmp_path / "real", id_prefix="REAL"),
        "synthetic_root": _independent_generated(tmp_path / "generated", id_prefix="GEN"),
        "policy": write_policy(tmp_path / "policy.json"),
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

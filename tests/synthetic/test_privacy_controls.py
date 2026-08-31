from __future__ import annotations

import csv
from pathlib import Path

from synthetic.privacy_audit import (
    PrivacyPolicy,
    _evaluate_exact_reproduction_control,
    _evaluate_identifier_overlap_control,
    _evaluate_linkage_control,
    _evaluate_nearest_neighbor_control,
    _load_private_package,
)
from synthetic.schema_contract import load_descriptor, resource_spec
from tests.synthetic.calibration_fixtures import write_mock_snapshot, write_synthetic_descriptor
from tests.synthetic.privacy_fixtures import (
    policy_mapping,
    write_generated_package,
    write_real_package,
)


def _policy(**changes: object) -> PrivacyPolicy:
    return PrivacyPolicy.from_mapping(policy_mapping(**changes))


def _shift_trajectory(package: Path) -> None:
    """Make fixture trajectories independent without exposing them to a control result."""
    descriptor = load_descriptor(package / "datapackage.json")
    path = package / resource_spec(descriptor, "visits_augmented")["path"]
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        assert rows and rows[0]
        fields = tuple(rows[0])
    for row in rows:
        for name in ("height_cm", "weight_kg", "head_circ_cm"):
            if row[name]:
                row[name] = str(float(row[name]) + 100.0)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _package(
    root: Path,
    *,
    synthetic: bool,
    prefix: str,
    independent: bool = False,
    patient_count: int = 12,
):
    if synthetic and patient_count != 12:
        package = write_mock_snapshot(root, id_prefix=prefix, patient_count=patient_count)
        write_synthetic_descriptor(package)
    else:
        package = (
            write_generated_package(root, id_prefix=prefix)
            if synthetic
            else write_real_package(root, id_prefix=prefix)
        )
    if independent:
        _shift_trajectory(package)
    return _load_private_package(package, synthetic=synthetic, longitudinal_minimum=3)


def test_mandatory_controls_fail_for_copied_identifiers_and_eligible_trajectories(
    tmp_path: Path,
) -> None:
    """Catches removing either mandatory zero-overlap/reproduction gate."""
    policy = _policy()
    reference = _package(tmp_path / "real", synthetic=False, prefix="COPY")
    generated = _package(tmp_path / "generated", synthetic=True, prefix="COPY")

    identifier = _evaluate_identifier_overlap_control(policy, reference, generated)
    reproduction = _evaluate_exact_reproduction_control(policy, reference, generated)

    assert identifier.status == reproduction.status == "FAIL"
    assert identifier.reason_code == "identifier_overlap_detected"
    assert reproduction.reason_code == "exact_reproduction_detected"
    assert (
        identifier.metrics["overlap_rate"] == reproduction.metrics["exact_reproduction_rate"] == 1.0
    )
    for result in (identifier, reproduction):
        text = repr(result)
        assert "COPY-P-001" not in text
        assert "sha256" not in text.lower()


def test_mandatory_controls_are_unevaluable_for_underpowered_evidence(tmp_path: Path) -> None:
    """Catches treating too few patients or trajectories as passing privacy evidence."""
    policy = _policy(minimum_evaluable_patients=13)
    reference = _package(tmp_path / "real", synthetic=False, prefix="REAL")
    generated = _package(tmp_path / "generated", synthetic=True, prefix="GEN", independent=True)

    identifier = _evaluate_identifier_overlap_control(policy, reference, generated)
    reproduction = _evaluate_exact_reproduction_control(policy, reference, generated)

    assert identifier.status == reproduction.status == "UNEVALUABLE"
    assert identifier.metrics == reproduction.metrics == {}
    assert identifier.reason_code == reproduction.reason_code == "insufficient_evidence"


def test_nearest_neighbor_requires_heldout_and_returns_only_aggregate_metrics(
    tmp_path: Path,
) -> None:
    """Catches accepting a required screen without its held-out comparison."""
    thresholds = policy_mapping()["thresholds"]
    assert isinstance(thresholds, dict)
    policy = _policy(
        required_controls=["exact_reproduction", "identifier_overlap", "nearest_neighbor"],
        thresholds=thresholds | {"nearest_neighbor_unique_rate": 1.0},
    )
    reference = _package(tmp_path / "real", synthetic=False, prefix="REAL")
    generated = _package(tmp_path / "generated", synthetic=True, prefix="GEN", independent=True)
    heldout = _package(tmp_path / "heldout", synthetic=False, prefix="HLD", independent=True)

    missing = _evaluate_nearest_neighbor_control(policy, reference, generated, heldout=None)
    first = _evaluate_nearest_neighbor_control(policy, reference, generated, heldout=heldout)
    second = _evaluate_nearest_neighbor_control(policy, reference, generated, heldout=heldout)

    assert missing.status == "UNEVALUABLE"
    assert missing.reason_code == "heldout_required"
    assert first == second
    assert first.status == "PASS"
    assert set(first.metrics) == {
        "evaluated_count",
        "heldout_count",
        "heldout_unique_nearest_rate",
        "heldout_zero_proximity_rate",
        "margin_positive_rate",
        "margin_zero_rate",
        "rate_ci_lower",
        "rate_ci_upper",
        "unique_nearest_rate",
        "zero_proximity_rate",
    }
    assert 0 <= first.metrics["rate_ci_lower"] <= first.metrics["zero_proximity_rate"] <= 1
    assert "REAL-P-001" not in repr(first)
    assert "distance" not in repr(first).lower()


def test_linkage_uses_fixed_components_and_heldout_permutation_baselines(tmp_path: Path) -> None:
    """Catches omitting held-out/permutation baselines or leaking component values."""
    policy = _policy(required_controls=["exact_reproduction", "identifier_overlap", "linkage"])
    reference = _package(tmp_path / "real", synthetic=False, prefix="REAL")
    generated = _package(tmp_path / "generated", synthetic=True, prefix="GEN", independent=True)
    heldout = _package(tmp_path / "heldout", synthetic=False, prefix="HLD", independent=True)

    missing = _evaluate_linkage_control(policy, reference, generated, heldout=None)
    first = _evaluate_linkage_control(policy, reference, generated, heldout=heldout)
    second = _evaluate_linkage_control(policy, reference, generated, heldout=heldout)

    assert missing.status == "UNEVALUABLE"
    assert missing.reason_code == "heldout_required"
    assert first == second
    assert first.status == "PASS"
    assert set(first.metrics) == {
        "evaluated_count",
        "heldout_count",
        "linkage_advantage",
        "permutation_unique_rate",
        "rate_ci_lower",
        "rate_ci_upper",
        "unique_candidate_rate",
    }
    assert first.metrics["linkage_advantage"] == 0.0
    assert "demographics" not in repr(first)
    assert "REAL-P-001" not in repr(first)


def test_linkage_suppresses_underpowered_sex_cells_without_turning_them_into_passes(
    tmp_path: Path,
) -> None:
    """Catches treating an undersized subgroup as evaluated evidence or exposing its category."""
    policy = _policy(required_controls=["exact_reproduction", "identifier_overlap", "linkage"])
    reference = _package(tmp_path / "real", synthetic=False, prefix="REAL")
    generated = _package(
        tmp_path / "generated", synthetic=True, prefix="GEN", independent=True, patient_count=4
    )
    heldout = _package(tmp_path / "heldout", synthetic=False, prefix="HLD", independent=True)

    result = _evaluate_linkage_control(policy, reference, generated, heldout=heldout)

    assert result.status == "PASS"
    assert result.metrics["evaluated_count"] == 4
    assert "sex" not in repr(result).lower()

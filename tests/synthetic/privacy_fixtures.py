"""Fictional inputs for privacy-audit contract tests."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from synthetic.schema_contract import load_descriptor, resource_spec, schema_fingerprint
from tests.synthetic.calibration_fixtures import write_mock_snapshot, write_synthetic_descriptor

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def exception_graph(error: BaseException) -> tuple[BaseException, ...]:
    """Return the recursively reachable cause and context graph for an error."""
    found: list[BaseException] = []
    pending = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        found.append(current)
        for linked in (current.__cause__, current.__context__):
            if linked is not None:
                pending.append(linked)
    return tuple(found)


def policy_mapping(**changes: object) -> dict[str, Any]:
    fingerprint = schema_fingerprint(load_descriptor(REPOSITORY_ROOT / "datapackage.json"))
    value: dict[str, Any] = {
        "policy_id": "privacy-policy-v1",
        "policy_version": "1",
        "schema_fingerprint": fingerprint,
        "recipient_class": "research-partner",
        "release_context": "offline-review",
        "accounting_unit": "patient",
        "attacker_knowledge": ["demographics", "diagnosis", "timing", "trajectory", "utilization"],
        "confidence_method": "wilson_95",
        "minimum_evaluable_patients": 3,
        "longitudinal_min_observations": 3,
        "required_controls": ["exact_reproduction", "identifier_overlap"],
        "subgroups": ["overall", "sex"],
        "minimum_shadow_runs": 0,
        "minimum_prior_releases": 0,
        "review_date": "2026-08-31",
        "approver": "privacy-reviewer",
        "thresholds": {
            "identifier_overlap_rate": 0,
            "exact_reproduction_rate": 0,
            "nearest_neighbor_zero_rate": 0.1,
            "nearest_neighbor_unique_rate": 0.1,
            "linkage_advantage": 0.1,
            "membership_inference_advantage": 0.1,
            "attribute_disclosure_advantage": 0.1,
            "composition_reproduction_rate": 0,
            "negative_control_advantage": 0.1,
            "positive_control_advantage": 0.1,
        },
    }
    value.update(changes)
    return value


def write_policy(path: Path, **changes: object) -> Path:
    path.write_text(json.dumps(policy_mapping(**changes)), encoding="utf-8")
    return path


def write_real_package(root: Path, *, id_prefix: str = "REAL") -> Path:
    package = write_mock_snapshot(root, id_prefix=id_prefix)
    descriptor = load_descriptor(REPOSITORY_ROOT / "datapackage.json")
    (package / "datapackage.json").write_text(json.dumps(descriptor), encoding="utf-8")
    return package


def write_generated_package(root: Path, *, id_prefix: str = "GEN") -> Path:
    package = write_mock_snapshot(root, id_prefix=id_prefix)
    write_synthetic_descriptor(package)
    return package


def write_shadow_manifest(path: Path, runs: list[dict[str, object]]) -> Path:
    """Write a fictional test-only privacy-shadow-v1 manifest."""
    path.write_text(
        json.dumps({"version": "privacy-shadow-v1", "runs": runs}), encoding="utf-8"
    )
    return path


def retain_eligible_growth_profiles(root: Path, patient_ids: set[str]) -> Path:
    """Blank growth observations outside a fictional eligible-patient set."""
    descriptor = load_descriptor(root / "datapackage.json")
    path = root / resource_spec(descriptor, "visits_augmented")["path"]
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        fields = tuple(rows[0])
    for row in rows:
        if row["patient_id"] not in patient_ids:
            for field in ("height_cm", "weight_kg", "head_circ_cm"):
                row[field] = ""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return root


def offset_growth_trajectories(root: Path, amount: float) -> Path:
    """Offset fictional measurements so a package is trajectory-independent."""
    descriptor = load_descriptor(root / "datapackage.json")
    path = root / resource_spec(descriptor, "visits_augmented")["path"]
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        fields = tuple(rows[0])
    for row in rows:
        for field in ("height_cm", "weight_kg", "head_circ_cm"):
            if row[field]:
                row[field] = str(float(row[field]) + amount)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return root


def set_first_growth_value(root: Path, value: str) -> Path:
    """Set one fictional growth value for private-error redaction tests."""
    descriptor = load_descriptor(root / "datapackage.json")
    path = root / resource_spec(descriptor, "visits_augmented")["path"]
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        fields = tuple(rows[0])
    rows[0]["height_cm"] = value
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return root


def copy_growth_trajectory(root: Path, source_patient: str, target_patient: str) -> Path:
    """Copy one fictional patient's growth measurements onto another patient."""
    descriptor = load_descriptor(root / "datapackage.json")
    path = root / resource_spec(descriptor, "visits_augmented")["path"]
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        fields = tuple(rows[0])
    measurements = {
        row["age_in_days"]: tuple(row[field] for field in ("height_cm", "weight_kg", "head_circ_cm"))
        for row in rows
        if row["patient_id"] == source_patient
    }
    if not measurements:
        raise ValueError("fictional source trajectory is missing")
    copied = 0
    for row in rows:
        if row["patient_id"] != target_patient:
            continue
        values = measurements.get(row["age_in_days"])
        if values is None:
            raise ValueError("fictional trajectory ages do not align")
        for field, value in zip(("height_cm", "weight_kg", "head_circ_cm"), values, strict=True):
            row[field] = value
        copied += 1
    if copied == 0:
        raise ValueError("fictional target trajectory is missing")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return root

"""Fictional inputs for privacy-audit contract tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from synthetic.schema_contract import load_descriptor, schema_fingerprint
from tests.synthetic.calibration_fixtures import write_mock_snapshot, write_synthetic_descriptor

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


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

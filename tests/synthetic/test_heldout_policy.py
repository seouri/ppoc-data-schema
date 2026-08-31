from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from synthetic.calibration_targets import TARGET_REGISTRY_VERSION
from synthetic.heldout_validate import FidelityPolicy, load_fidelity_policy


def valid_policy_mapping(**changes: object) -> dict[str, object]:
    policy: dict[str, object] = {
        "policy_id": "fidelity-v1",
        "policy_version": "1",
        "target_registry_version": TARGET_REGISTRY_VERSION,
        "minimum_evaluable_support": 2,
        "proportion_floor": 0.05,
        "proportion_z_score": 2.0,
        "continuous_tolerances": {
            "demographics": 0.05,
            "observation": 0.10,
            "physiology": 1.0,
            "utilization": 10.0,
            "recorded_outcome": 0.05,
        },
        "count_abs_tolerance": 1,
        "required_families": [
            "demographics",
            "observation",
            "physiology",
            "utilization",
            "recorded_outcome",
        ],
        "max_unevaluable_targets": 0,
    }
    policy.update(changes)
    return policy


def write_policy(path: Path, policy: object) -> Path:
    path.write_text(json.dumps(policy), encoding="utf-8")
    return path


def test_load_fidelity_policy_parses_exact_frozen_mapping(tmp_path: Path) -> None:
    policy = load_fidelity_policy(write_policy(tmp_path / "policy.json", valid_policy_mapping()))

    assert policy.policy_id == "fidelity-v1"
    assert policy.target_registry_version == TARGET_REGISTRY_VERSION
    assert policy.required_families == (
        "demographics",
        "observation",
        "physiology",
        "utilization",
        "recorded_outcome",
    )
    with pytest.raises(FrozenInstanceError):
        policy.policy_id = "other"  # type: ignore[misc]
    with pytest.raises(TypeError):
        policy.continuous_tolerances["physiology"] = 2.0  # type: ignore[index]


@pytest.mark.parametrize(
    "payload",
    [
        '{"policy_id":"fidelity-v1","policy_id":"other"}',
        json.dumps({**valid_policy_mapping(), "unknown": 1}),
        json.dumps({key: value for key, value in valid_policy_mapping().items() if key != "policy_id"}),
        json.dumps({**valid_policy_mapping(), "proportion_floor": float("nan")}),
    ],
)
def test_load_fidelity_policy_rejects_duplicate_unknown_missing_and_nonfinite_json(
    tmp_path: Path, payload: str
) -> None:
    path = tmp_path / "policy.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError):
        load_fidelity_policy(path)


@pytest.mark.parametrize(
    "changes",
    [
        {"policy_id": "patient-policy"},
        {"policy_version": "key-2026"},
        {"target_registry_version": "registry/path"},
        {"target_registry_version": "calibration-targets-v2"},
        {"minimum_evaluable_support": True},
        {"minimum_evaluable_support": 0},
        {"proportion_floor": True},
        {"proportion_floor": -0.01},
        {"proportion_floor": 1.01},
        {"proportion_z_score": 0.0},
        {"count_abs_tolerance": True},
        {"count_abs_tolerance": -1},
        {"max_unevaluable_targets": True},
        {"max_unevaluable_targets": -1},
        {"continuous_tolerances": {"physiology": 1.0}},
        {"continuous_tolerances": {**valid_policy_mapping()["continuous_tolerances"], "other": 1.0}},
        {"continuous_tolerances": {**valid_policy_mapping()["continuous_tolerances"], "physiology": -0.1}},
        {"required_families": ["demographics", "demographics"]},
        {"required_families": ["demographics", "unknown"]},
        {"required_families": ["utilization", "demographics"]},
    ],
)
def test_fidelity_policy_rejects_unsafe_or_invalid_values(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        FidelityPolicy(**valid_policy_mapping(**changes))  # type: ignore[arg-type]


def test_load_fidelity_policy_rejects_symlink_and_oversized_input(tmp_path: Path) -> None:
    target = write_policy(tmp_path / "target.json", valid_policy_mapping())
    link = tmp_path / "policy.json"
    link.symlink_to(target.name)
    with pytest.raises(ValueError):
        load_fidelity_policy(link)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (1024 * 1024 + 1))
    with pytest.raises(ValueError):
        load_fidelity_policy(oversized)

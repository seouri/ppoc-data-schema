from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "scripts" / "synthea" / "overlay"
MODULE = OVERLAY / "modules" / "ppoc_growth_disorder.json"


def _module() -> dict[str, object]:
    return json.loads(MODULE.read_text(encoding="utf-8"))


def test_versioned_module_has_the_fixed_fictional_transition_contract() -> None:
    module = _module()
    assert module["name"] == "PPOC Growth Hormone Deficiency"
    states = module["states"]
    assert isinstance(states, dict)
    assert set(states) == {
        "Initial",
        "GHD probability",
        "GHD delay",
        "GHD condition",
        "GHD evaluation",
        "IGF-1",
        "IGFBP-3",
        "End encounter",
        "Terminal",
    }
    branch = states["GHD probability"]
    assert isinstance(branch, dict)
    distributions = branch["distributed_transition"]
    assert distributions == [
        {"distribution": 0.143291, "transition": "GHD delay"},
        {"distribution": 0.856709, "transition": "Terminal"},
    ]
    condition = states["GHD condition"]
    assert isinstance(condition, dict)
    assert condition["type"] == "ConditionOnset"
    assert condition["assign_to_attribute"] == "ppoc_ghd"
    assert condition["codes"] == [
        {
            "system": "ICD10CM",
            "code": "E23.0",
            "display": "Fictional growth hormone deficiency",
        }
    ]
    for state_name in ("IGF-1", "IGFBP-3"):
        state = states[state_name]
        assert isinstance(state, dict)
        assert state["type"] == "Observation"
        assert state["category"] == "laboratory"
        assert state["codes"][0]["system"] == "LOINC"


def test_overlay_is_self_contained_and_has_a_stable_digest() -> None:
    assert (OVERLAY / "README.md").is_file()
    files = sorted(path for path in OVERLAY.rglob("*") if path.is_file())
    assert [path.relative_to(OVERLAY).as_posix() for path in files] == [
        "README.md",
        "modules/ppoc_growth_disorder.json",
    ]
    payload = b"".join(
        path.relative_to(OVERLAY).as_posix().encode("utf-8")
        + b"\0"
        + path.read_bytes()
        + b"\0"
        for path in files
    )
    assert hashlib.sha256(payload).hexdigest() == (
        "0b7ba5505213a7b7f7cdc05c233f5256ce893dca1f48a7183c948e95f8cb27b0"
    )


def test_overlay_docs_are_fictional_and_development_only() -> None:
    text = (OVERLAY / "README.md").read_text(encoding="utf-8").lower()
    for phrase in ("fictional", "development-only", "synthea", "e23.0", "not clinical"):
        assert phrase in text
    assert "http://" not in text
    assert "https://" not in text

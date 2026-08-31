from __future__ import annotations

import ast
import inspect
from pathlib import Path

from synthetic.models import PatientState
from synthetic.native.counterfactual import (
    InterventionKind,
    generate_counterfactual_pair,
    validate_counterfactual_pair,
    write_truth_manifest,
)
from tests.synthetic.test_counterfactual_validation import _familial_kernel

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_MODULES = {
    "synthetic.calibrate",
    "synthetic.calibration",
    "synthetic.calibration_input",
    "synthetic.heldout_validate",
    "synthetic.privacy_audit",
}
FORBIDDEN_ARGUMENTS = {
    "real_root",
    "data_root",
    "partition_key",
    "heldout_report",
    "privacy_report",
    "calibration_artifact",
}


def test_counterfactual_module_has_no_governed_input_imports() -> None:
    source = ROOT / "src" / "synthetic" / "native" / "counterfactual.py"
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    assert not imports & FORBIDDEN_MODULES


def test_counterfactual_api_has_no_real_data_or_governed_report_arguments() -> None:
    for function in (
        generate_counterfactual_pair,
        validate_counterfactual_pair,
        write_truth_manifest,
    ):
        assert not (set(inspect.signature(function).parameters) & FORBIDDEN_ARGUMENTS)


def test_ordinary_pair_and_report_mappings_exclude_hidden_truth() -> None:
    pair = generate_counterfactual_pair(
        _familial_kernel(),
        PatientState("syn-counterfactual-boundary", "F", "F"),
        (0, 365, 730, 1460, 1825, 2190, 4000),
        20260831,
        10,
        InterventionKind.EARLIER_RECOGNITION,
    )
    report = validate_counterfactual_pair(pair)

    ordinary = str(pair.to_mapping()) + str(report.to_mapping()) + repr(pair) + repr(report)
    assert "patient_id" not in ordinary
    assert "run_seed" not in ordinary
    assert "patient_index" not in ordinary
    assert "event_trace" not in ordinary
    assert "layer_sha256" not in ordinary
    assert "stream_identities" not in ordinary


def test_visible_manifest_module_does_not_import_counterfactual_truth() -> None:
    source = ROOT / "src" / "synthetic" / "manifest.py"
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "synthetic.native.counterfactual" not in imports

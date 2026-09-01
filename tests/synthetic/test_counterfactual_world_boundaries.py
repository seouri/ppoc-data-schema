from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

from synthetic.native.counterfactual import InterventionKind
from synthetic.native.counterfactual_worlds import (
    CounterfactualWorldValidationStatus,
    assemble_counterfactual_ehr_worlds,
    validate_counterfactual_ehr_worlds,
)
from synthetic.native.resources import SyntheticDemographics
from tests.synthetic.test_counterfactual_world_assembly import (
    PATIENT,
    _ancillary_policy,
    _descriptor,
    _pair,
    _policy,
)


def _worlds():
    return assemble_counterfactual_ehr_worlds(
        _pair(InterventionKind.PHYSIOLOGY_SEVERITY),
        SyntheticDemographics(PATIENT.patient_id, "F"),
        _policy(),
        _descriptor(),
        _ancillary_policy(),
    )


def _mapping_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(_mapping_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_mapping_keys(item) for item in value)) if value else set()
    return set()


def test_world_validator_public_outputs_are_aggregate_only_and_do_not_expose_private_bindings() -> None:
    worlds = _worlds()
    report = validate_counterfactual_ehr_worlds(worlds)

    rendered = json.dumps(worlds.to_mapping(), sort_keys=True) + repr(worlds)
    aggregate_rendered = json.dumps(report.to_mapping(), sort_keys=True) + repr(report)

    assert report.status is CounterfactualWorldValidationStatus.PASS
    assert worlds._pair.baseline_context.patient.patient_id not in aggregate_rendered
    assert "ObservationTruth" not in rendered
    assert not _mapping_keys(worlds.to_mapping()) & {
        "truth",
        "trajectory",
        "run_seed",
        "patient_index",
        "stream_identity",
        "source_frame",
    }
    assert set(report.to_mapping()) == {"status", "check_counts", "checks"}


def test_world_validator_module_remains_in_memory_and_uses_no_forbidden_public_inputs() -> None:
    module = inspect.getmodule(validate_counterfactual_ehr_worlds)
    assert module is not None and module.__file__ is not None
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    forbidden_import_fragments = (
        "pathlib",
        "os",
        "csv",
        "package",
        "export",
        "manifest",
        "calibration",
        "heldout",
        "privacy",
        "governed",
        "duckdb",
        "synthea",
        "network",
    )
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name.lower() for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module.lower())
    assert not any(fragment in imported for imported in imports for fragment in forbidden_import_fragments)

    forbidden_arguments = {"path", "output", "root", "key", "real_data", "calibration", "heldout", "privacy", "model", "callable", "manifest"}
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and not node.name.startswith("_"):
            arguments = node.args if isinstance(node, ast.FunctionDef) else None
            if arguments is not None:
                names = {argument.arg for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)}
                assert not names & forbidden_arguments

    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not calls & {"open", "print", "input", "eval", "exec", "__import__"}

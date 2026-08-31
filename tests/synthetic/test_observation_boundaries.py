from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from synthetic.native.counterfactual import InterventionKind
from synthetic.native.observations import (
    generate_observation_frame,
    validate_observation_frame,
)

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


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_observation_module_has_no_governed_input_imports() -> None:
    source = ROOT / "src" / "synthetic" / "native" / "observations.py"
    assert not _imports(source) & FORBIDDEN_MODULES


def test_observation_api_has_no_real_or_governed_arguments() -> None:
    for function in (generate_observation_frame, validate_observation_frame):
        assert not (set(inspect.signature(function).parameters) & FORBIDDEN_ARGUMENTS)


def test_observation_module_does_not_touch_visible_schema_or_cli() -> None:
    source = (ROOT / "src" / "synthetic" / "native" / "observations.py").read_text(
        encoding="utf-8"
    )
    assert "datapackage.json" not in source
    assert "generate.py" not in source
    assert "Path(" not in source
    assert "open(" not in source
    assert "read_csv" not in source


@pytest.mark.parametrize(
    "intervention",
    [InterventionKind.UTILIZATION_INTENSITY, InterventionKind.MEASUREMENT_ERROR_REMOVAL],
)
def test_deferred_counterfactual_interventions_remain_explicitly_rejected(
    intervention: InterventionKind,
) -> None:
    source = (ROOT / "src" / "synthetic" / "native" / "observations.py").read_text(
        encoding="utf-8"
    )

    assert intervention.value in {
        InterventionKind.UTILIZATION_INTENSITY.value,
        InterventionKind.MEASUREMENT_ERROR_REMOVAL.value,
    }
    assert "measurement-error" in source
    assert "routine" in source

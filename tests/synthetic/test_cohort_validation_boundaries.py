from __future__ import annotations

import ast
import inspect
import subprocess
import sys

from synthetic.cohort_validation import validate_native_cohort
from tests.synthetic.test_cohort_boundaries import (
    ROOT,
    _forbidden_arguments,
    _forbidden_calls,
    _forbidden_modules,
    _scan,
)

MODULE = ROOT / "src" / "synthetic" / "cohort_validation.py"


def test_cohort_validation_module_stays_in_memory_and_out_of_governed_runtimes() -> None:
    source = MODULE.read_text(encoding="utf-8")
    imports, calls, arguments = _scan(source, "synthetic.cohort_validation")

    assert _forbidden_modules(imports) == set()
    assert _forbidden_calls(calls) == set()
    assert _forbidden_arguments(arguments) == set()
    assert "duckdb" not in source.lower()
    assert "pathlib" not in source.lower()
    assert "Path" not in source
    assert _forbidden_arguments(set(inspect.signature(validate_native_cohort).parameters)) == set()


def test_validation_import_does_not_load_governed_or_duckdb_dependencies() -> None:
    probe = (
        "import sys; import synthetic.cohort_validation; "
        "print('duckdb' in sys.modules); "
        "print('synthetic.calibration_input' in sys.modules); "
        "print('synthetic.heldout_validate' in sys.modules); "
        "print('synthetic.privacy_audit' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["False", "False", "False", "False"]


def test_public_source_has_no_filesystem_or_hidden_report_arguments() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    arguments = {
        node.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.arg)
    }
    assert not any(name.endswith("_path") for name in arguments)
    assert not any(name.endswith("_report") for name in arguments)
    assert "truth" not in arguments

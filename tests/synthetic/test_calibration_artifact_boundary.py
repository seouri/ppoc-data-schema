import ast
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VISIBLE_RUNTIME_PATHS = (
    Path("src/synthetic/__init__.py"),
    Path("src/synthetic/generate.py"),
    Path("src/synthetic/base_resources.py"),
    Path("src/synthetic/csv_package.py"),
    Path("src/synthetic/derivation.py"),
    Path("src/synthetic/manifest.py"),
    Path("src/synthetic/models.py"),
    Path("src/synthetic/randomness.py"),
    Path("src/synthetic/references.py"),
    Path("src/synthetic/run_directory.py"),
    Path("src/synthetic/schema_contract.py"),
    Path("src/synthetic/validate.py"),
)


def visible_paths() -> tuple[Path, ...]:
    native_paths = sorted((REPOSITORY_ROOT / "src/synthetic/native").glob("*.py"))
    return tuple(REPOSITORY_ROOT / path for path in VISIBLE_RUNTIME_PATHS) + tuple(native_paths)


def test_visible_paths_include_transitive_generator_support_modules() -> None:
    relative_paths = {path.relative_to(REPOSITORY_ROOT) for path in visible_paths()}
    assert {
        Path("src/synthetic/derivation.py"),
        Path("src/synthetic/models.py"),
        Path("src/synthetic/randomness.py"),
        Path("src/synthetic/references.py"),
        Path("src/synthetic/run_directory.py"),
        Path("src/synthetic/validate.py"),
    } <= relative_paths


def is_calibration_module(module: str | None) -> bool:
    return module in {
        "synthetic.calibrate",
        "synthetic.calibration",
        "synthetic.calibration_input",
    } or bool(module and module.startswith("synthetic.calibration."))


def is_relative_calibration_module(module: str | None) -> bool:
    return module in {"calibrate", "calibration", "calibration_input"} or bool(
        module and module.startswith("calibration.")
    )


def forbidden_calibration_import(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(is_calibration_module(alias.name) for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and is_calibration_module(node.module):
                return True
            if node.level == 0 and node.module == "synthetic" and any(
                alias.name in {"calibrate", "calibration", "calibration_input"}
                for alias in node.names
            ):
                return True
            if node.level > 0 and is_relative_calibration_module(node.module):
                return True
            if node.level > 0 and node.module is None and any(
                alias.name in {"calibrate", "calibration", "calibration_input"}
                for alias in node.names
            ):
                return True
    return False


def forbidden_calibration_call(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callable_node = node.func
        if isinstance(callable_node, ast.Name) and callable_node.id in {
            "calibrate",
            "load_calibration_artifact",
            "prepare_input",
        }:
            return True
        if isinstance(callable_node, ast.Attribute) and callable_node.attr in {
            "calibrate",
            "load_calibration_artifact",
            "prepare_input",
        }:
            return True
    return False


def assert_paths_do_not_use_calibration(paths: tuple[Path, ...]) -> None:
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert not forbidden_calibration_import(tree), path
        assert not forbidden_calibration_call(tree), path


@pytest.mark.parametrize(
    "source",
    [
        "import synthetic.calibration.loader",
        "from synthetic.calibration.loader import load_calibration_artifact",
        "import synthetic.calibrate",
        "from synthetic.calibration_input import prepare_input",
    ],
)
def test_forbidden_calibration_import_rejects_submodules(source: str) -> None:
    assert forbidden_calibration_import(ast.parse(source))


@pytest.mark.parametrize(
    "source",
    [
        "from .calibration import load_calibration_artifact",
        "from . import calibration",
        "from .calibration_input import prepare_input",
        "from . import calibrate",
        "from ..calibration import load_calibration_artifact",
        "from .. import calibration",
    ],
)
def test_forbidden_calibration_import_rejects_relative_modules(source: str) -> None:
    assert forbidden_calibration_import(ast.parse(source))


@pytest.mark.parametrize("source", ["prepare_input(connection, config)", "calibrator.prepare_input(connection, config)"])
def test_forbidden_calibration_call_rejects_governed_input_calls(source: str) -> None:
    assert forbidden_calibration_call(ast.parse(source))


def test_visible_paths_do_not_import_or_call_calibration_loader() -> None:
    assert_paths_do_not_use_calibration(visible_paths())


def test_boundary_scan_rejects_calibrator_usage_in_transitive_support_module(
    tmp_path: Path,
) -> None:
    support_module = tmp_path / "derivation.py"
    support_module.write_text(
        "from synthetic.calibration_input import prepare_input\n"
        "prepared = prepare_input(connection, config)\n",
        encoding="utf-8",
    )

    with pytest.raises(AssertionError, match="derivation.py"):
        assert_paths_do_not_use_calibration((support_module,))


def test_docs_name_the_aggregate_only_boundary() -> None:
    text = (REPOSITORY_ROOT / "docs/synthetic-generator.md").read_text(encoding="utf-8")
    assert "Aggregate calibration artifacts (development boundary)" in text
    assert 'load_calibration_artifact(Path("approved-calibration.json"))' in text

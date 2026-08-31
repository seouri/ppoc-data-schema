import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VISIBLE_RUNTIME_PATHS = (
    Path("src/synthetic/generate.py"),
    Path("src/synthetic/csv_package.py"),
    Path("src/synthetic/manifest.py"),
    Path("src/synthetic/schema_contract.py"),
)


def visible_paths() -> tuple[Path, ...]:
    native_paths = sorted((REPOSITORY_ROOT / "src/synthetic/native").glob("*.py"))
    return tuple(REPOSITORY_ROOT / path for path in VISIBLE_RUNTIME_PATHS) + tuple(native_paths)


def forbidden_calibration_import(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "synthetic.calibration" for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module == "synthetic.calibration":
                return True
            if node.level == 0 and node.module == "synthetic" and any(
                alias.name == "calibration" for alias in node.names
            ):
                return True
    return False


def forbidden_calibration_call(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "load_calibration_artifact":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "load_calibration_artifact":
            return True
    return False


def test_visible_paths_do_not_import_or_call_calibration_loader() -> None:
    for path in visible_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert not forbidden_calibration_import(tree), path
        assert not forbidden_calibration_call(tree), path


def test_docs_name_the_aggregate_only_boundary() -> None:
    text = (REPOSITORY_ROOT / "docs/synthetic-generator.md").read_text(encoding="utf-8")
    assert "Aggregate calibration artifacts (development boundary)" in text
    assert "load_calibration_artifact" in text

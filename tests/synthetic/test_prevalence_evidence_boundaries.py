from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "synthetic-generator.md"
README = ROOT / "README.md"
GOVERNED_MODULE = ROOT / "src" / "synthetic" / "prevalence_evidence.py"
GOVERNED_IMPORT = "synthetic.prevalence_evidence"
VISIBLE_ROOTS = (
    ROOT / "src" / "synthetic" / "__init__.py",
    ROOT / "src" / "synthetic" / "generate.py",
    ROOT / "src" / "synthetic" / "base_resources.py",
    ROOT / "src" / "synthetic" / "csv_package.py",
    ROOT / "src" / "synthetic" / "manifest.py",
    ROOT / "src" / "synthetic" / "derivation.py",
    ROOT / "src" / "synthetic" / "package_export.py",
    ROOT / "src" / "synthetic" / "cohort.py",
    *sorted((ROOT / "src" / "synthetic" / "native").glob("*.py")),
)
FORBIDDEN_GOVERNED_IMPORTS = {
    "synthetic.generate",
    "synthetic.csv_package",
    "synthetic.manifest",
    "synthetic.derivation",
    "synthetic.package_export",
    "synthetic.cohort",
    "synthetic.native",
}
HIDDEN_SERIALIZATION_NAMES = {
    "event_trace",
    "events",
    "latent",
    "patient_id",
    "sequence",
    "sequences",
    "trajectory",
    "truth",
    "truth_hash",
    "visit_id",
}


def _section(document: str, heading: str) -> str:
    return document.split(heading, maxsplit=1)[1].split("\n## ", maxsplit=1)[0]


def _module_context(path: Path) -> tuple[str, bool]:
    relative = path.relative_to(ROOT / "src").with_suffix("")
    parts = list(relative.parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts.pop()
    return ".".join(parts), is_package


def _import_from_base(node: ast.ImportFrom, module: str, *, is_package: bool) -> str | None:
    if node.level == 0:
        return node.module
    package = module.split(".") if is_package else module.split(".")[:-1]
    climb = node.level - 1
    if climb > len(package):
        return None
    parts = package[: len(package) - climb]
    if node.module is not None:
        parts.extend(node.module.split("."))
    return ".".join(parts)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    module, is_package = _module_context(path)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = _import_from_base(node, module, is_package=is_package)
            if base:
                names.add(base)
                names.update(f"{base}.{alias.name}" for alias in node.names)
    return names


def _dynamic_module_literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("synthetic.")
    }


def _module_path(name: str) -> Path | None:
    if not name.startswith("synthetic."):
        return None
    candidate = ROOT / "src" / Path(*name.split("."))
    source = candidate.with_suffix(".py")
    if source.is_file():
        return source
    initializer = candidate / "__init__.py"
    return initializer if initializer.is_file() else None


def _transitive_imports(roots: tuple[Path, ...]) -> set[str]:
    pending = list(roots)
    visited: set[Path] = set()
    names: set[str] = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        direct = _imports(path)
        dynamic = _dynamic_module_literals(path)
        names.update(direct)
        names.update(dynamic)
        pending.extend(
            candidate
            for name in direct | dynamic
            if (candidate := _module_path(name)) is not None
        )
    return names


def _serializer_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name not in {
            "to_mapping",
            "canonical_json_bytes",
            "human_summary",
        }:
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                names.add(child.id)
            elif isinstance(child, ast.Constant) and isinstance(child.value, str):
                names.add(child.value)
    return names


def test_guide_documents_governed_multi_run_prevalence_evidence() -> None:
    section = _section(
        GUIDE.read_text(encoding="utf-8"),
        "## Governed multi-run prevalence evidence\n",
    )

    for name in (
        "synthetic.prevalence_evidence",
        "PrevalenceRunSpec",
        "PrevalenceEvidenceConfig",
        "evaluate_prevalence_evidence",
        "write_prevalence_evidence",
    ):
        assert name in section
    for flag in (
        "--real-root",
        "--descriptor",
        "--snapshot",
        "--calibration-artifact",
        "--calibration-report",
        "--partition-policy",
        "--disclosure-policy",
        "--partition-key-file",
        "--frozen-policy",
        "--package-root",
        "--expected-seed",
        "--output",
    ):
        assert flag in section
    for boundary in (
        "at least three",
        "predeclared",
        "distinct",
        "exact manifest/package binding",
        "observed demographics",
        "recorded outcomes",
        "latent",
        "observable",
        "aggregate-only",
        "no adaptive prevalence forcing",
        "explicit",
        "governed",
    ):
        assert boundary in section
    assert "FAIL" in section and "UNEVALUABLE" in section
    assert "PASS" in section


def test_prevalence_evidence_docs_preserve_separate_evidence_caveats() -> None:
    guide_section = _section(
        GUIDE.read_text(encoding="utf-8"),
        "## Governed multi-run prevalence evidence\n",
    )
    readme_section = _section(
        README.read_text(encoding="utf-8"),
        "## Governed multi-run prevalence evidence\n",
    )

    for section in (guide_section, readme_section):
        for boundary in (
            "held-out",
            "privacy",
            "non-matchability",
            "clinical validity",
            "task utility",
            "release",
            "Synthea",
        ):
            assert boundary in section


def test_visible_generator_roots_do_not_import_prevalence_evidence() -> None:
    direct = set().union(*(_imports(path) for path in VISIBLE_ROOTS))
    transitive = _transitive_imports(VISIBLE_ROOTS)

    assert not direct & {GOVERNED_IMPORT}
    assert not transitive & {GOVERNED_IMPORT}


def test_transitive_import_scan_detects_dynamic_governed_literal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "src" / "synthetic"
    root.mkdir(parents=True)
    (root / "generate.py").write_text("from . import support\n", encoding="utf-8")
    (root / "support.py").write_text(
        'importlib.import_module("synthetic.prevalence_evidence")\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)

    assert GOVERNED_IMPORT in _transitive_imports((root / "generate.py",))


def test_transitive_import_scan_follows_dynamic_import_chains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "src" / "synthetic"
    root.mkdir(parents=True)
    (root / "generate.py").write_text(
        'importlib.import_module("synthetic.support")\n',
        encoding="utf-8",
    )
    (root / "support.py").write_text(
        'importlib.import_module("synthetic.prevalence_evidence")\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)

    assert GOVERNED_IMPORT in _transitive_imports((root / "generate.py",))


@pytest.mark.parametrize(
    ("source", "module", "is_package"),
    [
        ("from synthetic import prevalence_evidence", "synthetic.generate", False),
        ("from . import prevalence_evidence", "synthetic.generate", False),
        ("from .. import prevalence_evidence", "synthetic.native.healthy", False),
    ],
)
def test_import_scan_detects_direct_and_relative_prevalence_evidence_imports(
    source: str, module: str, is_package: bool
) -> None:
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            base = _import_from_base(node, module, is_package=is_package)
            if base:
                imported.add(base)
                imported.update(f"{base}.{alias.name}" for alias in node.names)

    assert GOVERNED_IMPORT in imported


def test_governed_module_does_not_import_visible_generation_roots() -> None:
    imports = _imports(GOVERNED_MODULE)
    assert not {
        name
        for name in imports
        if any(name == forbidden or name.startswith(f"{forbidden}.") for forbidden in FORBIDDEN_GOVERNED_IMPORTS)
    }


def test_governed_public_serializers_do_not_name_hidden_truth_fields() -> None:
    tree = ast.parse(GOVERNED_MODULE.read_text(encoding="utf-8"), filename=str(GOVERNED_MODULE))
    assert not _serializer_names(tree) & HIDDEN_SERIALIZATION_NAMES

from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import pytest

from synthetic.cohort import generate_native_cohort

ROOT = Path(__file__).resolve().parents[2]
COHORT = ROOT / "src" / "synthetic" / "cohort.py"
GUIDE = ROOT / "docs" / "synthetic-generator.md"
README = ROOT / "README.md"
VISIBLE_NATIVE_GENERATION = (
    COHORT,
    ROOT / "src" / "synthetic" / "native" / "age_regime_disorder.py",
    ROOT / "src" / "synthetic" / "native" / "age_regimes.py",
    ROOT / "src" / "synthetic" / "native" / "clinical_modules.py",
    ROOT / "src" / "synthetic" / "native" / "healthy.py",
    ROOT / "src" / "synthetic" / "native" / "observations.py",
    ROOT / "src" / "synthetic" / "native" / "resources.py",
    ROOT / "src" / "synthetic" / "native" / "trajectories.py",
)

FORBIDDEN_MODULES = {
    "pathlib",
    "shutil",
    "tempfile",
    "synthetic.calibrate",
    "synthetic.calibration_disclosure",
    "synthetic.calibration_input",
    "synthetic.csv_package",
    "synthetic.generate",
    "synthetic.heldout_validate",
    "synthetic.manifest",
    "synthetic.package_export",
    "synthetic.privacy_audit",
    "synthetic.real_data",
    "synthetic.realdata",
    "synthetic.run_directory",
    "synthetic.synthea",
}
FORBIDDEN_CALL_LEAVES = {
    "NamedTemporaryFile",
    "RunDirectory",
    "SpooledTemporaryFile",
    "TemporaryDirectory",
    "TemporaryFile",
    "audit_privacy",
    "calibrate",
    "chmod",
    "chown",
    "copy",
    "copy2",
    "copyfile",
    "copytree",
    "dump",
    "export_exact_schema_package",
    "export_observed_resource_package",
    "fchmod",
    "fchown",
    "ftruncate",
    "hardlink_to",
    "link",
    "lchmod",
    "lchown",
    "load_calibration_artifact",
    "load_descriptor",
    "make_archive",
    "makedirs",
    "mkdir",
    "mkdtemp",
    "mkfifo",
    "mknod",
    "mkstemp",
    "move",
    "open",
    "posix_fallocate",
    "pwrite",
    "pwritev",
    "read_bytes",
    "read_csv",
    "read_excel",
    "read_json",
    "read_parquet",
    "read_text",
    "read_table",
    "remove",
    "removedirs",
    "rename",
    "renames",
    "replace",
    "rmdir",
    "rmtree",
    "sendfile",
    "symlink",
    "symlink_to",
    "touch",
    "truncate",
    "unlink",
    "unpack_archive",
    "utime",
    "validate_heldout",
    "write",
    "write_bytes",
    "write_csv",
    "write_json",
    "write_text",
    "writev",
    "writelines",
}
SAFE_NON_FILESYSTEM_CALLS = {"dataclasses.replace"}
FORBIDDEN_ARGUMENTS = {
    "calibration_path",
    "data_root",
    "descriptor_path",
    "heldout_report",
    "key",
    "keys",
    "key_file",
    "output",
    "output_path",
    "path",
    "paths",
    "partition_key",
    "privacy_policy",
    "privacy_report",
    "real_data_root",
    "real_root",
    "report",
    "reports",
    "row",
    "rows",
    "sequence",
    "sequences",
    "snapshot_root",
    "synthea_input",
    "truth",
}
FORBIDDEN_ARGUMENT_SUFFIXES = (
    "_key",
    "_keys",
    "_key_file",
    "_key_files",
    "_path",
    "_paths",
    "_report",
    "_reports",
    "_root",
    "_roots",
    "_row",
    "_rows",
    "_sequence",
    "_sequences",
)


def _import_base(node: ast.ImportFrom, module_name: str) -> str | None:
    if node.level == 0:
        return node.module
    package = module_name.split(".")[:-1]
    climb = node.level - 1
    if climb > len(package):
        return None
    parts = package[: len(package) - climb]
    if node.module is not None:
        parts.extend(node.module.split("."))
    return ".".join(parts)


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


def _scan(source: str, module_name: str) -> tuple[set[str], set[str], set[str]]:
    tree = ast.parse(source, filename=f"<{module_name}>")
    imports: set[str] = set()
    bindings: dict[str, str] = {}
    arguments: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
                bindings[alias.asname or alias.name.split(".", maxsplit=1)[0]] = alias.name
        elif isinstance(node, ast.ImportFrom):
            base = _import_base(node, module_name)
            if base:
                imports.add(base)
                for alias in node.names:
                    qualified = f"{base}.{alias.name}"
                    imports.add(qualified)
                    bindings[alias.asname or alias.name] = qualified
        elif isinstance(node, ast.arg):
            arguments.add(node.arg)

    calls: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node.func)
        if name is None:
            continue
        root, dot, suffix = name.partition(".")
        calls.add(f"{bindings.get(root, root)}{dot}{suffix}")
    return imports, calls, arguments


def _forbidden_modules(imports: set[str]) -> set[str]:
    return {
        name
        for name in imports
        if any(
            name == forbidden or name.startswith(f"{forbidden}.")
            for forbidden in FORBIDDEN_MODULES
        )
    }


def _forbidden_calls(calls: set[str]) -> set[str]:
    return {
        name
        for name in calls
        if name not in SAFE_NON_FILESYSTEM_CALLS
        and name.rsplit(".", maxsplit=1)[-1] in FORBIDDEN_CALL_LEAVES
    }


def _forbidden_arguments(arguments: set[str]) -> set[str]:
    return {
        name
        for name in arguments
        if name in FORBIDDEN_ARGUMENTS
        or any(name.endswith(suffix) for suffix in FORBIDDEN_ARGUMENT_SUFFIXES)
    }


def test_cohort_module_has_no_governed_input_or_output_lifecycle_boundary() -> None:
    """Catches cohort orchestration gaining a reader, writer, or governed dependency."""
    imports, calls, arguments = _scan(
        COHORT.read_text(encoding="utf-8"), "synthetic.cohort"
    )

    assert _forbidden_modules(imports) == set()
    assert _forbidden_calls(calls) == set()
    assert _forbidden_arguments(arguments) == set()
    assert _forbidden_arguments(
        set(inspect.signature(generate_native_cohort).parameters)
    ) == set()


def test_importing_cohort_does_not_load_governed_target_runtime_dependencies() -> None:
    """Catches ordinary cohort import transitively loading governed target machinery."""
    probe = (
        "import sys; import synthetic.cohort; "
        "print('duckdb' in sys.modules); "
        "print('synthetic.calibration_input' in sys.modules)"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            probe,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["False", "False"]


def test_visible_native_generation_has_no_governed_or_package_lifecycle_dependency() -> None:
    """Catches visible native generation gaining file/package side effects."""
    for path in VISIBLE_NATIVE_GENERATION:
        module_name = ".".join(
            path.relative_to(ROOT / "src").with_suffix("").parts
        )
        imports, calls, _arguments = _scan(
            path.read_text(encoding="utf-8"), module_name
        )

        assert _forbidden_modules(imports) == set(), path
        assert _forbidden_calls(calls) == set(), path


def test_cohort_boundary_scanner_detects_aliases_and_lifecycle_calls() -> None:
    source = """from pathlib import Path as FilePath
from synthetic.package_export import export_observed_resource_package as export_package

def unsafe(*, real_root, output_path):
    FilePath(real_root).read_text()
    export_package([], {}, output_path)
"""

    imports, calls, arguments = _scan(source, "synthetic.cohort")

    assert _forbidden_modules(imports) == {
        "pathlib",
        "pathlib.Path",
        "synthetic.package_export",
        "synthetic.package_export.export_observed_resource_package",
    }
    assert _forbidden_calls(calls) == {
        "pathlib.Path.read_text",
        "synthetic.package_export.export_observed_resource_package",
    }
    assert _forbidden_arguments(arguments) == {"output_path", "real_root"}


@pytest.mark.parametrize(
    "source",
    (
        "from synthetic import package_export as pe",
        "from . import package_export as pe",
    ),
)
def test_cohort_boundary_scanner_detects_imported_module_aliases(source: str) -> None:
    imports, _calls, _arguments = _scan(source, "synthetic.cohort")

    assert _forbidden_modules(imports) == {"synthetic.package_export"}


@pytest.mark.parametrize(
    ("source", "expected_call"),
    (
        ("import os\nos.remove(path)", "os.remove"),
        ("from pathlib import Path\nPath(path).touch()", "pathlib.Path.touch"),
        ("import os\nos.link(source, target)", "os.link"),
        ("import os\nos.symlink(source, target)", "os.symlink"),
        ("import os\nos.truncate(path, 0)", "os.truncate"),
        ("import tempfile\ntempfile.mkstemp()", "tempfile.mkstemp"),
        ("import tempfile\ntempfile.mkdtemp()", "tempfile.mkdtemp"),
        ("import shutil\nshutil.copyfile(source, target)", "shutil.copyfile"),
        ("import os\nos.chmod(path, 0o600)", "os.chmod"),
        ("import os\nos.lchown(path, 0, 0)", "os.lchown"),
        ("import os\nos.fchmod(fd, 0o600)", "os.fchmod"),
        ("import os\nos.writev(fd, [b'x'])", "os.writev"),
        ("import os\nos.pwritev(fd, [b'x'], 0)", "os.pwritev"),
    ),
)
def test_cohort_boundary_scanner_detects_file_output_lifecycle_calls(
    source: str,
    expected_call: str,
) -> None:
    _imports, calls, _arguments = _scan(source, "synthetic.cohort")

    assert expected_call in _forbidden_calls(calls)


def test_cohort_boundary_scanner_detects_governed_argument_families() -> None:
    expected = {
        "path",
        "key",
        "report",
        "patient_row",
        "patient_rows",
        "row",
        "rows",
        "patient_sequence",
        "patient_sequences",
        "sequence",
        "sequences",
        "source_path",
        "source_key",
        "source_report",
        "source_reports",
        "source_rows",
        "source_keys",
        "source_paths",
        "visit_sequences",
        "keys",
        "paths",
        "reports",
    }
    parameters = ", ".join(sorted(expected))
    _imports, _calls, arguments = _scan(
        f"def unsafe({parameters}):\n    pass\n", "synthetic.cohort"
    )

    assert _forbidden_arguments(arguments) == expected


def test_native_cohort_documentation_states_usage_and_deferred_gates() -> None:
    """Catches the user guide presenting the cohort without its safety boundaries."""
    guide = GUIDE.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")

    for document in (guide, readme):
        for required in (
            "generate_native_cohort",
            "CalibrationSamplingProfile",
            "released aggregate",
            "explicit module prior",
            "healthy-plus-disorder",
            "already-loaded descriptor mapping",
            "evaluator-only",
            "no real-data path",
            "fail-closed command-line",
        ):
            assert required in document

    for required in (
        "CalibrationArtifact",
        "ObservationPolicy",
        "RegimeLinearTestReference",
        "blank/nonresponse",
        "race slot two",
        "recorded flags do not allocate latent disease",
        "export_observed_resource_package",
    ):
        assert required in guide

    for deferred in (
        "prevalence validation",
        "held-out validation",
        "privacy/non-matchability",
        "clinical validity",
        "task utility",
        "ancillary resources",
        "authoritative derivation",
        "release approval",
        "Synthea",
    ):
        assert deferred in guide

from __future__ import annotations

import ast
import inspect
import json
from pathlib import Path

import pytest

from synthetic.base_resources import build_base_rows
from synthetic.derivation import DerivationResult
from synthetic.derivation_binding import (
    BoundDerivationOracle,
    DerivationBinding,
    DerivationBindingUnavailable,
)
from synthetic.generate import generate_smoke
from synthetic.models import LatentPoint, PatientState
from synthetic.package_export import (
    PackageExportMetadata,
    PackageExportUnavailable,
    export_exact_schema_package,
    export_observed_resource_package,
)
from synthetic.schema_contract import (
    EXPECTED_SCHEMA_FINGERPRINT,
    load_descriptor,
    resource_spec,
)
from synthetic.validate import validate_structure
from tests.synthetic.fakes import (
    IdentityPreservingTestDerivationOracle,
    LinearTestReference,
    test_derivation_binding,
)

ROOT = Path(__file__).resolve().parents[2]
FINGERPRINT = "0123456789abcdef" * 4


class CountingOracle:
    oracle_id = "identity-preserving-test-oracle-v1"

    def __init__(self, result: object | None = None) -> None:
        self.calls = 0
        self.result = result or DerivationResult(self.oracle_id, FINGERPRINT, True)

    def derive(self, package_root: Path, descriptor: dict) -> object:
        del package_root, descriptor
        self.calls += 1
        return self.result


def _approved_binding() -> DerivationBinding:
    value = test_derivation_binding().to_mapping()
    value["test_only"] = False
    value["golden_evidence"] = {
        "manifest_id": "golden-ci-v1",
        "manifest_fingerprint": "c" * 64,
        "parity_contract": "derivation-parity-v1",
        "parity_report_id": "parity-ci-v1",
        "parity_report_fingerprint": "d" * 64,
        "parity_status": "PASS",
        "candidate_implementation_fingerprint": FINGERPRINT,
        "reference_implementation_fingerprint": "e" * 64,
        "parity_schema_fingerprint": EXPECTED_SCHEMA_FINGERPRINT,
        "covered_categories": [
            "filter_order",
            "age_boundaries",
            "missingness",
            "harrall_outlier",
            "biv_filtering",
            "velocity_variants",
            "rounding",
        ],
        "bidirectional_case_count": 7,
        "synthetic_fuzz_case_count": 10,
        "fuzz_corpus_fingerprint": "f" * 64,
    }
    value["review"] = {
        "review_id": "review-ci-v1",
        "review_fingerprint": "1" * 64,
        "reviewed_at": "2026-09-01T00:00:00Z",
        "reviewer_role": "custodian",
        "status": "APPROVED",
    }
    return DerivationBinding.from_mapping(value)


def _base_rows(descriptor: dict) -> dict[str, list[dict[str, object]]]:
    return build_base_rows(
        descriptor,
        PatientState("fictional-member-a", "F", "F"),
        (
            LatentPoint(
                patient_id="fictional-member-a",
                age_days=1095,
                height_cm=100.0,
                bmi=16.0,
                weight_kg=16.0,
                height_z=0.0,
                bmi_z=0.0,
            ),
        ),
        seed=1,
    )


def _metadata() -> PackageExportMetadata:
    return PackageExportMetadata(
        profile="binding-integration",
        seed=1,
        reference_time="2026-09-01T00:00:00Z",
        reference_id="reference-ci-v1",
        software_revision="revision-ci-v1",
        configuration_sha256="2" * 64,
        reference_sha256="3" * 64,
    )


def test_bound_oracle_delegates_exactly_once_for_matching_test_binding(tmp_path: Path) -> None:
    oracle = CountingOracle()
    bound = BoundDerivationOracle(oracle, test_derivation_binding())

    result = bound.derive(tmp_path, {})

    assert result is oracle.result
    assert oracle.calls == 1
    assert bound.oracle_id == oracle.oracle_id


@pytest.mark.parametrize(
    "mode",
    ["declared-id", "returned-id", "returned-fingerprint", "returned-classification", "wrong-shape"],
)
def test_bound_oracle_identity_failures_are_fixed_and_redacted(tmp_path: Path, mode: str) -> None:
    oracle = CountingOracle()
    if mode == "declared-id":
        oracle.oracle_id = "other-oracle-v1"
    elif mode == "returned-id":
        oracle.result = DerivationResult("other-oracle-v1", FINGERPRINT, True)
    elif mode == "returned-fingerprint":
        oracle.result = DerivationResult(oracle.oracle_id, "f" * 64, True)
    elif mode == "returned-classification":
        oracle.result = DerivationResult(oracle.oracle_id, FINGERPRINT, False)
    else:
        oracle.result = type(
            "DuckResult",
            (),
            {"oracle_id": oracle.oracle_id, "implementation_fingerprint": FINGERPRINT, "test_only": True},
        )()

    with pytest.raises(DerivationBindingUnavailable) as error:
        bound = BoundDerivationOracle(oracle, test_derivation_binding())
        bound.derive(tmp_path, {})

    assert str(error.value) == "derivation binding is unavailable"
    assert error.value.args == ("derivation binding is unavailable",)
    assert oracle.calls == (0 if mode == "declared-id" else 1)


def test_bound_oracle_discards_underlying_failure_text(tmp_path: Path) -> None:
    class LeakyOracle(CountingOracle):
        def derive(self, package_root: Path, descriptor: dict) -> object:
            del package_root, descriptor
            self.calls += 1
            raise RuntimeError("confidential implementation detail")

    oracle = LeakyOracle()
    bound = BoundDerivationOracle(oracle, test_derivation_binding())

    with pytest.raises(DerivationBindingUnavailable) as error:
        bound.derive(tmp_path, {})

    assert str(error.value) == "derivation binding is unavailable"
    assert error.value.__cause__ is None


def test_incomplete_non_test_binding_is_rejected_before_oracle_or_output(tmp_path: Path) -> None:
    value = test_derivation_binding().to_mapping()
    value["test_only"] = False
    binding = DerivationBinding.from_mapping(value)
    oracle = CountingOracle()
    descriptor = load_descriptor(ROOT / "datapackage.json")
    output = tmp_path / "package"

    with pytest.raises(PackageExportUnavailable, match="^observed package export failed$"):
        export_exact_schema_package(
            descriptor,
            _base_rows(descriptor),
            output,
            metadata=_metadata(),
            derivation_oracle=oracle,
            derivation_binding=binding,
        )

    assert oracle.calls == 0
    assert not output.exists()
    assert list(tmp_path.iterdir()) == []


def test_approved_non_test_binding_preserves_package_lifecycle(tmp_path: Path) -> None:
    class ApprovedOracle(IdentityPreservingTestDerivationOracle):
        def derive(self, package_root: Path, descriptor: dict) -> DerivationResult:
            result = super().derive(package_root, descriptor)
            return DerivationResult(result.oracle_id, result.implementation_fingerprint, False)

    descriptor = load_descriptor(ROOT / "datapackage.json")
    base_rows = _base_rows(descriptor)
    before = json.dumps(base_rows, sort_keys=True)
    package = export_exact_schema_package(
        descriptor,
        base_rows,
        tmp_path / "package",
        metadata=_metadata(),
        derivation_oracle=ApprovedOracle(),
        derivation_binding=_approved_binding(),
    )

    generated = json.loads((package / "datapackage.json").read_text(encoding="utf-8"))
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    assert json.dumps(base_rows, sort_keys=True) == before
    for name in ("patients_augmented", "visits_augmented"):
        assert (package / resource_spec(generated, name)["path"]).is_file()
    assert validate_structure(package, generated).errors == ()
    assert manifest["status"] == "STRUCTURE_VALIDATED"
    assert manifest["derivation_fingerprint"] == FINGERPRINT
    assert manifest["file_sha256"]


def test_exporter_and_generator_require_explicit_binding_argument(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    common = {
        "metadata": _metadata(),
        "derivation_oracle": IdentityPreservingTestDerivationOracle(),
    }
    with pytest.raises(TypeError, match="derivation_binding"):
        export_exact_schema_package(descriptor, _base_rows(descriptor), tmp_path / "exact", **common)
    with pytest.raises(TypeError, match="derivation_binding"):
        export_observed_resource_package((), descriptor, tmp_path / "observed", **common)
    with pytest.raises(TypeError, match="derivation_binding"):
        generate_smoke(
            descriptor_path=ROOT / "datapackage.json",
            output=tmp_path / "smoke",
            patient_count=1,
            seed=1,
            reference_time="2026-09-01T00:00:00Z",
            software_revision="revision-ci-v1",
            reference=LinearTestReference(),
            derivation_oracle=IdentityPreservingTestDerivationOracle(),
        )


def test_test_package_manifest_exposes_only_bound_classification(tmp_path: Path) -> None:
    descriptor = load_descriptor(ROOT / "datapackage.json")
    package = export_exact_schema_package(
        descriptor,
        _base_rows(descriptor),
        tmp_path / "package",
        metadata=_metadata(),
        derivation_oracle=IdentityPreservingTestDerivationOracle(),
        derivation_binding=test_derivation_binding(),
    )
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    rendered = json.dumps(manifest, sort_keys=True).lower()

    assert manifest["derivation_fingerprint"] == FINGERPRINT
    assert manifest["status"] == "STRUCTURE_VALIDATED_TEST_ORACLE"
    for forbidden in (
        "binding_id",
        "binding-ci-v1",
        "golden_evidence",
        "parity_report",
        "review_id",
        "review-ci-v1",
        "truth",
    ):
        assert forbidden not in rendered


def test_binding_integration_has_no_reader_network_synthea_or_implicit_call_path() -> None:
    binding_path = ROOT / "src" / "synthetic" / "derivation_binding.py"
    export_path = ROOT / "src" / "synthetic" / "package_export.py"
    generate_path = ROOT / "src" / "synthetic" / "generate.py"
    binding_tree = ast.parse(binding_path.read_text(encoding="utf-8"))

    forbidden_imports = {"requests", "urllib", "socket", "synthea", "pandas", "duckdb"}
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(binding_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    calls = {
        node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
        for node in ast.walk(binding_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
    }
    assert not imports & forbidden_imports
    assert not calls & {"open", "read_bytes", "read_text", "read_csv", "urlopen", "run", "Popen"}

    for function in (
        export_exact_schema_package,
        export_observed_resource_package,
        generate_smoke,
    ):
        parameter = inspect.signature(function).parameters["derivation_binding"]
        assert parameter.default is inspect.Parameter.empty
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY

    combined = export_path.read_text(encoding="utf-8") + generate_path.read_text(encoding="utf-8")
    assert "trusted_derivation_fingerprint" not in combined
    assert "trusted_derivation_test_only" not in combined

import ast
import math
import shutil
from pathlib import Path

import numpy as np
import pytest

from synthetic.cdc_reference import CdcGrowthReference, _inverse_lms, _parse_lms_table

ROOT = Path(__file__).parents[2]


def test_repository_reference_exposes_manifest_backed_metrics() -> None:
    reference = CdcGrowthReference.from_repository(ROOT)

    assert reference.reference_id == "cdc-lms-reference-v1"
    assert reference.metrics == (
        "bmi",
        "head_circumference_cm",
        "height_cm",
        "length_cm",
        "weight_kg",
    )
    assert reference.min_age_days == 0
    assert reference.max_age_days == 7305
    assert len(reference.source_sha256) == 64


def test_reference_matches_source_row_and_interpolates_lms() -> None:
    reference = CdcGrowthReference.from_repository(ROOT)
    rows = (ROOT / "data/statage_combined.csv").read_text(encoding="utf-8-sig").splitlines()
    header = rows[0].split(",")
    first = dict(zip(header, rows[1].split(",")))
    assert reference.value("length_cm", 0, "M", 0.0) == float(first["M"])

    lower = [line.split(",") for line in rows[2:4]]
    age = 30
    l, m, s = (float(np.interp(age / 30.4375, [float(row[1]) for row in lower], [float(row[i]) for row in lower])) for i in (2, 3, 4))
    z = 1.25
    expected = m * math.exp(s * z) if abs(l) < 1e-6 else m * (1 + l * s * z) ** (1 / l)
    assert math.isclose(reference.value("length_cm", int(age), "M", z), expected, rel_tol=1e-12)


def test_inverse_lms_branches_and_tiny_parser() -> None:
    assert math.isclose(_inverse_lms(1e-7, 10.0, 0.2, 1.5), 10.0 * math.exp(0.3))
    tiny = b"Sex,Agemos,L,M,S\n1,0,1,10,0.2\n1,1,1,11,0.2\n2,0,1,9,0.2\n2,1,1,10,0.2\n"
    parsed = _parse_lms_table(tiny, "tiny")
    assert len(parsed) == 4
    assert {row.sex for row in parsed} == {"M", "F"}
    assert math.isclose(_inverse_lms(parsed[0].l, parsed[0].m, parsed[0].s, 1), 12.0)


@pytest.mark.parametrize(
    ("metric", "age", "sex", "z", "error"),
    [("unknown", 0, "M", 0.0, KeyError), ("length_cm", -1, "M", 0.0, ValueError),
     ("length_cm", 0.5, "M", 0.0, TypeError), ("length_cm", 0, "U", 0.0, ValueError),
     ("length_cm", 0, "M", math.nan, ValueError), ("length_cm", 7306, "M", 0.0, ValueError)],
)
def test_reference_rejects_invalid_requests(metric, age, sex, z, error) -> None:
    reference = CdcGrowthReference.from_repository(ROOT)
    with pytest.raises(error):
        reference.value(metric, age, sex, z)


def test_bmi_smoke_boundary_uses_24_month_row() -> None:
    reference = CdcGrowthReference.from_repository(ROOT)
    assert reference.value("bmi", 730, "M", 0.0) == 16.57502768
    with pytest.raises(ValueError):
        reference.value("bmi", 729, "M", 0.0)


def test_reference_module_has_no_forbidden_imports() -> None:
    tree = ast.parse((ROOT / "src/synthetic/cdc_reference.py").read_text())
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert "scripts.augment" not in imports
    assert "synthetic.generate" not in imports
    assert "pandas" not in imports


@pytest.mark.parametrize(
    "source",
    [
        b"Sex,Agemos,L,M,S\n3,0,1,10,0.2\n3,1,1,11,0.2\n",
        b"Sex,Agemos,L,M,S\n1,0,1,10,0.2\n1,0,1,11,0.2\n2,0,1,9,0.2\n2,1,1,10,0.2\n",
        b"Sex,Agemos,L,M,S,M\n1,0,1,10,0.2\n1,1,1,11,0.2\n",
        b"Sex,Agemos,L,M,S\n1,0,nan,10,0.2\n1,1,1,11,0.2\n",
        b"Sex,Agemos,L,M,S\n1,0,1,0,0.2\n1,1,1,11,0.2\n",
        b"Sex,Agemos,L,M,S\n1,1,1,10,0.2\n1,0,1,11,0.2\n",
        b"Sex,Agemos,L,M\n1,0,1,10\n1,1,1,11\n",
        b"Sex,Agemos,L,M,S\n1,0,1,10,0.2\n1,1,1,11,0.2\n\xff",
        b"Sex,Agemos,L,M,S\n1,0,1,10,-0.2\n1,1,1,11,0.2\n2,0,1,9,0.2\n2,1,1,10,0.2\n",
    ],
)
def test_parser_rejects_malformed_tables(source: bytes) -> None:
    with pytest.raises(ValueError):
        _parse_lms_table(source, "test")


def _minimal_repository(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    shutil.copy(ROOT / "data/augment-runtime-manifest.json", data / "augment-runtime-manifest.json")
    for table in ("statage_combined.csv", "wtage_combined.csv", "bmiagerev.csv", "hcageinf.csv"):
        shutil.copy(ROOT / "data" / table, data / table)
    return tmp_path


def test_reference_rejects_table_digest_drift_without_leaking_path(tmp_path: Path) -> None:
    repository = _minimal_repository(tmp_path)
    table = repository / "data/statage_combined.csv"
    table.write_bytes(table.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="digest") as caught:
        CdcGrowthReference.from_repository(repository)
    assert str(repository) not in str(caught.value)


def test_reference_rejects_altered_manifest_without_leaking_path(tmp_path: Path) -> None:
    repository = _minimal_repository(tmp_path)
    manifest = repository / "data/augment-runtime-manifest.json"
    manifest.write_bytes(manifest.read_bytes() + b" ")
    with pytest.raises(ValueError) as caught:
        CdcGrowthReference.from_repository(repository)
    assert str(repository) not in str(caught.value)


def test_reference_rejects_symlinked_data_directory(tmp_path: Path) -> None:
    (tmp_path / "data").symlink_to(ROOT / "data", target_is_directory=True)
    with pytest.raises(ValueError):
        CdcGrowthReference.from_repository(tmp_path)

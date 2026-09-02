import hashlib
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

from synthetic.references import LmsGrowthReference, LmsRow


def test_lms_reference_converts_zero_and_nonzero_l_parameters() -> None:
    reference = LmsGrowthReference(
        "public-growth-v1",
        rows=(
            LmsRow("height_cm", 730, "F", 1.0, 100.0, 0.1),
            LmsRow("bmi", 730, "F", 0.0, 16.0, 0.1),
        ),
    )

    assert reference.value("height_cm", 730, "F", 2.0) == pytest.approx(120.0)
    assert reference.value("bmi", 730, "F", 2.0) == pytest.approx(16.0 * math.exp(0.2))


def test_lms_reference_linearly_interpolates_parameters_by_age() -> None:
    reference = LmsGrowthReference(
        "public-growth-v1",
        rows=(
            LmsRow("height_cm", 730, "F", 1.0, 100.0, 0.1),
            LmsRow("height_cm", 1095, "F", 1.0, 110.0, 0.2),
        ),
    )

    expected = 100.0 + (182.0 / 365.0) * 10.0
    assert reference.value("height_cm", 912, "F", 0.0) == pytest.approx(expected)


def test_lms_reference_rejects_missing_duplicate_and_invalid_rows() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        LmsGrowthReference(
            "public-growth-v1",
            rows=(
                LmsRow("height_cm", 730, "F", 1.0, 100.0, 0.1),
                LmsRow("height_cm", 730, "F", 1.0, 100.0, 0.1),
            ),
        )

    with pytest.raises(ValueError, match="positive"):
        LmsGrowthReference(
            "public-growth-v1",
            rows=(LmsRow("height_cm", 730, "F", 1.0, 100.0, 0.0),),
        )

    with pytest.raises(ValueError, match="reference_id"):
        LmsGrowthReference("", rows=(LmsRow("height_cm", 730, "F", 1.0, 100.0, 0.1),))


def test_lms_reference_rejects_unknown_keys_and_out_of_domain_values() -> None:
    reference = LmsGrowthReference(
        "public-growth-v1",
        rows=(LmsRow("height_cm", 730, "F", 1.0, 100.0, 0.1),),
    )

    with pytest.raises(KeyError, match="weight"):
        reference.value("weight", 730, "F", 0.0)
    with pytest.raises(ValueError, match="domain"):
        reference.value("height_cm", 729, "F", 0.0)
    with pytest.raises(ValueError, match="finite"):
        reference.value("height_cm", 730, "F", float("nan"))


def test_lms_reference_loads_csv_and_checks_exact_source_hash(tmp_path) -> None:
    path = tmp_path / "growth.csv"
    path.write_text(
        "metric,age_days,reference_sex,l,m,s\n"
        "height_cm,730,F,1,100,0.1\n",
        encoding="utf-8",
        newline="",
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    reference = LmsGrowthReference.from_csv(
        path, reference_id="public-growth-v1", expected_sha256=digest
    )

    assert reference.source_sha256 == digest
    assert reference.value("height_cm", 730, "F", 0.0) == pytest.approx(100.0)
    with pytest.raises(ValueError, match="SHA-256"):
        LmsGrowthReference.from_csv(
            path, reference_id="public-growth-v1", expected_sha256="0" * 64
        )
    with pytest.raises(ValueError, match="SHA-256"):
        LmsGrowthReference.from_csv(
            path, reference_id="public-growth-v1", expected_sha256=digest.upper()
        )


def test_lms_reference_hashes_and_parses_the_same_single_read(
    monkeypatch, tmp_path: Path
) -> None:
    path = tmp_path / "growth.csv"
    approved = (
        b"metric,age_days,reference_sex,l,m,s\n"
        b"height_cm,730,F,1,100,0.1\n"
    )
    replacement = (
        "metric,age_days,reference_sex,l,m,s\n"
        "height_cm,730,F,1,999,0.1\n"
    )
    approved_path = tmp_path / "approved.csv"
    path.write_text(replacement, encoding="utf-8", newline="")
    approved_path.write_bytes(approved)
    reads: list[str] = []
    real_open = os.open

    def open_approved(source, flags, *args, **kwargs):
        if Path(source) == path:
            reads.append("path-open")
            return real_open(approved_path, flags, *args, **kwargs)
        return real_open(source, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", open_approved)

    digest = hashlib.sha256(approved).hexdigest()
    reference = LmsGrowthReference.from_csv(
        path, reference_id="public-growth-v1", expected_sha256=digest
    )

    assert reads == ["path-open"]
    assert reference.source_sha256 == digest
    assert reference.value("height_cm", 730, "F", 0.0) == pytest.approx(100.0)


def test_lms_reference_rejects_bad_csv_columns(tmp_path) -> None:
    path = tmp_path / "growth.csv"
    path.write_text("metric,age_days,reference_sex,l,m\nheight_cm,730,F,1,100\n", encoding="utf-8")

    with pytest.raises(ValueError, match="columns"):
        LmsGrowthReference.from_csv(path, reference_id="public-growth-v1")


def test_lms_reference_rejects_malformed_or_uppercase_source_hash() -> None:
    row = LmsRow("height_cm", 730, "F", 1.0, 100.0, 0.1)

    with pytest.raises(ValueError, match="SHA-256"):
        LmsGrowthReference("public-growth-v1", rows=(row,), source_sha256="abc")
    with pytest.raises(ValueError, match="SHA-256"):
        LmsGrowthReference("public-growth-v1", rows=(row,), source_sha256="A" * 64)


def _write_reference_csv(path: Path) -> None:
    path.write_bytes(
        b"metric,age_days,reference_sex,l,m,s\n"
        b"height_cm,730,F,1,100,0.1\n"
    )


def test_lms_reference_rejects_symlink_source_without_following_it(tmp_path: Path) -> None:
    target = tmp_path / "growth.csv"
    link = tmp_path / "growth-link.csv"
    _write_reference_csv(target)
    link.symlink_to(target)

    with pytest.raises(ValueError, match="regular") as error:
        LmsGrowthReference.from_csv(link, reference_id="public-growth-v1")

    assert str(link) not in str(error.value)


def test_lms_reference_rejects_directory_source_without_path_in_error(tmp_path: Path) -> None:
    directory = tmp_path / "growth-directory"
    directory.mkdir()

    with pytest.raises(ValueError, match="regular") as error:
        LmsGrowthReference.from_csv(directory, reference_id="public-growth-v1")

    assert str(directory) not in str(error.value)


def test_lms_reference_rejects_missing_source_without_path_in_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.csv"

    with pytest.raises(ValueError, match="unavailable") as error:
        LmsGrowthReference.from_csv(missing, reference_id="public-growth-v1")

    assert str(missing) not in str(error.value)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO creation is unavailable")
def test_lms_reference_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "growth.fifo"
    os.mkfifo(fifo)
    root = Path(__file__).resolve().parents[2]
    script = """
from pathlib import Path
import sys

from synthetic.references import LmsGrowthReference

try:
    LmsGrowthReference.from_csv(Path(sys.argv[1]), reference_id="public-growth-v1")
except ValueError as error:
    if "regular" not in str(error) or sys.argv[1] in str(error):
        raise
    raise SystemExit(0)
raise SystemExit("FIFO was unexpectedly accepted")
"""

    result = subprocess.run(
        [sys.executable, "-c", script, str(fifo)],
        cwd=root,
        env=os.environ | {"PYTHONPATH": str(root / "src")},
        capture_output=True,
        text=True,
        timeout=2,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_lms_reference_normalizes_invalid_utf8(tmp_path: Path) -> None:
    path = tmp_path / "growth.csv"
    path.write_bytes(
        b"metric,age_days,reference_sex,l,m,s\n"
        b"height_cm,730,F,1,100,\xff\n"
    )

    with pytest.raises(ValueError, match="UTF-8"):
        LmsGrowthReference.from_csv(path, reference_id="public-growth-v1")


@pytest.mark.parametrize("field", ["l", "m", "s"])
def test_lms_row_rejects_boolean_parameters(field: str) -> None:
    parameters = {"l": 1.0, "m": 100.0, "s": 0.1}
    parameters[field] = True

    with pytest.raises(ValueError, match=field):
        LmsRow("height_cm", 730, "F", **parameters)


def test_lms_reference_rejects_nonfinite_base_before_exponentiation() -> None:
    reference = LmsGrowthReference(
        "public-growth-v1",
        rows=(LmsRow("height_cm", 730, "F", 1e308, 100.0, 1e308),),
    )

    with pytest.raises(ValueError, match="base"):
        reference.value("height_cm", 730, "F", 1.0)


def test_lms_reference_normalizes_oversized_z_score() -> None:
    reference = LmsGrowthReference(
        "public-growth-v1",
        rows=(LmsRow("height_cm", 730, "F", 1.0, 100.0, 0.1),),
    )

    with pytest.raises(ValueError, match="z must be finite"):
        reference.value("height_cm", 730, "F", 10**1000)


@pytest.mark.parametrize("field", ["l", "m", "s"])
def test_lms_row_normalizes_oversized_parameters(field: str) -> None:
    parameters = {"l": 1.0, "m": 100.0, "s": 0.1}
    parameters[field] = 10**1000

    with pytest.raises(ValueError, match=f"{field} must be a finite float"):
        LmsRow("height_cm", 730, "F", **parameters)

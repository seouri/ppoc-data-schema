import hashlib
import math

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

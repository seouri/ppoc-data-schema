import json
import os
from pathlib import Path

import pytest

from synthetic.calibration import (
    MAX_CALIBRATION_ARTIFACT_BYTES,
    CalibrationArtifact,
    load_calibration_artifact,
)


def valid_mapping() -> dict[str, object]:
    return {
        "artifact_version": "calibration-artifact-v1",
        "artifact_id": "calibration-2026-08-24-v1",
        "source_snapshot": "2026-08-24",
        "source_partition": "calibration",
        "source_aggregate_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "schema_fingerprint": "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210",
        "created_at": "2026-08-30T00:00:00Z",
        "disclosure_policy": {
            "policy_id": "policy-example-v1",
            "policy_version": "1",
            "minimum_cell_count": 10,
            "continuous_rounding_decimals": 3,
        },
        "strata": [
            {
                "stratum_id": "age_regime=infancy|reference_sex=F",
                "dimensions": {"reference_sex": "F", "age_regime": "infancy"},
                "targets": [
                    {
                        "target_name": "height_z",
                        "family": "physiology",
                        "statistic": "mean",
                        "unit": "z",
                        "status": "released",
                        "value": -0.03,
                        "support_count": 120,
                        "denominator": 120,
                        "rounding_decimals": 3,
                    },
                    {
                        "target_name": "service_rate",
                        "family": "utilization",
                        "statistic": "rate",
                        "unit": "per_year",
                        "status": "released",
                        "value": 0.3,
                        "support_count": 40,
                        "denominator": 120,
                        "rounding_decimals": 3,
                    },
                ],
            },
            {
                "stratum_id": "age_regime=infancy|reference_sex=M",
                "dimensions": {"reference_sex": "M", "age_regime": "infancy"},
                "targets": [
                    {
                        "target_name": "height_z",
                        "family": "physiology",
                        "statistic": "mean",
                        "unit": "z",
                        "status": "released",
                        "value": 0.02,
                        "support_count": 120,
                        "denominator": 120,
                        "rounding_decimals": 3,
                    }
                ],
            },
        ],
    }


def valid_mapping_with_strata_and_targets_in_reverse_order() -> dict[str, object]:
    mapping = valid_mapping()
    strata = mapping["strata"]
    assert isinstance(strata, list)
    first_targets = strata[0]["targets"]
    assert isinstance(first_targets, list)
    first_targets.reverse()
    strata.reverse()
    return mapping


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")


def test_loader_and_canonical_json_are_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_json(first, valid_mapping())
    write_json(second, valid_mapping_with_strata_and_targets_in_reverse_order())

    left = load_calibration_artifact(first)
    right = load_calibration_artifact(second)

    assert left == right
    assert left.canonical_json() == right.canonical_json()
    assert " " not in left.canonical_json()
    assert "\n" not in left.canonical_json()
    assert "\\ud" not in left.canonical_json().lower()


@pytest.mark.parametrize(
    ("replacement", "match"),
    [
        (
            '"artifact_version":"previous","artifact_version":"calibration-artifact-v1"',
            "duplicate key",
        ),
        ('"target_name":"duplicate","target_name":"height_z"', "duplicate key"),
    ],
)
def test_loader_rejects_duplicate_keys_at_every_object_depth(
    tmp_path: Path, replacement: str, match: str
) -> None:
    path = tmp_path / "duplicate.json"
    payload = json.dumps(valid_mapping(), separators=(",", ":"))
    if "artifact_version" in replacement:
        payload = payload.replace('"artifact_version":"calibration-artifact-v1"', replacement, 1)
    else:
        payload = payload.replace('"target_name":"height_z"', replacement, 1)
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match=match):
        load_calibration_artifact(path)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_loader_rejects_nonfinite_json_constants_without_parser_exception(
    tmp_path: Path, constant: str
) -> None:
    path = tmp_path / "nonfinite.json"
    payload = json.dumps(valid_mapping(), separators=(",", ":")).replace(
        '"value":-0.03', f'"value":{constant}', 1
    )
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match="nonfinite JSON constant") as error:
        load_calibration_artifact(path)

    assert error.value.__cause__ is None


@pytest.mark.parametrize(
    ("filename", "payload", "match"),
    [
        ("bom.json", b"\xef\xbb\xbf{}", "UTF-8 BOM"),
        ("invalid-utf8.json", b"\xff", "UTF-8"),
        ("malformed.json", b'{"artifact_version":', "valid JSON"),
        ("array.json", b"[]", "root"),
    ],
)
def test_loader_rejects_invalid_encoding_and_nonobject_roots_without_parser_exception(
    tmp_path: Path, filename: str, payload: bytes, match: str
) -> None:
    path = tmp_path / filename
    path.write_bytes(payload)

    with pytest.raises(ValueError, match=match) as error:
        load_calibration_artifact(path)

    assert error.value.__cause__ is None


def test_loader_rejects_missing_path_symlink_and_directory(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    source = tmp_path / "source.json"
    symlink = tmp_path / "linked.json"
    directory = tmp_path / "directory"
    write_json(source, valid_mapping())
    symlink.symlink_to(source)
    directory.mkdir()

    for path, match in ((missing, "not found"), (symlink, "regular file"), (directory, "regular file")):
        with pytest.raises(ValueError, match=match):
            load_calibration_artifact(path)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO creation is not supported")
def test_loader_rejects_fifo_before_opening(tmp_path: Path) -> None:
    fifo = tmp_path / "artifact.fifo"
    os.mkfifo(fifo)

    with pytest.raises(ValueError, match="regular file"):
        load_calibration_artifact(fifo)


def test_loader_accepts_exact_byte_limit_and_rejects_one_byte_over(tmp_path: Path) -> None:
    payload = json.dumps(valid_mapping(), separators=(",", ":")).encode("utf-8")
    exact = tmp_path / "exact.json"
    over = tmp_path / "over.json"
    exact.write_bytes(payload + b" " * (MAX_CALIBRATION_ARTIFACT_BYTES - len(payload)))
    over.write_bytes(payload + b" " * (MAX_CALIBRATION_ARTIFACT_BYTES + 1 - len(payload)))

    assert load_calibration_artifact(exact) == CalibrationArtifact.from_mapping(valid_mapping())
    with pytest.raises(ValueError, match="maximum size"):
        load_calibration_artifact(over)


def test_loader_rejects_file_that_grows_after_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "growing.json"
    write_json(path, valid_mapping())
    original_read = os.read
    grew = False

    def grow_after_read(descriptor: int, length: int) -> bytes:
        nonlocal grew
        payload = original_read(descriptor, length)
        if not grew:
            with path.open("ab") as handle:
                handle.write(b" " * MAX_CALIBRATION_ARTIFACT_BYTES)
            grew = True
        return payload

    monkeypatch.setattr(os, "read", grow_after_read)

    with pytest.raises(ValueError, match="maximum size"):
        load_calibration_artifact(path)

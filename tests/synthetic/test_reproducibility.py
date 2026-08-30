import json

import pytest

from synthetic.manifest import RunManifest
from synthetic.randomness import NamedRandomStreams, synthetic_id


def test_named_streams_are_stable_and_isolated() -> None:
    left = NamedRandomStreams(20260830, 7)
    right = NamedRandomStreams(20260830, 7)
    assert left.generator("growth").normal(size=4).tolist() == (
        right.generator("growth").normal(size=4).tolist()
    )
    assert left.generator("growth").normal(size=4).tolist() != (
        left.generator("visits").normal(size=4).tolist()
    )


def test_named_streams_are_isolated_from_consumption_order() -> None:
    consumed = NamedRandomStreams(20260830, 7)
    consumed.generator("visits").normal(size=20)
    expected = NamedRandomStreams(20260830, 7).generator("growth").normal(size=4)
    actual = consumed.generator("growth").normal(size=4)
    assert actual.tolist() == expected.tolist()


@pytest.mark.parametrize("name", ["", " ", "growth\ntrace"])
def test_named_streams_reject_invalid_names(name: str) -> None:
    with pytest.raises(ValueError, match="stream name"):
        NamedRandomStreams(20260830, 7).generator(name)


def test_identifiers_are_deterministic_but_opaque() -> None:
    first = synthetic_id(20260830, "patient", 7)
    assert first == synthetic_id(20260830, "patient", 7)
    assert first != synthetic_id(20260830, "visit", 7)
    assert "7" not in first


def test_identifiers_do_not_expose_adversarial_kind_or_index() -> None:
    identifier = synthetic_id(20260830, "patient:real-child-123", 987654321)
    assert identifier.startswith("syn-")
    assert "patient" not in identifier
    assert "real-child-123" not in identifier
    assert "987654321" not in identifier
    assert " " not in identifier


@pytest.mark.parametrize("args", [(20260830, "", 1), (20260830, "patient", -1)])
def test_identifiers_reject_invalid_inputs(args: tuple[int, str, int]) -> None:
    with pytest.raises(ValueError):
        synthetic_id(*args)


def test_manifest_serialization_is_canonical() -> None:
    manifest = RunManifest.smoke(
        seed=20260830,
        schema_fingerprint="abc",
        reference_time="2026-08-30T00:00:00Z",
        reference_id="linear-test-reference-v1",
        configuration_sha256="config-hash",
        software_revision="test-revision",
    )
    decoded = json.loads(manifest.to_json_bytes())
    assert decoded["status"] == "GENERATED_UNVALIDATED"
    assert decoded["reference_id"] == "linear-test-reference-v1"
    assert decoded["software_revision"] == "test-revision"
    assert decoded["metadata_only"] is True
    assert decoded["row_counts"] == {}
    assert decoded["file_sha256"] == {}
    assert "derivation_oracle" not in decoded
    assert manifest.to_json_bytes().endswith(b"\n")


def test_generated_manifest_requires_output_evidence() -> None:
    manifest = RunManifest.smoke(
        seed=20260830,
        schema_fingerprint="abc",
        reference_time="2026-08-30T00:00:00Z",
        reference_id="linear-test-reference-v1",
        configuration_sha256="config-hash",
        software_revision="test-revision",
    )
    generated = manifest.__class__(**{**manifest.__dict__, "metadata_only": False})
    with pytest.raises(ValueError, match="row_counts and file_sha256"):
        generated.to_json_bytes()

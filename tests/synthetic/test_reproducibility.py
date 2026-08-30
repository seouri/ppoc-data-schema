import json

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


def test_identifiers_are_deterministic_but_opaque() -> None:
    first = synthetic_id(20260830, "patient", 7)
    assert first == synthetic_id(20260830, "patient", 7)
    assert first != synthetic_id(20260830, "visit", 7)
    assert "7" not in first


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
    assert manifest.to_json_bytes().endswith(b"\n")

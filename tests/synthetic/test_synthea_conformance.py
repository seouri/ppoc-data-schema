from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from synthetic.synthea_conformance import (
    SYNTHEA_CONFORMANCE_VERSION,
    SyntheaConformanceUnavailable,
    SyntheaEngineManifest,
)

ERROR_MESSAGE = "synthea conformance manifest unavailable"


def manifest_mapping() -> dict[str, object]:
    """Return fictional, aggregate-only repository fixture metadata."""
    return {
        "manifest_version": "synthea-conformance-v1",
        "engine_id": "synthea",
        "engine_revision": "revision-20260901",
        "engine_sha256": "a" * 64,
        "module_manifest_sha256": "b" * 64,
        "growth_extension_id": "growth-extension-v1",
        "growth_extension_sha256": "c" * 64,
        "event_adapter_id": "event-adapter-v1",
        "event_adapter_sha256": "d" * 64,
        "ppoc_exporter_id": "ppoc-exporter-v1",
        "ppoc_exporter_sha256": "e" * 64,
        "configuration_sha256": "f" * 64,
        "license_notice_id": "apache-notice-v1",
        "review_status": "PENDING",
        "test_only": True,
    }


def assert_unavailable(call: Callable[[], object], submitted: object) -> None:
    with pytest.raises(SyntheaConformanceUnavailable) as caught:
        call()

    assert str(caught.value) == ERROR_MESSAGE
    assert caught.value.args == (ERROR_MESSAGE,)
    assert caught.value.__cause__ is None
    submitted_text = str(submitted)
    if submitted_text and submitted_text not in ERROR_MESSAGE:
        assert submitted_text not in str(caught.value)


def test_valid_manifest_constructs_and_round_trips() -> None:
    expected = manifest_mapping()

    manifest = SyntheaEngineManifest.from_mapping(expected)

    assert SYNTHEA_CONFORMANCE_VERSION == "synthea-conformance-v1"
    assert manifest.manifest_version == SYNTHEA_CONFORMANCE_VERSION
    assert manifest.engine_id == "synthea"
    assert manifest.review_status == "PENDING"
    assert manifest.test_only is True
    assert manifest.to_mapping() == expected
    assert json.loads(manifest.to_json_bytes()) == expected


def test_manifest_is_frozen_and_mapping_results_do_not_alias_state() -> None:
    source = manifest_mapping()
    manifest = SyntheaEngineManifest.from_mapping(source)

    with pytest.raises(FrozenInstanceError):
        manifest.engine_revision = "changed"  # type: ignore[misc]

    first = manifest.to_mapping()
    second = manifest.to_mapping()
    assert first is not second

    source["engine_revision"] = "source-was-mutated"
    first["engine_revision"] = "result-was-mutated"
    assert manifest.engine_revision == "revision-20260901"
    assert manifest.to_mapping()["engine_revision"] == "revision-20260901"


def test_direct_construction_cannot_retain_non_scalar_state() -> None:
    submitted = ["mutable-secret"]
    value = manifest_mapping()
    value["engine_revision"] = submitted

    assert_unavailable(lambda: SyntheaEngineManifest(**value), "mutable-secret")  # type: ignore[arg-type]


def test_manifest_json_is_canonical_ascii_sorted_and_newline_terminated() -> None:
    expected = (
        b'{"configuration_sha256":"ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",'
        b'"engine_id":"synthea","engine_revision":"revision-20260901",'
        b'"engine_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
        b'"event_adapter_id":"event-adapter-v1",'
        b'"event_adapter_sha256":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",'
        b'"growth_extension_id":"growth-extension-v1",'
        b'"growth_extension_sha256":"cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",'
        b'"license_notice_id":"apache-notice-v1",'
        b'"manifest_version":"synthea-conformance-v1",'
        b'"module_manifest_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",'
        b'"ppoc_exporter_id":"ppoc-exporter-v1",'
        b'"ppoc_exporter_sha256":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",'
        b'"review_status":"PENDING","test_only":true}\n'
    )

    encoded = SyntheaEngineManifest.from_mapping(manifest_mapping()).to_json_bytes()

    assert encoded == expected
    assert encoded.isascii()
    assert encoded.endswith(b"\n") and not encoded.endswith(b"\n\n")


def test_manifest_json_round_trip_preserves_equality() -> None:
    manifest = SyntheaEngineManifest.from_mapping(manifest_mapping())

    assert SyntheaEngineManifest.from_json_bytes(manifest.to_json_bytes()) == manifest


@pytest.mark.parametrize(
    ("field", "submitted"),
    [
        ("manifest_version", True),
        ("engine_id", 1),
        ("engine_revision", False),
        ("growth_extension_id", object()),
        ("event_adapter_id", []),
        ("ppoc_exporter_id", {}),
        ("license_notice_id", 3.5),
        ("review_status", None),
        ("engine_sha256", True),
        ("module_manifest_sha256", 64),
        ("growth_extension_sha256", None),
        ("event_adapter_sha256", []),
        ("ppoc_exporter_sha256", {}),
        ("configuration_sha256", 3.5),
        ("test_only", 1),
    ],
)
def test_manifest_rejects_wrong_scalar_types(field: str, submitted: object) -> None:
    value = manifest_mapping()
    value[field] = submitted

    assert_unavailable(lambda: SyntheaEngineManifest.from_mapping(value), submitted)


@pytest.mark.parametrize(
    ("field", "submitted"),
    [
        ("manifest_version", "synthea-conformance-v2"),
        ("engine_id", "another-engine"),
        ("review_status", "PASS"),
        ("review_status", "approved"),
        ("test_only", "true"),
    ],
)
def test_manifest_rejects_wrong_fixed_or_enumerated_values(
    field: str, submitted: object
) -> None:
    value = manifest_mapping()
    value[field] = submitted

    assert_unavailable(lambda: SyntheaEngineManifest.from_mapping(value), submitted)


@pytest.mark.parametrize(
    "submitted",
    [
        "",
        "x" * 65,
        "Uppercase-token",
        "two tokens",
        "line\nbreak",
        "../module",
        "module/path",
        "module\\path",
        "https://example.test",
        ".hidden-component",
        "patient-aggregate",
        "visit-aggregate",
        "row-count",
        "clinical-value-v1",
        "hidden-truth-v1",
        "secret-key-v1",
        "source-record-v1",
        "network-endpoint-v1",
        "runtime-state-v1",
    ],
)
def test_manifest_rejects_unsafe_identifier_tokens(submitted: str) -> None:
    value = manifest_mapping()
    value["growth_extension_id"] = submitted

    assert_unavailable(lambda: SyntheaEngineManifest.from_mapping(value), submitted)


@pytest.mark.parametrize(
    "submitted",
    [
        "0" * 64,
        "A" * 64,
        "g" * 64,
        "a" * 63,
        "a" * 65,
        "sha256:" + "a" * 64,
    ],
)
def test_manifest_rejects_noncanonical_or_zero_digests(submitted: str) -> None:
    value = manifest_mapping()
    value["engine_sha256"] = submitted

    assert_unavailable(lambda: SyntheaEngineManifest.from_mapping(value), submitted)


def test_manifest_requires_exactly_the_declared_keys() -> None:
    missing = manifest_mapping()
    del missing["license_notice_id"]
    assert_unavailable(lambda: SyntheaEngineManifest.from_mapping(missing), "license_notice_id")

    unknown = manifest_mapping()
    unknown["submitted-secret"] = "do-not-echo"
    assert_unavailable(lambda: SyntheaEngineManifest.from_mapping(unknown), "do-not-echo")

    not_a_mapping: Any = [("manifest_version", "synthea-conformance-v1")]
    assert_unavailable(
        lambda: SyntheaEngineManifest.from_mapping(not_a_mapping), "synthea-conformance-v1"
    )


@pytest.mark.parametrize(
    ("submitted", "marker"),
    [
        (
            lambda: (
                json.dumps(manifest_mapping())[:-1] + ', "engine_id": "duplicate-secret"}'
            ).encode("ascii"),
            "duplicate-secret",
        ),
        (
            lambda: json.dumps({**manifest_mapping(), "test_only": float("nan")}).encode(
                "ascii"
            ),
            "NaN",
        ),
        (
            lambda: json.dumps({**manifest_mapping(), "test_only": float("inf")}).encode(
                "ascii"
            ),
            "Infinity",
        ),
        (lambda: b'{"engine_id":"synthea-\xc3\xa9"}', "é"),
        (lambda: b"[]", "[]"),
        (lambda: b"null", "null"),
        (lambda: json.dumps(manifest_mapping()).encode("ascii") + b" trailing-secret", "trailing-secret"),
    ],
)
def test_manifest_rejects_invalid_json_bytes(
    submitted: Callable[[], bytes], marker: str
) -> None:
    assert_unavailable(lambda: SyntheaEngineManifest.from_json_bytes(submitted()), marker)


def test_manifest_json_parser_requires_bytes() -> None:
    submitted = json.dumps(manifest_mapping())
    assert_unavailable(lambda: SyntheaEngineManifest.from_json_bytes(submitted), submitted)  # type: ignore[arg-type]


def test_approved_manifest_is_still_only_a_declaration() -> None:
    approved = manifest_mapping()
    approved["review_status"] = "APPROVED"
    declaration = SyntheaEngineManifest.from_mapping(approved)

    assert declaration.review_status == "APPROVED"
    for prohibited_name in (
        "conformance_result",
        "is_conformant",
        "passes",
        "release_ready",
        "is_release_ready",
        "promote",
        "execute",
    ):
        assert not hasattr(declaration, prohibited_name)

    fixture = manifest_mapping()
    assert fixture["review_status"] == "PENDING"
    assert fixture["test_only"] is True

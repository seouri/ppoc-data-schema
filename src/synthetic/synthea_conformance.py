"""Aggregate-only declaration contract for a future pinned Synthea engine."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

SYNTHEA_CONFORMANCE_VERSION: str = "synthea-conformance-v1"

_ERROR_MESSAGE = "synthea conformance manifest unavailable"
_ENGINE_ID = "synthea"
_REVIEW_STATUSES = frozenset({"PENDING", "APPROVED", "REJECTED"})
_TOKEN_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?\Z")
_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_UNSAFE_IDENTIFIER_PARTS = (
    "patient",
    "visit",
    "mrn",
    "encounter",
    "subject",
    "person",
    "clinical",
    "value",
    "truth",
    "key",
    "source",
    "network",
    "runtime",
    "record",
    "trace",
    "secret",
    "credential",
    "input",
    "output",
    "file",
    "path",
    "url",
    "http",
    "host",
    "socket",
    "endpoint",
)
_UNSAFE_IDENTIFIER_COMPONENT_PREFIXES = ("row",)
_TOKEN_FIELDS = (
    "engine_revision",
    "growth_extension_id",
    "event_adapter_id",
    "ppoc_exporter_id",
    "license_notice_id",
)
_DIGEST_FIELDS = (
    "engine_sha256",
    "module_manifest_sha256",
    "growth_extension_sha256",
    "event_adapter_sha256",
    "ppoc_exporter_sha256",
    "configuration_sha256",
)
_FIELD_NAMES = (
    "manifest_version",
    "engine_id",
    "engine_revision",
    "engine_sha256",
    "module_manifest_sha256",
    "growth_extension_id",
    "growth_extension_sha256",
    "event_adapter_id",
    "event_adapter_sha256",
    "ppoc_exporter_id",
    "ppoc_exporter_sha256",
    "configuration_sha256",
    "license_notice_id",
    "review_status",
    "test_only",
)
_FIELD_NAME_SET = frozenset(_FIELD_NAMES)


class SyntheaConformanceUnavailable(Exception):
    """Indicate that a manifest cannot be accepted without exposing its input."""


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject_json_constant(_: str) -> object:
    raise ValueError


def _is_safe_token(value: object) -> bool:
    return (
        type(value) is str
        and _TOKEN_PATTERN.fullmatch(value) is not None
        and not any(part in value for part in _UNSAFE_IDENTIFIER_PARTS)
        and not any(
            component.startswith(prefix)
            for component in value.split("-")
            for prefix in _UNSAFE_IDENTIFIER_COMPONENT_PREFIXES
        )
    )


def _is_digest(value: object) -> bool:
    return (
        type(value) is str
        and _DIGEST_PATTERN.fullmatch(value) is not None
        and value != "0" * 64
    )


def _validate_mapping(value: dict[str, object]) -> None:
    if set(value) != _FIELD_NAME_SET:
        raise ValueError
    if (
        type(value["manifest_version"]) is not str
        or value["manifest_version"] != SYNTHEA_CONFORMANCE_VERSION
    ):
        raise ValueError
    if type(value["engine_id"]) is not str or value["engine_id"] != _ENGINE_ID:
        raise ValueError
    if not all(_is_safe_token(value[field]) for field in _TOKEN_FIELDS):
        raise ValueError
    if not all(_is_digest(value[field]) for field in _DIGEST_FIELDS):
        raise ValueError
    if type(value["review_status"]) is not str:
        raise TypeError
    if value["review_status"] not in _REVIEW_STATUSES:
        raise ValueError
    if not isinstance(value["test_only"], bool):
        raise TypeError


@dataclass(frozen=True)
class SyntheaEngineManifest:
    """Immutable aggregate identities for an optional future Synthea handoff."""

    manifest_version: str
    engine_id: str
    engine_revision: str
    engine_sha256: str
    module_manifest_sha256: str
    growth_extension_id: str
    growth_extension_sha256: str
    event_adapter_id: str
    event_adapter_sha256: str
    ppoc_exporter_id: str
    ppoc_exporter_sha256: str
    configuration_sha256: str
    license_notice_id: str
    review_status: str
    test_only: bool

    def __init_subclass__(cls, **_: object) -> None:
        raise TypeError(_ERROR_MESSAGE)

    def __post_init__(self) -> None:
        try:
            _validate_mapping(self.to_mapping())
        except Exception:  # noqa: BLE001
            raise SyntheaConformanceUnavailable(_ERROR_MESSAGE) from None

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> SyntheaEngineManifest:
        """Validate and copy an exact aggregate-only manifest mapping."""
        try:
            if not isinstance(value, Mapping):
                raise TypeError
            copied = dict(value)
            _validate_mapping(copied)
            return cls(**copied)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001
            raise SyntheaConformanceUnavailable(_ERROR_MESSAGE) from None

    @classmethod
    def from_json_bytes(cls, value: bytes) -> SyntheaEngineManifest:
        """Parse strict ASCII JSON and reuse the exact mapping validator."""
        try:
            if not isinstance(value, bytes):
                raise TypeError
            parsed = json.loads(
                value.decode("ascii"),
                object_pairs_hook=_strict_json_object,
                parse_constant=_reject_json_constant,
            )
            if not isinstance(parsed, dict):
                raise TypeError
            return cls.from_mapping(parsed)
        except Exception:  # noqa: BLE001
            raise SyntheaConformanceUnavailable(_ERROR_MESSAGE) from None

    def to_mapping(self) -> dict[str, object]:
        """Return a fresh mapping of immutable scalar values."""
        return {
            "manifest_version": self.manifest_version,
            "engine_id": self.engine_id,
            "engine_revision": self.engine_revision,
            "engine_sha256": self.engine_sha256,
            "module_manifest_sha256": self.module_manifest_sha256,
            "growth_extension_id": self.growth_extension_id,
            "growth_extension_sha256": self.growth_extension_sha256,
            "event_adapter_id": self.event_adapter_id,
            "event_adapter_sha256": self.event_adapter_sha256,
            "ppoc_exporter_id": self.ppoc_exporter_id,
            "ppoc_exporter_sha256": self.ppoc_exporter_sha256,
            "configuration_sha256": self.configuration_sha256,
            "license_notice_id": self.license_notice_id,
            "review_status": self.review_status,
            "test_only": self.test_only,
        }

    def to_json_bytes(self) -> bytes:
        """Serialize canonical sorted ASCII JSON with one trailing newline."""
        return (
            json.dumps(
                self.to_mapping(),
                sort_keys=True,
                ensure_ascii=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("ascii")
            + b"\n"
        )

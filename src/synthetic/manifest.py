from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from synthetic.randomness import PRNG_FAMILY, SEED_DERIVATION_VERSION


@dataclass(frozen=True)
class RunManifest:
    manifest_version: str
    generator_version: str
    profile: str
    engine: str
    seed: int
    schema_fingerprint: str
    reference_time: str
    reference_id: str
    configuration_sha256: str
    software_revision: str
    prng_family: str
    seed_derivation_version: str
    status: str
    reference_sha256: str | None = None
    derivation_fingerprint: str = ""
    test_only_derivation: bool | None = None
    metadata_only: bool = False
    row_counts: dict[str, int] = field(default_factory=dict)
    file_sha256: dict[str, str] = field(default_factory=dict)

    @classmethod
    def smoke(
        cls,
        *,
        seed: int,
        schema_fingerprint: str,
        reference_time: str,
        reference_id: str,
        configuration_sha256: str,
        software_revision: str,
        reference_sha256: str | None = None,
        derivation_fingerprint: str = "",
    ) -> RunManifest:
        if reference_sha256 is not None and re.fullmatch(
            r"[0-9a-f]{64}", reference_sha256
        ) is None:
            raise ValueError(
                "reference_sha256 must be a lowercase 64-character SHA-256 hex digest"
            )
        return cls(
            manifest_version="1",
            generator_version="0.1.0",
            profile="smoke",
            engine="native",
            seed=seed,
            schema_fingerprint=schema_fingerprint,
            reference_time=reference_time,
            reference_id=reference_id,
            reference_sha256=reference_sha256,
            configuration_sha256=configuration_sha256,
            software_revision=software_revision,
            derivation_fingerprint=derivation_fingerprint,
            prng_family=PRNG_FAMILY,
            seed_derivation_version=SEED_DERIVATION_VERSION,
            status="GENERATED_UNVALIDATED",
            metadata_only=True,
        )

    @classmethod
    def generated(
        cls,
        *,
        profile: str,
        seed: int,
        schema_fingerprint: str,
        reference_time: str,
        reference_id: str,
        configuration_sha256: str,
        software_revision: str,
        derivation_fingerprint: str,
        test_only_derivation: bool,
        row_counts: dict[str, int],
        file_sha256: dict[str, str],
        reference_sha256: str | None = None,
        engine: str = "native",
    ) -> RunManifest:
        if type(engine) is not str or engine not in {"native", "synthea"}:
            raise ValueError("engine must be native or synthea")
        if reference_sha256 is not None and re.fullmatch(
            r"[0-9a-f]{64}", reference_sha256
        ) is None:
            raise ValueError(
                "reference_sha256 must be a lowercase 64-character SHA-256 hex digest"
            )
        return cls(
            manifest_version="1",
            generator_version="0.1.0",
            profile=profile,
            engine=engine,
            seed=seed,
            schema_fingerprint=schema_fingerprint,
            reference_time=reference_time,
            reference_id=reference_id,
            reference_sha256=reference_sha256,
            configuration_sha256=configuration_sha256,
            software_revision=software_revision,
            derivation_fingerprint=derivation_fingerprint,
            test_only_derivation=True if test_only_derivation else None,
            prng_family=PRNG_FAMILY,
            seed_derivation_version=SEED_DERIVATION_VERSION,
            status=(
                "STRUCTURE_VALIDATED_TEST_ORACLE"
                if test_only_derivation
                else "STRUCTURE_VALIDATED"
            ),
            metadata_only=False,
            row_counts=row_counts,
            file_sha256=file_sha256,
        )

    def to_json_bytes(self) -> bytes:
        if not self.metadata_only and (not self.row_counts or not self.file_sha256):
            raise ValueError("generated manifests require row_counts and file_sha256")
        mapping = asdict(self)
        if mapping["test_only_derivation"] is not True:
            del mapping["test_only_derivation"]
        return (
            json.dumps(mapping, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        ).encode("utf-8")

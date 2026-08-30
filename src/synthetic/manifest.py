from __future__ import annotations

import json
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
    row_counts: dict[str, int] = field(default_factory=dict)
    file_sha256: dict[str, str] = field(default_factory=dict)
    derivation_oracle: str | None = None

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
    ) -> RunManifest:
        return cls(
            manifest_version="1",
            generator_version="0.1.0",
            profile="smoke",
            engine="native",
            seed=seed,
            schema_fingerprint=schema_fingerprint,
            reference_time=reference_time,
            reference_id=reference_id,
            configuration_sha256=configuration_sha256,
            software_revision=software_revision,
            prng_family=PRNG_FAMILY,
            seed_derivation_version=SEED_DERIVATION_VERSION,
            status="GENERATED_UNVALIDATED",
        )

    def to_json_bytes(self) -> bytes:
        return (
            json.dumps(asdict(self), sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        ).encode("utf-8")

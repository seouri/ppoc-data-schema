from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from synthetic.base_resources import BASE_RESOURCES, build_base_rows
from synthetic.derivation import DerivationOracle, DerivationUnavailable
from synthetic.models import PatientState
from synthetic.native.healthy import HealthyKernel
from synthetic.package_export import (
    PackageExportMetadata,
    _scan_tree,  # noqa: F401 - public import compatibility.
    export_exact_schema_package,
)
from synthetic.randomness import NamedRandomStreams, synthetic_id
from synthetic.references import GrowthReference
from synthetic.schema_contract import load_descriptor


def generate_smoke(
    *,
    descriptor_path: Path,
    output: Path,
    patient_count: int,
    seed: int,
    reference_time: str,
    software_revision: str,
    reference: GrowthReference,
    derivation_oracle: DerivationOracle | None,
    trusted_derivation_fingerprint: str,
    trusted_derivation_test_only: bool,
) -> Path:
    """Generate and atomically promote the exact-schema synthetic smoke package."""
    if patient_count < 1:
        raise ValueError("patient_count must be positive")
    if derivation_oracle is None:
        raise DerivationUnavailable("authoritative derivation oracle is not configured")
    if re.fullmatch(r"[0-9a-f]{64}", trusted_derivation_fingerprint) is None:
        raise ValueError("trusted_derivation_fingerprint must be lowercase SHA-256 hex")
    if trusted_derivation_fingerprint == "0" * 64:
        raise ValueError("trusted_derivation_fingerprint cannot be a placeholder")
    if not isinstance(trusted_derivation_test_only, bool):
        raise TypeError("trusted_derivation_test_only must be a boolean")
    descriptor = load_descriptor(descriptor_path)
    smoke_configuration = {
        "patient_count": patient_count,
        "ages_days": [730, 1095, 1460],
        "profile": "smoke",
    }
    configuration_sha256 = hashlib.sha256(
        json.dumps(smoke_configuration, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    accumulated = {name: [] for name in BASE_RESOURCES}
    kernel = HealthyKernel(reference)
    for patient_index in range(patient_count):
        reference_sex = "F" if patient_index % 2 == 0 else "M"
        patient = PatientState(
            patient_id=synthetic_id(seed, "patient", patient_index),
            recorded_sex=reference_sex,
            reference_sex=reference_sex,
        )
        points = kernel.generate(
            patient,
            ages_days=(730, 1095, 1460),
            streams=NamedRandomStreams(seed, patient_index),
        )
        patient_rows = build_base_rows(descriptor, patient, points, seed=seed + patient_index)
        for name in BASE_RESOURCES:
            accumulated[name].extend(patient_rows[name])

    return export_exact_schema_package(
        descriptor,
        accumulated,
        output,
        metadata=PackageExportMetadata(
            profile="smoke",
            seed=seed,
            reference_time=reference_time,
            reference_id=reference.reference_id,
            reference_sha256=getattr(reference, "source_sha256", None),
            configuration_sha256=configuration_sha256,
            software_revision=software_revision,
        ),
        derivation_oracle=derivation_oracle,
        trusted_derivation_fingerprint=trusted_derivation_fingerprint,
        trusted_derivation_test_only=trusted_derivation_test_only,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--patients", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.parse_args()
    raise SystemExit(
        "No production growth reference or authoritative derivation oracle is configured"
    )


if __name__ == "__main__":
    main()

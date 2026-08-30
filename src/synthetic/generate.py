from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
from pathlib import Path

from synthetic.base_resources import BASE_RESOURCES, build_base_rows
from synthetic.csv_package import write_resource, write_synthetic_descriptor
from synthetic.derivation import DerivationOracle, DerivationUnavailable, require_augmented_outputs
from synthetic.manifest import RunManifest
from synthetic.models import PatientState
from synthetic.native.healthy import HealthyKernel
from synthetic.randomness import NamedRandomStreams, synthetic_id
from synthetic.references import GrowthReference
from synthetic.run_directory import RunDirectory
from synthetic.schema_contract import load_descriptor, resource_spec, schema_fingerprint
from synthetic.validate import validate_structure


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
) -> Path:
    """Generate and atomically promote the exact-schema synthetic smoke package."""
    if patient_count < 1:
        raise ValueError("patient_count must be positive")
    if derivation_oracle is None:
        raise DerivationUnavailable("authoritative derivation oracle is not configured")

    descriptor = load_descriptor(descriptor_path)
    smoke_configuration = {
        "patient_count": patient_count,
        "ages_days": [730, 1095, 1460],
        "profile": "smoke",
    }
    configuration_sha256 = hashlib.sha256(
        json.dumps(smoke_configuration, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    run_id = hashlib.sha256(
        f"{seed}:{patient_count}:{reference_time}".encode()
    ).hexdigest()[:12]
    run = RunDirectory.start(output, run_id)
    try:
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
            patient_rows = build_base_rows(
                descriptor, patient, points, seed=seed + patient_index
            )
            for name in BASE_RESOURCES:
                accumulated[name].extend(patient_rows[name])

        row_counts: dict[str, int] = {}
        for name in BASE_RESOURCES:
            resource = resource_spec(descriptor, name)
            row_counts[name] = write_resource(
                run.partial_path / resource["path"], resource, accumulated[name]
            )

        derivation = derivation_oracle.derive(run.partial_path, descriptor)
        if not derivation.oracle_id:
            raise DerivationUnavailable("derivation oracle returned no identity")
        require_augmented_outputs(
            run.partial_path, descriptor, oracle_id=derivation.oracle_id
        )
        report = validate_structure(run.partial_path, descriptor)
        if report.errors:
            raise ValueError("; ".join(report.errors))
        row_counts.update(report.row_counts)
        write_synthetic_descriptor(run.partial_path, descriptor, row_counts)
        (run.partial_path / "validation-report.json").write_text(
            json.dumps(dataclasses.asdict(report), indent=2) + "\n", encoding="utf-8"
        )

        manifest = RunManifest.smoke(
            seed=seed,
            schema_fingerprint=schema_fingerprint(descriptor),
            reference_time=reference_time,
            reference_id=reference.reference_id,
            configuration_sha256=configuration_sha256,
            software_revision=software_revision,
        )
        file_sha256 = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(run.partial_path.iterdir())
            if path.is_file() and path.name != "manifest.json"
        }
        manifest = dataclasses.replace(
            manifest,
            status=(
                "STRUCTURE_VALIDATED_TEST_ORACLE"
                if derivation.oracle_id.startswith("identity-preserving-test-")
                else "STRUCTURE_VALIDATED"
            ),
            metadata_only=False,
            row_counts=row_counts,
            file_sha256=file_sha256,
        )
        (run.partial_path / "manifest.json").write_bytes(manifest.to_json_bytes())
        return run.promote()
    except Exception as error:
        run.fail(str(error))
        raise


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

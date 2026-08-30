from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import re
import shutil
import tempfile
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
from synthetic.schema_contract import (
    load_descriptor,
    resource_spec,
    schema_fingerprint,
    validate_resource_paths,
)
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
    run_id = hashlib.sha256(
        f"{seed}:{patient_count}:{reference_time}".encode()
    ).hexdigest()[:12]
    run = RunDirectory.start(output, run_id)
    try:
        validate_resource_paths(descriptor, run.partial_path)
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

        with tempfile.TemporaryDirectory(prefix="synthetic-derive-") as staging_name:
            staging = Path(staging_name)
            staging_parent_entries = set(staging.parent.iterdir())
            stage_descriptor = json.loads(json.dumps(descriptor))
            validate_resource_paths(stage_descriptor, staging)
            for name in BASE_RESOURCES:
                resource = resource_spec(descriptor, name)
                source = run.partial_path / resource["path"]
                target = staging / resource["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
            base_hashes = {
                Path(resource_spec(descriptor, name)["path"]).as_posix(): hashlib.sha256(
                    (staging / resource_spec(descriptor, name)["path"]).read_bytes()
                ).hexdigest()
                for name in BASE_RESOURCES
            }
            derivation = derivation_oracle.derive(staging, stage_descriptor)
            unexpected_parent_entries = set(staging.parent.iterdir()) - staging_parent_entries
            if unexpected_parent_entries:
                raise DerivationUnavailable("derivation escaped staging directory")
            if not derivation.oracle_id:
                raise DerivationUnavailable("derivation oracle returned no identity")
            if any(
                hashlib.sha256((staging / path).read_bytes()).hexdigest() != digest
                for path, digest in base_hashes.items()
            ):
                raise DerivationUnavailable("derivation mutated a base resource")
            stage_descriptor = json.loads(json.dumps(descriptor))
            require_augmented_outputs(
                staging, stage_descriptor, oracle_id=derivation.oracle_id
            )
            expected_augmented = {
                Path(resource_spec(descriptor, name)["path"]).as_posix()
                for name in ("patients_augmented", "visits_augmented")
            }
            for path in staging.rglob("*"):
                relative = path.relative_to(staging).as_posix()
                if path.is_symlink() or not path.is_file() or relative not in {
                    *(Path(resource_spec(descriptor, name)["path"]).as_posix() for name in BASE_RESOURCES),
                    *expected_augmented,
                }:
                    raise DerivationUnavailable(f"derivation wrote unexpected artifact: {relative}")
            for name in ("patients_augmented", "visits_augmented"):
                resource = resource_spec(descriptor, name)
                source = staging / resource["path"]
                target = run.partial_path / resource["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as handle:
                    handle.write(source.read_bytes())
        descriptor_names = [item["name"] for item in descriptor["resources"]]
        allowed = {Path(resource_spec(descriptor, name)["path"]).as_posix() for name in descriptor_names}
        for path in run.partial_path.rglob("*"):
            relative = path.relative_to(run.partial_path).as_posix()
            if path.is_symlink() or (path.is_file() and relative not in allowed) or (
                path.is_dir() and relative not in {parent for item in allowed for parent in Path(item).parents if str(parent) != "."}
            ):
                raise DerivationUnavailable(f"unexpected run artifact: {relative}")
        if derivation.implementation_fingerprint != trusted_derivation_fingerprint:
            raise DerivationUnavailable("derivation fingerprint does not match trusted configuration")
        if derivation.implementation_fingerprint == "":
            raise DerivationUnavailable("derivation implementation fingerprint is required")
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
            path.relative_to(run.partial_path).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(run.partial_path.rglob("*"))
            if path.is_file() and not path.is_symlink() and path.name != "manifest.json"
        }
        manifest = dataclasses.replace(
            manifest,
            status="STRUCTURE_VALIDATED_TEST_ORACLE" if trusted_derivation_test_only else "STRUCTURE_VALIDATED",
            derivation_fingerprint=trusted_derivation_fingerprint,
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

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from synthetic.base_resources import BASE_RESOURCES, build_base_rows
from synthetic.cdc_reference import CDC_GENERATION_DOMAIN_POLICY
from synthetic.derivation import DerivationOracle, DerivationUnavailable
from synthetic.derivation_binding import DerivationBinding
from synthetic.development_runtime import (
    build_development_runtime,
    generate_development_cohort,
    generate_development_realistic_cohort,
)
from synthetic.models import PatientState
from synthetic.native.healthy import HealthyKernel
from synthetic.package_export import (
    PackageExportMetadata,
    _require_output_available,
    _scan_tree,  # noqa: F401 - public import compatibility.
    export_exact_schema_package,
)
from synthetic.randomness import NamedRandomStreams, synthetic_id
from synthetic.references import GrowthReference
from synthetic.schema_contract import load_descriptor

CLI_UNAVAILABLE_MESSAGE = "No production growth reference or authoritative derivation oracle is configured"
_DEVELOPMENT_UNAVAILABLE_MESSAGE = "Synthetic development generation unavailable"
_DEVELOPMENT_PROFILES = frozenset(
    {"development-smoke", "development-cohort", "development-realistic"}
)
_AGGREGATE_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_AGGREGATE_IDENTIFIER_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*-[PV]-[0-9]{3,}\b", re.IGNORECASE)
_AGGREGATE_PATH_EXTENSION_RE = re.compile(
    r"\b[A-Za-z0-9_-]+\.(?:csv|tsv|json|parquet|txt|zip|gz)\b", re.IGNORECASE
)
_AGGREGATE_UNSAFE_WORDS = frozenset({"patient", "visit", "path", "key", "identifier"})
_RECORD_INDICATORS = frozenset(
    {"patient", "visit", "identifier", "uuid", "sequence", "truth", "candidate", "match", "row", "resource"}
)


def _metadata_components(value: str) -> tuple[str, ...]:
    acronym_separated = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", acronym_separated)
    return tuple(re.findall(r"[a-z0-9]+", normalized.lower()))


def _contains_indicator_components(value: str, indicators: frozenset[str]) -> bool:
    components = _metadata_components(value)
    for indicator in indicators:
        indicator_components = _metadata_components(indicator)
        width = len(indicator_components)
        if width and any(
            components[index : index + width] == indicator_components
            for index in range(len(components) - width + 1)
        ):
            return True
    return False


def _contains_unsafe_metadata_material(value: str) -> bool:
    return (
        bool(frozenset(_metadata_components(value)) & _AGGREGATE_UNSAFE_WORDS)
        or _AGGREGATE_IDENTIFIER_RE.search(value) is not None
        or "/" in value
        or "\\" in value
        or _AGGREGATE_PATH_EXTENSION_RE.search(value) is not None
    )


def _require_aggregate_safe_token(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")  # noqa: TRY004
    if _AGGREGATE_TOKEN_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be an ASCII token without whitespace or path separators")
    if _contains_unsafe_metadata_material(value):
        raise ValueError(f"{field} must be aggregate-safe")
    if _contains_indicator_components(value, _RECORD_INDICATORS):
        raise ValueError(f"{field} must not contain record or hidden-state indicators")
    return value


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
    derivation_binding: DerivationBinding,
    profile: str = "smoke",
) -> Path:
    """Generate and atomically promote the exact-schema synthetic smoke package."""
    if patient_count < 1:
        raise ValueError("patient_count must be positive")
    if derivation_oracle is None:
        raise DerivationUnavailable("authoritative derivation oracle is not configured")
    profile = _require_aggregate_safe_token(profile, "profile")
    _require_output_available(output)
    descriptor = load_descriptor(descriptor_path)
    smoke_configuration = {
        "patient_count": patient_count,
        "ages_days": [730, 1095, 1460],
        "generation_domain_policy": CDC_GENERATION_DOMAIN_POLICY,
        "profile": profile,
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
            profile=profile,
            seed=seed,
            reference_time=reference_time,
            reference_id=reference.reference_id,
            reference_sha256=getattr(reference, "source_sha256", None),
            configuration_sha256=configuration_sha256,
            software_revision=software_revision,
        ),
        derivation_oracle=derivation_oracle,
        derivation_binding=derivation_binding,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--patients", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--descriptor", type=Path, default=None)
    parser.add_argument("--reference-time", default="2026-09-01T00:00:00Z")
    parser.add_argument("--software-revision", default="development-generator-v1")
    args = parser.parse_args()

    if args.profile not in _DEVELOPMENT_PROFILES:
        raise SystemExit(CLI_UNAVAILABLE_MESSAGE)

    try:
        repository_root = Path(__file__).resolve().parents[2]
        descriptor_path = args.descriptor or repository_root / "datapackage.json"
        runtime = build_development_runtime(repository_root)
        if args.profile == "development-smoke":
            generate_smoke(
                descriptor_path=descriptor_path,
                output=args.output,
                patient_count=args.patients,
                seed=args.seed,
                reference_time=args.reference_time,
                software_revision=args.software_revision,
                reference=runtime.reference,
                derivation_oracle=runtime.derivation_oracle,
                derivation_binding=runtime.derivation_binding,
                profile="development-smoke",
            )
        elif args.profile == "development-cohort":
            generate_development_cohort(
                runtime,
                descriptor_path=descriptor_path,
                output=args.output,
                patient_count=args.patients,
                seed=args.seed,
                reference_time=args.reference_time,
                software_revision=args.software_revision,
            )
        elif args.profile == "development-realistic":
            generate_development_realistic_cohort(
                runtime,
                descriptor_path=descriptor_path,
                output=args.output,
                patient_count=args.patients,
                seed=args.seed,
                reference_time=args.reference_time,
                software_revision=args.software_revision,
            )
        else:
            raise RuntimeError("development profile dispatch is not configured")
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception:  # noqa: BLE001 - CLI failures must not expose implementation details.
        raise SystemExit(_DEVELOPMENT_UNAVAILABLE_MESSAGE) from None


if __name__ == "__main__":
    main()

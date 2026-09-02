# Development-only augmenter oracle

`SourceMatchedAugmenterOracle` is a non-authoritative, test-only adapter for exercising the checked-in, source-matched growth augmenter against a wholly synthetic staged package. It is intended for development and counterfactual experiments only. Do not use real or governed patient data with this adapter.

The adapter is separate from the imported command-line program described in [the imported augmenter guide](augment-import.md). Explicit `development-smoke` and `development-cohort` profiles may compose this test-only adapter through the exact-schema exporter. The default/no-profile and production `synthetic.generate` paths remain fail-closed; the adapter remains wholly synthetic, non-authoritative, and outside governed-data, calibration, privacy, counterfactual, Synthea, or release decisions.

## Install and call the candidate explicitly

From the repository root, install the locked environment:

```sh
uv sync
```

The caller must supply a descriptor mapping, six base-resource row collections that are completely generated, an unused output path, export metadata, the candidate oracle, and a matching explicitly test-only `DerivationBinding`. The example below is copy-pasteable as a function once the caller supplies `fictional_base_rows`; it does not read a patient-data directory.

```python
from collections.abc import Iterable, Mapping
from pathlib import Path

from synthetic.augmenter_oracle import SourceMatchedAugmenterOracle
from synthetic.derivation_binding import DerivationBinding
from synthetic.package_export import PackageExportMetadata, export_exact_schema_package
from synthetic.schema_contract import EXPECTED_SCHEMA_FINGERPRINT, load_descriptor


def export_with_candidate_augmenter(
    repository: Path,
    fictional_base_rows: Mapping[str, Iterable[Mapping[str, object]]],
    fictional_destination: Path,
) -> Path:
    candidate_oracle = SourceMatchedAugmenterOracle(repository)
    candidate_test_binding = DerivationBinding.from_mapping(
        {
            "binding_version": "derivation-binding-v1",
            "binding_id": "augmenter-candidate-test-v1",
            "schema_fingerprint": EXPECTED_SCHEMA_FINGERPRINT,
            "oracle": {
                "oracle_id": candidate_oracle.oracle_id,
                "implementation_fingerprint": candidate_oracle.implementation_fingerprint,
                "source_revision": "copied-runtime-v1",
                "dependency_fingerprint": "c" * 64,
                "source_kind": "approved_parity_harness",
            },
            "reference_standard": {
                "standard_id": "fictional-standard-v1",
                "standard_fingerprint": "b" * 64,
                "version": "fictional-standard-v1",
            },
            "golden_evidence": {
                "manifest_id": None,
                "manifest_fingerprint": None,
                "parity_contract": None,
                "parity_report_id": None,
                "parity_report_fingerprint": None,
                "parity_status": "UNEVALUABLE",
                "candidate_implementation_fingerprint": None,
                "reference_implementation_fingerprint": None,
                "parity_schema_fingerprint": None,
                "covered_categories": [
                    "filter_order",
                    "age_boundaries",
                    "missingness",
                    "harrall_outlier",
                    "biv_filtering",
                    "velocity_variants",
                    "rounding",
                ],
                "bidirectional_case_count": 0,
                "synthetic_fuzz_case_count": 0,
                "fuzz_corpus_fingerprint": None,
            },
            "review": {
                "review_id": None,
                "review_fingerprint": None,
                "reviewed_at": None,
                "reviewer_role": None,
                "status": "PENDING",
            },
            "test_only": True,
        }
    )

    return export_exact_schema_package(
        load_descriptor(repository / "datapackage.json"),
        fictional_base_rows,
        fictional_destination,
        metadata=PackageExportMetadata(
            profile="augmenter-candidate-development",
            seed=20260901,
            reference_time="2026-09-01T00:00:00Z",
            reference_id="fictional-reference-v1",
            reference_sha256="e" * 64,
            configuration_sha256="d" * 64,
            software_revision="local-development-v1",
        ),
        derivation_oracle=candidate_oracle,
        derivation_binding=candidate_test_binding,
    )
```

The binding is deliberately incomplete and `UNEVALUABLE`; its `approved_parity_harness` transport value is one of the binding schema's accepted enumerations, not a claim that this candidate has passed parity or review. Setting `test_only` to false, changing the mapping, or changing the oracle result cannot make the adapter authoritative.

## Runtime and output contract

The fixed oracle identity is `augmenter-cli-v1`. Its implementation fingerprint is the pinned runtime-manifest SHA-256 `b50afc36eca61684380154129cdacf484e62d56fa6da55914adab18c2d94d1d6`. The identity is a bounded aggregate-safe token accepted by the derivation-binding parser. Before each call, the adapter verifies `data/augment-runtime-manifest.json` and its exact 14-file closure as regular, non-symlink files with matching byte counts and hashes.

After verification, the adapter copies that closure into a private temporary runtime snapshot, verifies the copied bytes again, and executes only that snapshot. It invokes the current Python interpreter without a shell, with `-E -s`, the private runtime as the working directory, the exporter's staged package as the only input directory, a separate private output directory, and `--output_format csv`. The candidate accepts CSV only.

The private output directory must contain exactly two regular, non-symlink files: one `visits_augmented-YYYYMMDDHHMMSS.csv` and one `patients_augmented-YYYYMMDDHHMMSS.csv`. No other file, directory, symlink, or duplicate output is accepted. The adapter exclusively copies those two byte streams to the descriptor-named `visits_augmented` and `patients_augmented` paths in the staged package. It never mutates the six base resources.

The exact-schema exporter remains responsible for validating base-resource hashes, output paths, the complete resource schemas, structural relationships, and the final package lifecycle after the oracle returns. The adapter reports a fixed redacted `DerivationUnavailable` error for runtime-integrity, subprocess, timeout, or output-boundary failures; it does not expose captured command output, paths, rows, or identifiers.

## Authority and evidence boundary

Matching the copied source and runtime hash does not prove clinical validity, prevalence or demographic fidelity, privacy or non-matchability, release readiness, or Synthea conformance. It also does not approve the bundled CDC or ICD references as clinical standards. Those remain independent evidence and governance questions.

This candidate cannot become authoritative without independently reviewed reference provenance, parity and golden evidence, synthetic fuzz evidence, clinical review, a matching approved non-test binding, governed calibration and held-out evidence where applicable, privacy evaluation, and release authorization. A Synthea module remains a separate optional route; this adapter is not a Synthea module or conformance test.

The `synthetic.generate` production command remains fail closed with `No production growth reference or authoritative derivation oracle is configured`. The production command has no configured authoritative oracle, and this development adapter does not change that boundary.

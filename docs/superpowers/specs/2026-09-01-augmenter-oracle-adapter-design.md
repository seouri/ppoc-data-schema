# Source-Matched Augmenter Oracle Adapter Design

**Date:** 2026-09-01
**Status:** Approved development-only roadmap slice
**Parent:** [Imported growth augmenter](2026-09-01-augment-import-design.md)
**Prerequisites:** the exact-schema package exporter, the derivation-binding contract, and the byte-preserved `scripts/augment.py` runtime closure

## Purpose

The repository now contains the supplied growth augmenter and its non-patient
runtime references, but the native package exporter still requires a caller
supplied derivation oracle. This slice adds a narrow adapter that can exercise
the imported CLI against a package-exporter's already staged synthetic base
resources. It makes the candidate usable in development and counterfactual
experiments without changing the native generator's fail-closed command or
claiming that the imported implementation is authoritative.

## Public interface

Add `synthetic.augmenter_oracle.SourceMatchedAugmenterOracle`:

```python
class SourceMatchedAugmenterOracle:
    oracle_id: str
    implementation_fingerprint: str

    def __init__(
        self,
        repository_root: Path | None = None,
        *,
        timeout_seconds: float = 300.0,
    ) -> None: ...

    def derive(
        self,
        package_root: Path,
        descriptor: dict[str, Any],
    ) -> DerivationResult: ...
```

The default repository root is the checkout containing the adapter. An
explicit root is useful for tests and local checkouts, but it is a runtime
code root, not a patient-data or governed-data input. The adapter's stable
oracle identity is `growth-augmenter-cli-v1`; its implementation fingerprint
is the pinned SHA-256 of `data/augment-runtime-manifest.json`. It always
returns `DerivationResult(..., test_only=True)`.

The adapter remains a `DerivationOracle` candidate. It does not supply an
approved non-test `DerivationBinding`, change `generate.py`, or make the
production `synthetic.generate` command runnable.

## Runtime contract

Before invoking the CLI, the adapter verifies the pinned runtime manifest and
every listed file as a regular, non-symlink file with the recorded byte count
and SHA-256 digest. It rejects a changed manifest, missing reference, helper,
or script file before starting a subprocess. It then copies the verified
14-file closure into a private temporary runtime root, rechecks every copied
byte against the same manifest, and executes only that snapshot. This closes
the replace-between-check-and-use window without changing the supplied source
bytes. The manifest digest is the implementation fingerprint so a changed
runtime cannot silently retain the same binding identity.

`derive` accepts only the package root supplied by the exporter. It rejects a
missing, non-directory, or symlink package root and never accepts a separate
input or output data root. It runs the preserved CLI without a shell using
the current Python interpreter, `-E -s` isolation flags, the private runtime
root as `cwd`, the package root as `input_dir`, a private temporary output
directory, and the fixed `--output_format csv` option. The command is
equivalent to:

```text
<interpreter> -E -s <runtime-root>/scripts/augment.py <staged-package-root> \
  --output_dir <private-temporary-output> --output_format csv
```

The subprocess has a finite configured timeout, captures stdout/stderr only
for local diagnostics, and exposes no command output or path in a raised
exception. Nonzero exit, timeout, unavailable interpreter, malformed output,
or runtime-integrity failure raises the fixed `DerivationUnavailable`
boundary error.

The temporary output directory must contain exactly two regular, non-symlink
CSV files matching one each of
`visits_augmented-YYYYMMDDHHMMSS.csv` and
`patients_augmented-YYYYMMDDHHMMSS.csv`. The two files' bytes are copied into
the descriptor paths `visits_augmented` and `patients_augmented` beneath the
staged package root using exclusive creation. Any extra file, directory,
symlink, duplicate timestamped output, pre-existing destination, or unsafe
descriptor path fails closed. The adapter does not mutate any base resource;
the existing package exporter remains responsible for hash, schema, and
structural validation after the oracle returns.

## Boundary and safety

- The adapter is development-only and test-only. It does not infer latent
  disease, calibrate prevalence, establish demographic fidelity, or provide
  clinical, privacy, non-matchability, release, or Synthea evidence.
- It runs only the checked-in CLI and bundled reference files. It never reads
  PPOC records, calibration/held-out/privacy artifacts, network resources, or
  a caller-selected real-data root.
- It does not import the native generator, package exporter, calibration,
  held-out, privacy, counterfactual, or Synthea modules; the exporter calls it
  only through the existing `DerivationOracle` protocol.
- The adapter never serializes subprocess output, input paths, rows, patient
  identifiers, diagnosis values, or runtime internals. Public failures use
  fixed redacted text from the existing derivation/package boundary.
- A caller must supply a test-only binding whose oracle identity and
  implementation fingerprint match this adapter. Changing `test_only=False`
  or mutating binding metadata cannot make it authoritative; the existing
  binding and review gates remain required.

## Verification and documentation

Focused tests use temporary, wholly synthetic exact-schema package roots and
cover successful CSV derivation, exact output mapping, unchanged base hashes,
runtime-manifest tampering, nonzero exit, timeout, extra artifacts, symlink
outputs, output collisions, and redacted failures. A subprocess invocation is
tested rather than importing the byte-preserved script as a Python package.
Boundary tests confirm the adapter is not imported by visible generation or
evaluator modules and that the production CLI still fails closed.

Documentation shows the explicit candidate-oracle call and its required
test-only binding, labels the runtime as non-authoritative, and points to the
existing imported-augmenter guide. It must not present the adapter as a
clinical reference, a prevalence calibrator, a privacy proof, or a release
path.

## Deferred work

This slice does not approve the bundled CDC/ICD tables as clinical standards,
bind the adapter as an authoritative oracle, enable cohort-scale production
generation, or add a Synthea module. Those require independently verified
reference provenance, parity and golden evidence, clinical review, governed
calibration/held-out evidence, privacy evaluation, release authorization, and
engine-conformance work under their separate gates.

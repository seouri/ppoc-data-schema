# PPOC Synthea overlay

This directory is a versioned, completely fictional, development-only overlay
for the optional Synthea bridge. It contains one Generic Module Framework
module that samples a growth-hormone-deficiency event and emits an evaluation
encounter with two observations. `E23.0` is a fictional development token for
the local augmenter; it is not a clinical diagnosis or a claim about ICD-10-CM
coding, prevalence, or patient data.

The bridge copies this overlay into a private temporary Synthea build root.
It never modifies a caller checkout, reads real data, or publishes this
directory as a Synthea release module. The Python adapter applies its separate
bounded growth overlay to parsed anthropometry; that adapter-layer behavior is
documented in `docs/superpowers/specs/2026-09-03-synthea-backend-design.md`.

This module is not clinical and does not establish Synthea conformance,
population fidelity, privacy/non-matchability, or release authorization.

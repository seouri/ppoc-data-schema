# PPOC Synthea overlay

This directory is a versioned, completely fictional, development-only overlay
for the optional Synthea bridge. It contains one Generic Module Framework
module that samples a growth-hormone-deficiency event and emits an evaluation
encounter with two observations. `E23.0` is a valid ICD-10-CM code used only as
a completely synthetic development diagnosis; its occurrence is not a clinical
diagnosis or a claim about prevalence or patient data. The local evaluator
placeholders used by the native observation contract are translated to valid
ICD-10-CM codes at exact-schema CSV serialization.

The bridge copies this overlay into a private temporary Synthea build root.
It never modifies a caller checkout, reads real data, or publishes this
directory as a Synthea release module. The Python adapter applies its separate
bounded growth overlay to parsed anthropometry; that adapter-layer behavior is
documented in `docs/superpowers/specs/2026-09-03-synthea-backend-design.md`.

This module is not clinical and does not establish Synthea conformance,
population fidelity, privacy/non-matchability, or release authorization.

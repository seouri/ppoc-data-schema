from __future__ import annotations

import json

from synthetic.native.ancillary_bundle import (
    ANCILLARY_BUNDLE_CHECK_NAMES,
    AncillaryBundleValidationStatus,
    validate_ghd_ancillary_bundle,
)
from synthetic.native.resources import ObservedResourceBundle, validate_observed_resources
from tests.synthetic.test_ancillary_bundle_merge import _merge_inputs, _policy


def _check(report: object, name: str) -> tuple[str, str]:
    item = next(check for check in report.checks if check.name == name)  # type: ignore[union-attr]
    return item.status.value, item.reason_code


def _enriched_bundle(base: object, projection: object) -> ObservedResourceBundle:
    rows = dict(base.rows)  # type: ignore[union-attr]
    for name, resource_rows in projection.rows.items():  # type: ignore[union-attr]
        rows[name] = resource_rows
    return ObservedResourceBundle(
        base.patient_id,  # type: ignore[union-attr]
        base.shape,  # type: ignore[union-attr]
        rows,
        base.clinical_descendants,  # type: ignore[union-attr]
        base.source_frame,  # type: ignore[union-attr]
    )


def test_full_bundle_validator_passes_clean_ghd_and_empty_pathways_with_fixed_aggregate_output() -> None:
    member, base, projection = _merge_inputs()
    from synthetic.native.ancillary_bundle import merge_ghd_ancillary_resources

    merged = merge_ghd_ancillary_resources(base, member, projection, _policy())
    healthy_member, healthy_base, _healthy_projection = _merge_inputs(recognized=False)

    report = validate_ghd_ancillary_bundle(merged, member, _policy())
    empty_report = validate_ghd_ancillary_bundle(healthy_base, healthy_member, _policy())

    assert report.status is AncillaryBundleValidationStatus.PASS
    assert empty_report.status is AncillaryBundleValidationStatus.PASS
    assert tuple(check.name for check in report.checks) == ANCILLARY_BUNDLE_CHECK_NAMES
    assert all(check.status is AncillaryBundleValidationStatus.PASS for check in report.checks)
    assert report.to_mapping() == validate_ghd_ancillary_bundle(merged, member, _policy()).to_mapping()
    rendered = repr(report) + json.dumps(report.to_mapping(), sort_keys=True)
    assert member.demographics.patient_id not in rendered
    assert "source_frame" not in rendered
    assert "latent_trajectory" not in rendered
    assert validate_observed_resources(merged).status.value == "FAIL"


def test_full_bundle_validator_fails_visible_base_and_ancillary_tampering_without_payloads() -> None:
    mutations = (
        ("base_resources", "visits", 0, "visit_id", "syn-unlinked"),
        ("ancillary_resources", "labs", 0, "visit_id", "syn-unlinked"),
        ("ancillary_resources", "labs", 0, "lab_result_date_age_in_days", 0),
        ("ancillary_resources", "labs", 0, "result_component_name", "SYN-WRONG"),
        ("ancillary_resources", "problem_list", 0, "patient_id", "syn-other-patient"),
    )
    for expected_check, resource_name, index, field_name, replacement in mutations:
        member, base, projection = _merge_inputs()
        from synthetic.native.ancillary_bundle import merge_ghd_ancillary_resources

        merged = merge_ghd_ancillary_resources(base, member, projection, _policy())
        row = merged.rows[resource_name][index]
        object.__setattr__(
            row,
            "values",
            tuple((name, replacement if name == field_name else value) for name, value in row.values),
        )

        report = validate_ghd_ancillary_bundle(merged, member, _policy())

        assert report.status is AncillaryBundleValidationStatus.FAIL
        assert _check(report, expected_check)[0] == "FAIL"
        rendered = repr(report) + json.dumps(report.to_mapping(), sort_keys=True)
        if isinstance(replacement, str):
            assert replacement not in rendered
        assert member.demographics.patient_id not in rendered

    member, base, projection = _merge_inputs()
    from synthetic.native.ancillary_bundle import merge_ghd_ancillary_resources

    merged = merge_ghd_ancillary_resources(base, member, projection, _policy())
    lab = merged.rows["labs"][0]
    object.__setattr__(lab, "values", tuple(reversed(lab.values)))
    report = validate_ghd_ancillary_bundle(merged, member, _policy())
    assert report.status is AncillaryBundleValidationStatus.FAIL
    assert _check(report, "ancillary_resources")[0] == "FAIL"


def test_full_bundle_validator_suppresses_hidden_treatment_and_marks_missing_evidence_unevaluable() -> None:
    untreated_member, untreated_base, untreated_projection = _merge_inputs(treatment=False)
    treated_member, _, treated_projection = _merge_inputs(treatment=True)
    assert untreated_member.demographics.patient_id == treated_member.demographics.patient_id
    assert untreated_base.source_frame is untreated_member.frame

    enriched = _enriched_bundle(untreated_base, treated_projection)
    report = validate_ghd_ancillary_bundle(enriched, untreated_member, _policy())
    assert report.status is AncillaryBundleValidationStatus.FAIL
    assert _check(report, "ancillary_resources")[0] == "FAIL"

    from synthetic.native.ancillary_bundle import merge_ghd_ancillary_resources

    merged = merge_ghd_ancillary_resources(untreated_base, untreated_member, untreated_projection, _policy())
    object.__setattr__(merged.source_frame, "truth", None)
    unevaluable = validate_ghd_ancillary_bundle(merged, untreated_member, _policy())
    assert unevaluable.status is AncillaryBundleValidationStatus.UNEVALUABLE
    assert _check(unevaluable, "base_resources")[0] == "UNEVALUABLE"
    assert _check(unevaluable, "ancillary_resources")[0] == "UNEVALUABLE"

    object.__setattr__(merged, "source_frame", None)
    absent = validate_ghd_ancillary_bundle(merged, untreated_member, _policy())
    assert absent.status is AncillaryBundleValidationStatus.UNEVALUABLE
    assert _check(absent, "bundle_identity")[0] == "UNEVALUABLE"


def test_full_bundle_validator_marks_a_shared_malformed_private_frame_unevaluable() -> None:
    member, base, projection = _merge_inputs()
    from synthetic.native.ancillary_bundle import merge_ghd_ancillary_resources

    merged = merge_ghd_ancillary_resources(base, member, projection, _policy())
    opaque_frame = object()
    object.__setattr__(member, "frame", opaque_frame)
    object.__setattr__(merged, "source_frame", opaque_frame)

    report = validate_ghd_ancillary_bundle(merged, member, _policy())

    assert report.status is AncillaryBundleValidationStatus.UNEVALUABLE
    assert _check(report, "bundle_identity") == ("UNEVALUABLE", "INSUFFICIENT_EVIDENCE")
    assert _check(report, "base_resources") == ("UNEVALUABLE", "INSUFFICIENT_EVIDENCE")


def test_full_bundle_validator_keeps_visible_base_failures_above_malformed_private_evidence() -> None:
    member, base, projection = _merge_inputs()
    from synthetic.native.ancillary_bundle import merge_ghd_ancillary_resources

    merged = merge_ghd_ancillary_resources(base, member, projection, _policy())
    visit = merged.rows["visits"][0]
    object.__setattr__(
        visit,
        "values",
        tuple((name, "syn-unlinked" if name == "visit_id" else value) for name, value in visit.values),
    )
    opaque_frame = object()
    object.__setattr__(member, "frame", opaque_frame)
    object.__setattr__(merged, "source_frame", opaque_frame)

    report = validate_ghd_ancillary_bundle(merged, member, _policy())

    assert report.status is AncillaryBundleValidationStatus.FAIL
    assert _check(report, "bundle_identity") == ("UNEVALUABLE", "INSUFFICIENT_EVIDENCE")
    assert _check(report, "base_resources") == ("FAIL", "BASE_RESOURCES_INVALID")


def test_full_bundle_validator_rejects_nested_private_values_without_rendering_them() -> None:
    member, base, projection = _merge_inputs()
    from synthetic.native.ancillary_bundle import merge_ghd_ancillary_resources

    merged = merge_ghd_ancillary_resources(base, member, projection, _policy())
    lab = merged.rows["labs"][0]
    object.__setattr__(
        lab,
        "values",
        tuple((name, member.frame if name == "result_value" else value) for name, value in lab.values),
    )

    report = validate_ghd_ancillary_bundle(merged, member, _policy())

    assert report.status is AncillaryBundleValidationStatus.FAIL
    assert _check(report, "truth_boundary") == ("FAIL", "TRUTH_BOUNDARY_INVALID")
    rendered = repr(report) + json.dumps(report.to_mapping(), sort_keys=True)
    assert "ObservationFrame" not in rendered
    assert member.demographics.patient_id not in rendered


def test_full_bundle_validator_returns_redacted_unevaluable_report_for_malformed_typed_input() -> None:
    report = validate_ghd_ancillary_bundle(object(), object(), object())

    assert report.status is AncillaryBundleValidationStatus.UNEVALUABLE
    assert tuple(check.name for check in report.checks) == ANCILLARY_BUNDLE_CHECK_NAMES
    assert all(check.status is AncillaryBundleValidationStatus.UNEVALUABLE for check in report.checks)
    assert "object at" not in repr(report)

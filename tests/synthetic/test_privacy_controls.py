from __future__ import annotations

import csv
from pathlib import Path
from types import MappingProxyType

from synthetic.privacy_audit import (
    PrivacyPolicy,
    _evaluate_exact_reproduction_control,
    _evaluate_identifier_overlap_control,
    _evaluate_linkage_control,
    _evaluate_nearest_neighbor_control,
    _load_private_package,
    _PrivatePackage,
    _PrivatePatientProfile,
)
from synthetic.schema_contract import field_names, load_descriptor, resource_spec
from tests.synthetic.calibration_fixtures import write_mock_snapshot, write_synthetic_descriptor
from tests.synthetic.privacy_fixtures import (
    policy_mapping,
    write_generated_package,
    write_real_package,
)


def _policy(**changes: object) -> PrivacyPolicy:
    return PrivacyPolicy.from_mapping(policy_mapping(**changes))


def _private_profile(label: str, components: tuple[str, str, str, str, str], *, sex: str = "F") -> _PrivatePatientProfile:
    return _PrivatePatientProfile(
        _patient_id=f"test-{label}",
        _demographics=(sex, components[0]),
        _ages=(100, 800, 3500),
        _visit_count=3,
        _trajectory=((100, 1.0, 1.0, 1.0),) * 3,
        _growth_dx_flag=components[4],
        _trajectory_signature=f"trajectory-{label}",
        _profile_signature=f"profile-{label}",
        _component_buckets=MappingProxyType(
            dict(zip(("demographics", "timing", "utilization", "trajectory", "diagnosis"), components))
        ),
    )


def _private_package(profiles: tuple[_PrivatePatientProfile, ...]) -> _PrivatePackage:
    return _PrivatePackage(
        patient_count=len(profiles),
        _identifier_values=frozenset(f"test-id-{index}" for index in range(len(profiles))),
        _profiles=profiles,
        _trajectory_signatures=frozenset(profile._trajectory_signature for profile in profiles),
        _profile_signatures=frozenset(profile._profile_signature for profile in profiles),
        _ineligible_profile_count=0,
    )


def _copy_identifier_from_reference(package: Path, resource_name: str, field_name: str) -> None:
    """Copy one governed identifier namespace while preserving fixture link validity."""
    descriptor = load_descriptor(package / "datapackage.json")
    source = package / resource_spec(descriptor, resource_name)["path"]
    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        assert rows and rows[0][field_name]
        fields = tuple(rows[0])
    generated_value = rows[0][field_name]
    copied_value = generated_value.replace("GEN-", "REAL-", 1)
    rows[0][field_name] = copied_value
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    if field_name == "visit_id":
        for name in ("visits", "visits_augmented"):
            path = package / resource_spec(descriptor, name)["path"]
            with path.open(newline="", encoding="utf-8") as handle:
                linked_rows = list(csv.DictReader(handle))
                linked_fields = tuple(linked_rows[0])
            for row in linked_rows:
                if row["visit_id"] == generated_value:
                    row["visit_id"] = copied_value
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=linked_fields)
                writer.writeheader()
                writer.writerows(linked_rows)
    if field_name != "patient_id":
        return
    for resource in descriptor["resources"]:
        assert isinstance(resource, dict)
        name = resource["name"]
        assert isinstance(name, str)
        if "patient_id" not in field_names(descriptor, name):
            continue
        path = package / resource_spec(descriptor, name)["path"]
        with path.open(newline="", encoding="utf-8") as handle:
            linked_rows = list(csv.DictReader(handle))
            linked_fields = tuple(linked_rows[0])
        for row in linked_rows:
            if row["patient_id"] == generated_value:
                row["patient_id"] = copied_value
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=linked_fields)
            writer.writeheader()
            writer.writerows(linked_rows)


def _shift_trajectory(package: Path) -> None:
    """Make fixture trajectories independent without exposing them to a control result."""
    descriptor = load_descriptor(package / "datapackage.json")
    path = package / resource_spec(descriptor, "visits_augmented")["path"]
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        assert rows and rows[0]
        fields = tuple(rows[0])
    for row in rows:
        for name in ("height_cm", "weight_kg", "head_circ_cm"):
            if row[name]:
                row[name] = str(float(row[name]) + 100.0)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _package(
    root: Path,
    *,
    synthetic: bool,
    prefix: str,
    independent: bool = False,
    patient_count: int = 12,
):
    if synthetic and patient_count != 12:
        package = write_mock_snapshot(root, id_prefix=prefix, patient_count=patient_count)
        write_synthetic_descriptor(package)
    else:
        package = (
            write_generated_package(root, id_prefix=prefix)
            if synthetic
            else write_real_package(root, id_prefix=prefix)
        )
    if independent:
        _shift_trajectory(package)
    return _load_private_package(package, synthetic=synthetic, longitudinal_minimum=3)


def test_mandatory_controls_fail_for_copied_identifiers_and_eligible_trajectories(
    tmp_path: Path,
) -> None:
    """Catches removing either mandatory zero-overlap/reproduction gate."""
    policy = _policy()
    reference = _package(tmp_path / "real", synthetic=False, prefix="COPY")
    generated = _package(tmp_path / "generated", synthetic=True, prefix="COPY")

    identifier = _evaluate_identifier_overlap_control(policy, reference, generated)
    reproduction = _evaluate_exact_reproduction_control(policy, reference, generated)

    assert identifier.status == reproduction.status == "FAIL"
    assert identifier.reason_code == "identifier_overlap_detected"
    assert reproduction.reason_code == "exact_reproduction_detected"
    assert (
        identifier.metrics["overlap_rate"] == reproduction.metrics["exact_reproduction_rate"] == 1.0
    )
    for result in (identifier, reproduction):
        text = repr(result)
        assert "COPY-P-001" not in text
        assert "sha256" not in text.lower()


def test_identifier_overlap_covers_every_primary_key_and_id_namespace(tmp_path: Path) -> None:
    """Catches narrowing overlap checks to patient IDs or a subset of exact-schema resources."""
    policy = _policy()
    descriptor = load_descriptor(Path(__file__).resolve().parents[2] / "datapackage.json")
    namespaces: list[tuple[str, str]] = []
    for resource in descriptor["resources"]:
        assert isinstance(resource, dict)
        name = resource["name"]
        assert isinstance(name, str)
        primary_key = resource["schema"].get("primaryKey")
        primary_fields = (primary_key,) if isinstance(primary_key, str) else tuple(primary_key or ())
        namespaces.extend(
            (name, field)
            for field in set(primary_fields) | {field for field in field_names(descriptor, name) if field.endswith("_id")}
        )
    reference = _package(tmp_path / "reference", synthetic=False, prefix="REAL", independent=True)

    for index, (resource_name, field_name) in enumerate(namespaces):
        package = write_generated_package(tmp_path / f"generated-{index}", id_prefix="GEN")
        _copy_identifier_from_reference(package, resource_name, field_name)
        generated = _load_private_package(package, synthetic=True, longitudinal_minimum=3)
        result = _evaluate_identifier_overlap_control(policy, reference, generated)

        assert result.status == "FAIL"
        assert result.reason_code == "identifier_overlap_detected"
        assert result.metrics["overlap_count"] >= 1
        assert "REAL-" not in repr(result)


def test_mandatory_controls_are_unevaluable_for_underpowered_evidence(tmp_path: Path) -> None:
    """Catches treating too few patients or trajectories as passing privacy evidence."""
    policy = _policy(minimum_evaluable_patients=13)
    reference = _package(tmp_path / "real", synthetic=False, prefix="REAL")
    generated = _package(tmp_path / "generated", synthetic=True, prefix="GEN", independent=True)

    identifier = _evaluate_identifier_overlap_control(policy, reference, generated)
    reproduction = _evaluate_exact_reproduction_control(policy, reference, generated)

    assert identifier.status == reproduction.status == "UNEVALUABLE"
    assert identifier.metrics == reproduction.metrics == {}
    assert identifier.reason_code == reproduction.reason_code == "insufficient_evidence"


def test_nearest_neighbor_requires_heldout_and_returns_only_aggregate_metrics(
    tmp_path: Path,
) -> None:
    """Catches accepting a required screen without its held-out comparison."""
    thresholds = policy_mapping()["thresholds"]
    assert isinstance(thresholds, dict)
    policy = _policy(
        required_controls=["exact_reproduction", "identifier_overlap", "nearest_neighbor"],
        thresholds=thresholds | {"nearest_neighbor_unique_rate": 1.0},
    )
    reference = _package(tmp_path / "real", synthetic=False, prefix="REAL")
    generated = _package(tmp_path / "generated", synthetic=True, prefix="GEN", independent=True)
    heldout = _package(tmp_path / "heldout", synthetic=False, prefix="HLD", independent=True)

    missing = _evaluate_nearest_neighbor_control(policy, reference, generated, heldout=None)
    first = _evaluate_nearest_neighbor_control(policy, reference, generated, heldout=heldout)
    second = _evaluate_nearest_neighbor_control(policy, reference, generated, heldout=heldout)

    assert missing.status == "UNEVALUABLE"
    assert missing.reason_code == "heldout_required"
    assert first == second
    assert first.status == "PASS"
    assert set(first.metrics) == {
        "evaluated_count",
        "heldout_count",
        "heldout_unique_nearest_rate",
        "heldout_zero_proximity_rate",
        "margin_positive_rate",
        "margin_zero_rate",
        "rate_ci_lower",
        "rate_ci_upper",
        "unique_nearest_rate",
        "zero_proximity_rate",
    }
    assert 0 <= first.metrics["rate_ci_lower"] <= first.metrics["zero_proximity_rate"] <= 1
    assert "REAL-P-001" not in repr(first)
    assert "distance" not in repr(first).lower()


def test_heldout_baselines_query_heldout_profiles_against_reference_only() -> None:
    """Catches orienting a held-out baseline as generated queries against held-out candidates."""
    policy = _policy(
        required_controls=["exact_reproduction", "identifier_overlap", "linkage", "nearest_neighbor"],
        subgroups=["overall"],
        thresholds=policy_mapping()["thresholds"] | {
            "linkage_advantage": 1.0,
            "nearest_neighbor_unique_rate": 1.0,
            "nearest_neighbor_zero_rate": 1.0,
        },
    )
    reference = _private_package(
        tuple(_private_profile(f"r{index}", tuple(f"ref-{component}-{index}" for component in "dturx")) for index in range(3))
    )
    generated = _private_package(
        tuple(_private_profile(f"g{index}", tuple(f"shared-{component}-{index}" for component in "dturx")) for index in range(3))
    )
    heldout = _private_package(
        tuple(_private_profile(f"h{index}", tuple(f"shared-{component}-{index}" for component in "dturx")) for index in range(3))
    )

    nearest = _evaluate_nearest_neighbor_control(policy, reference, generated, heldout=heldout)
    linkage = _evaluate_linkage_control(policy, reference, generated, heldout=heldout)

    assert nearest.metrics["heldout_zero_proximity_rate"] == 0.0
    assert linkage.metrics["heldout_unique_candidate_rate"] == 0.0


def test_heldout_nearest_baseline_cannot_hide_a_raw_threshold_failure() -> None:
    """Catches treating a high held-out baseline as permission to pass a raw nearest-neighbor risk."""
    policy = _policy(
        subgroups=["overall"],
        thresholds=policy_mapping()["thresholds"]
        | {"nearest_neighbor_zero_rate": 0.0, "nearest_neighbor_unique_rate": 1.0},
    )
    reference = _private_package(
        tuple(_private_profile(f"r{index}", tuple(f"v-{component}-{index}" for component in "dturx")) for index in range(3))
    )
    generated = _private_package(
        tuple(_private_profile(f"g{index}", tuple(f"v-{component}-{index}" for component in "dturx")) for index in range(3))
    )
    heldout = _private_package(
        tuple(_private_profile(f"h{index}", tuple(f"v-{component}-{index}" for component in "dturx")) for index in range(3))
    )

    without_heldout = _evaluate_nearest_neighbor_control(policy, reference, generated, heldout=None)
    with_heldout = _evaluate_nearest_neighbor_control(policy, reference, generated, heldout=heldout)

    assert without_heldout.status == "FAIL"
    assert with_heldout.status == "FAIL"
    assert with_heldout.metrics["zero_proximity_rate"] == 1.0
    assert with_heldout.metrics["heldout_zero_proximity_rate"] == 1.0


def test_linkage_uses_fixed_components_and_heldout_permutation_baselines(tmp_path: Path) -> None:
    """Catches omitting held-out/permutation baselines or leaking component values."""
    policy = _policy(
        required_controls=["exact_reproduction", "identifier_overlap", "linkage"],
        thresholds=policy_mapping()["thresholds"] | {"linkage_advantage": 1.0},
    )
    reference = _package(tmp_path / "real", synthetic=False, prefix="REAL")
    generated = _package(tmp_path / "generated", synthetic=True, prefix="GEN", independent=True)
    heldout = _package(tmp_path / "heldout", synthetic=False, prefix="HLD", independent=True)

    missing = _evaluate_linkage_control(policy, reference, generated, heldout=None)
    first = _evaluate_linkage_control(policy, reference, generated, heldout=heldout)
    second = _evaluate_linkage_control(policy, reference, generated, heldout=heldout)

    assert missing.status == "UNEVALUABLE"
    assert missing.reason_code == "heldout_required"
    assert first == second
    assert first.status == "PASS"
    assert set(first.metrics) == {
        "evaluated_count",
        "heldout_count",
        "heldout_unique_candidate_rate",
        "linkage_advantage",
        "permutation_unique_rate",
        "rate_ci_lower",
        "rate_ci_upper",
        "unique_candidate_rate",
    }
    assert first.metrics["linkage_advantage"] == 0.0
    assert "demographics" not in repr(first)
    assert "REAL-P-001" not in repr(first)


def test_optional_nearest_and_linkage_evaluate_without_heldout_against_fixed_baselines(
    tmp_path: Path,
) -> None:
    """Catches treating optional controls as unevaluable when their fixed baseline is available."""
    thresholds = policy_mapping()["thresholds"]
    assert isinstance(thresholds, dict)
    policy = _policy(
        thresholds=thresholds
        | {
            "linkage_advantage": 1.0,
            "nearest_neighbor_unique_rate": 1.0,
            "nearest_neighbor_zero_rate": 1.0,
        }
    )
    reference = _package(tmp_path / "real", synthetic=False, prefix="REAL")
    generated = _package(tmp_path / "generated", synthetic=True, prefix="GEN", independent=True)

    nearest = _evaluate_nearest_neighbor_control(policy, reference, generated, heldout=None)
    linkage = _evaluate_linkage_control(policy, reference, generated, heldout=None)

    assert nearest.status == linkage.status == "PASS"
    assert nearest.reason_code == "nearest_neighbor_reference_only"
    assert linkage.reason_code == "linkage_reference_permutation_only"
    assert "heldout_count" not in nearest.metrics
    assert "heldout_unique_candidate_rate" not in linkage.metrics


def test_nearest_neighbor_reports_exact_near_unique_and_tied_buckets_without_overcounting() -> None:
    """Catches counting a reference candidate more than once across matching component buckets."""
    policy = _policy(
        thresholds=policy_mapping()["thresholds"]
        | {"nearest_neighbor_zero_rate": 0.2, "nearest_neighbor_unique_rate": 1.0}
    )
    reference = _private_package(
        (
            _private_profile("r0", ("same", "a", "a", "a", "a")),
            _private_profile("r1", ("same", "b", "b", "b", "b")),
            _private_profile("r2", ("other", "c", "c", "c", "c")),
        )
    )
    generated = _private_package(
        (
            _private_profile("g0", ("same", "a", "a", "a", "a")),
            _private_profile("g1", ("same", "a", "a", "a", "new")),
            _private_profile("g2", ("same", "new", "new", "new", "new")),
        )
    )

    result = _evaluate_nearest_neighbor_control(policy, reference, generated, heldout=None)

    assert result.status == "FAIL"
    assert result.reason_code == "zero_proximity_threshold_exceeded"
    assert result.metrics["zero_proximity_rate"] == round(1 / 3, 6)
    assert result.metrics["unique_nearest_rate"] == round(2 / 3, 6)
    assert result.metrics["margin_zero_rate"] == round(1 / 3, 6)


def test_linkage_full_combination_uses_permutation_and_heldout_rates(tmp_path: Path) -> None:
    """Catches omitting the full-combination signal or either reported baseline rate."""
    policy = _policy(
        required_controls=["exact_reproduction", "identifier_overlap", "linkage"],
        subgroups=["overall"],
    )
    reference = _private_package(
        tuple(
            _private_profile(f"r{index}", tuple(f"{component}{index}" for component in "dturx"))
            for index in range(3)
        )
    )
    generated = _private_package(
        tuple(
            _private_profile(f"g{index}", tuple(f"{component}{index}" for component in "dturx"))
            for index in range(3)
        )
    )
    heldout = _private_package(
        tuple(
            _private_profile(f"h{index}", tuple(f"held-{component}{index}" for component in "dturx"))
            for index in range(3)
        )
    )

    result = _evaluate_linkage_control(policy, reference, generated, heldout=heldout)

    assert result.status == "FAIL"
    assert result.reason_code == "linkage_threshold_exceeded"
    assert result.metrics["unique_candidate_rate"] == 1.0
    assert result.metrics["permutation_unique_rate"] == 0.0
    assert result.metrics["heldout_unique_candidate_rate"] == 0.0
    assert result.metrics["linkage_advantage"] == 1.0


def test_linkage_promotes_an_evaluable_subgroup_failure_without_reporting_subgroups() -> None:
    """Catches ignoring a failing evaluable subgroup or exporting its private cell."""
    policy = _policy(thresholds=policy_mapping()["thresholds"] | {"linkage_advantage": 0.75})
    reference = _private_package(
        tuple(
            _private_profile(f"r{index}", tuple(f"{component}{index}" for component in "dturx"))
            for index in range(6)
        )
    )
    generated = _private_package(
        tuple(
            _private_profile(
                f"g{index}",
                tuple(f"{component}{index}" for component in "dturx")
                if index < 3
                else tuple(f"none-{component}{index}" for component in "dturx"),
                sex="F" if index < 3 else "M",
            )
            for index in range(6)
        )
    )
    heldout = _private_package(
        tuple(
            _private_profile(f"h{index}", tuple(f"held-{component}{index}" for component in "dturx"))
            for index in range(6)
        )
    )

    result = _evaluate_linkage_control(policy, reference, generated, heldout=heldout)

    assert result.status == "FAIL"
    assert result.reason_code == "subgroup_linkage_threshold_exceeded"
    assert result.metrics["evaluated_count"] == 3
    assert "sex" not in repr(result).lower()


def test_linkage_suppresses_underpowered_sex_cells_without_turning_them_into_passes(
    tmp_path: Path,
) -> None:
    """Catches treating an undersized subgroup as evaluated evidence or exposing its category."""
    policy = _policy(
        required_controls=["exact_reproduction", "identifier_overlap", "linkage"],
        thresholds=policy_mapping()["thresholds"] | {"linkage_advantage": 1.0},
    )
    overall_only = _policy(
        required_controls=["exact_reproduction", "identifier_overlap", "linkage"],
        subgroups=["overall"],
        thresholds=policy_mapping()["thresholds"] | {"linkage_advantage": 1.0},
    )
    reference = _package(tmp_path / "real", synthetic=False, prefix="REAL")
    generated = _package(
        tmp_path / "generated", synthetic=True, prefix="GEN", independent=True, patient_count=4
    )
    heldout = _package(tmp_path / "heldout", synthetic=False, prefix="HLD", independent=True)

    result = _evaluate_linkage_control(policy, reference, generated, heldout=heldout)
    overall_result = _evaluate_linkage_control(overall_only, reference, generated, heldout=heldout)

    assert result.status == "PASS"
    assert result.metrics["evaluated_count"] == 4
    assert "sex" not in repr(result).lower()
    assert result.metrics == overall_result.metrics

"""Disclosure control and aggregate-only calibration result construction."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Iterable
from typing import TYPE_CHECKING

from synthetic.calibration import (
    ARTIFACT_VERSION,
    CalibrationArtifact,
    CalibrationStratum,
    CalibrationTarget,
)
from synthetic.calibration_targets import RawTarget

if TYPE_CHECKING:
    from synthetic.calibrate import CalibrationInput, CalibrationResult, CalibrationRunConfig


def _disclose_target(raw: RawTarget, config: CalibrationRunConfig) -> CalibrationTarget:
    if raw.support_count < config.disclosure_policy.minimum_cell_count:
        return CalibrationTarget(
            target_name=raw.target_name,
            family=raw.family,
            statistic=raw.statistic,
            unit=raw.unit,
            status="suppressed",
            value=None,
            support_count=None,
            denominator=None,
            rounding_decimals=0,
            quantile_level=raw.quantile_level,
        )

    if raw.statistic == "count":
        if isinstance(raw.value, bool) or not isinstance(raw.value, int) or raw.value < 0:
            raise ValueError("released count values must be nonnegative integers")
        value: int | float = raw.value
        rounding_decimals = 0
    else:
        if isinstance(raw.value, bool) or not isinstance(raw.value, (int, float)) or not math.isfinite(raw.value):
            raise ValueError("released continuous values must be finite")
        rounding_decimals = config.disclosure_policy.continuous_rounding_decimals
        value = round(float(raw.value), rounding_decimals)

    return CalibrationTarget(
        target_name=raw.target_name,
        family=raw.family,
        statistic=raw.statistic,
        unit=raw.unit,
        status="released",
        value=value,
        support_count=raw.support_count,
        denominator=raw.denominator,
        rounding_decimals=rounding_decimals,
        quantile_level=raw.quantile_level,
    )


def disclose_targets(
    raw_targets: Iterable[RawTarget], config: CalibrationRunConfig
) -> tuple[CalibrationStratum, ...]:
    """Suppress low-support targets before applying release rounding."""
    grouped: dict[tuple[str, tuple[tuple[str, str], ...]], list[CalibrationTarget]] = {}
    for raw in raw_targets:
        if not isinstance(raw, RawTarget):
            raise TypeError("raw_targets must contain RawTarget values")
        key = (raw.stratum_id, raw.dimensions)
        grouped.setdefault(key, []).append(_disclose_target(raw, config))
    if not grouped:
        raise ValueError("raw_targets must not be empty")
    return tuple(
        CalibrationStratum(stratum_id, dimensions, tuple(targets))
        for (stratum_id, dimensions), targets in sorted(grouped.items())
    )


def _aggregate_payload(strata: tuple[CalibrationStratum, ...]) -> list[dict[str, object]]:
    return [CalibrationArtifact._stratum_to_mapping(stratum) for stratum in sorted(strata, key=lambda item: item.stratum_id)]


def _aggregate_sha256(strata: tuple[CalibrationStratum, ...]) -> str:
    canonical = json.dumps(
        _aggregate_payload(strata),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def _validate_direct_strata_precision(
    strata: tuple[CalibrationStratum, ...], config: CalibrationRunConfig
) -> None:
    precision = config.disclosure_policy.continuous_rounding_decimals
    for stratum in strata:
        for target in stratum.targets:
            if target.status != "released" or target.statistic == "count":
                continue
            if target.rounding_decimals != precision:
                raise ValueError("released continuous targets must use policy precision")
            if target.value != round(float(target.value), precision):
                raise ValueError("released continuous targets must be already rounded")


def build_result(
    strata: tuple[CalibrationStratum, ...], prepared: CalibrationInput, config: CalibrationRunConfig
) -> CalibrationResult:
    """Build a strict artifact and report from disclosed aggregate strata only."""
    from synthetic.calibrate import (
        CalibrationCheck,
        CalibrationInput,
        CalibrationReport,
        CalibrationResult,
    )

    if not isinstance(prepared, CalibrationInput):
        raise TypeError("prepared must be a CalibrationInput")
    if not isinstance(strata, tuple) or not strata or not all(isinstance(item, CalibrationStratum) for item in strata):
        raise ValueError("strata must be a nonempty tuple of CalibrationStratum values")

    _validate_direct_strata_precision(strata, config)
    source_aggregate_sha256 = _aggregate_sha256(strata)
    artifact = CalibrationArtifact(
        artifact_version=ARTIFACT_VERSION,
        artifact_id=config.artifact_id,
        source_snapshot=config.source_snapshot,
        source_partition="calibration",
        source_aggregate_sha256=source_aggregate_sha256,
        schema_fingerprint=prepared.schema_fingerprint,
        created_at=config.created_at,
        disclosure_policy=config.disclosure_policy,
        strata=strata,
    )
    targets = [target for stratum in artifact.strata for target in stratum.targets]
    target_family_counts = dict(sorted(Counter(target.family for target in targets).items()))
    suppression_counts = dict(sorted(Counter(target.family for target in targets if target.status == "suppressed").items()))
    report = CalibrationReport(
        report_version="calibration-report-v1",
        status="AGGREGATES_ONLY",
        source_snapshot=config.source_snapshot,
        schema_fingerprint=prepared.schema_fingerprint,
        partition_policy=config.partition_policy.to_report_mapping(),
        partition_counts=dict(prepared.partition_summary.patient_counts),
        resource_row_counts={
            resource: dict(counts) for resource, counts in prepared.partition_summary.resource_row_counts.items()
        },
        target_family_counts=target_family_counts,
        suppression_counts=suppression_counts,
        source_aggregate_sha256=source_aggregate_sha256,
        checks=(
            CalibrationCheck("schema", True, "schema contract matched"),
            CalibrationCheck("partition", True, "partition counts available"),
            CalibrationCheck("target_registry", True, "target registry complete"),
            CalibrationCheck("disclosure", True, "disclosure controls applied"),
        ),
    )
    return CalibrationResult(artifact, report)

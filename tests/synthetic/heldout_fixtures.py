"""Fictional exact-schema packages for held-out validation tests."""

from __future__ import annotations

import csv
import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from synthetic.schema_contract import resource_spec
from tests.synthetic.calibration_fixtures import (
    write_mock_snapshot,
    write_synthetic_descriptor,
)


def read_synthetic_descriptor(package_root: Path) -> dict[str, Any]:
    """Read only a regular, non-symlinked package descriptor."""
    descriptor_path = package_root / "datapackage.json"
    try:
        entry = os.stat(descriptor_path, follow_symlinks=False)
        if not stat.S_ISREG(entry.st_mode):
            raise ValueError("synthetic descriptor is unavailable")
        descriptor_fd = os.open(descriptor_path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise ValueError("synthetic descriptor is unavailable") from exc
    try:
        with os.fdopen(descriptor_fd, "r", encoding="utf-8") as handle:
            descriptor = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("synthetic descriptor is invalid") from exc
    if not isinstance(descriptor, dict):
        raise TypeError("synthetic descriptor must be a mapping")
    return descriptor


def write_synthetic_package(root: Path, *, patient_count: int = 12, id_prefix: str = "GEN") -> Path:
    """Create a complete fictional generated package with independent visible identifiers."""
    package_root = write_mock_snapshot(root, patient_count=patient_count, id_prefix=id_prefix)
    write_synthetic_descriptor(package_root)
    return package_root


def write_header_only_package(package_root: Path) -> None:
    """Replace each fictional resource with its exact declared header only."""
    descriptor = read_synthetic_descriptor(package_root)
    for resource in descriptor["resources"]:
        resource_name = resource["name"]
        assert isinstance(resource_name, str)
        specification = resource_spec(descriptor, resource_name)
        path = package_root / specification["path"]
        dialect = specification.get("dialect", {})
        with path.open(newline="", encoding=specification.get("encoding", "utf-8")) as handle:
            header = next(
                csv.reader(
                    handle,
                    delimiter=dialect.get("delimiter", ","),
                    quotechar=dialect.get("quoteChar", '"'),
                    doublequote=dialect.get("doubleQuote", True),
                )
            )
        with path.open("w", newline="", encoding=specification.get("encoding", "utf-8")) as handle:
            csv.writer(
                handle,
                delimiter=dialect.get("delimiter", ","),
                quotechar=dialect.get("quoteChar", '"'),
                doublequote=dialect.get("doubleQuote", True),
            ).writerow(header)


def descriptor_for(package_root: Path) -> Mapping[str, Any]:
    return read_synthetic_descriptor(package_root)

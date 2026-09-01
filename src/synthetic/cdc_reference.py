"""Strict, development-only adapter for the checked-in CDC LMS tables."""

from __future__ import annotations

import csv
import hashlib
import io
import itertools
import json
import math
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import numpy as np

from synthetic.augmenter_oracle import AUGMENTER_RUNTIME_MANIFEST_SHA256

_REFERENCE_ID = "cdc-lms-reference-v1"
_MAPPING_TOKEN = "cdc-lms-mapping-v1"
_TABLES = {
    "length_cm": "statage_combined.csv",
    "height_cm": "statage_combined.csv",
    "weight_kg": "wtage_combined.csv",
    "bmi": "bmiagerev.csv",
    "head_circumference_cm": "hcageinf.csv",
}
_TABLE_NAMES = tuple(dict.fromkeys(_TABLES.values()))
_EXPECTED_MANIFEST_COUNT = 14
_REQUIRED_COLUMNS = ("Sex", "Agemos", "L", "M", "S")


@dataclass(frozen=True)
class _LmsRow:
    sex: str
    agemos: float
    l: float
    m: float
    s: float


def _inverse_lms(l: float, m: float, s: float, z: float) -> float:
    if abs(l) < 1e-6:
        try:
            result = m * math.exp(s * z)
        except (OverflowError, ValueError) as exc:
            raise ValueError("LMS result is not finite and positive") from exc
    else:
        base = 1.0 + l * s * z
        if base <= 0 or not math.isfinite(base):
            raise ValueError("LMS base must be positive")
        try:
            result = m * math.pow(base, 1.0 / l)
        except (OverflowError, ValueError) as exc:
            raise ValueError("LMS result is not finite and positive") from exc
    if not math.isfinite(result) or result <= 0:
        raise ValueError("LMS result is not finite and positive")
    return result


def _parse_lms_table(source_bytes: bytes, metric: str) -> tuple[_LmsRow, ...]:
    try:
        text = source_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CDC table must be valid UTF-8") from exc
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ValueError("CDC table is empty") from exc
    if len(header) != len(set(header)) or not set(_REQUIRED_COLUMNS).issubset(header):
        raise ValueError(f"CDC table has invalid columns for {metric}")
    rows: list[_LmsRow] = []
    for fields in reader:
        if len(fields) != len(header) or not any(fields):
            raise ValueError("CDC table has an invalid row")
        try:
            values_by_name = dict(zip(header, fields))
            sex = {"1": "M", "2": "F"}[values_by_name["Sex"].strip()]
            values = [float(values_by_name[name].strip()) for name in ("Agemos", "L", "M", "S")]
        except (KeyError, ValueError) as exc:
            raise ValueError("CDC table has an invalid LMS row") from exc
        if not all(math.isfinite(value) for value in values):
            raise ValueError("CDC table has non-finite LMS values")
        agemos, l, m, s = values
        if m <= 0 or s <= 0:
            raise ValueError("CDC table M and S must be positive")
        rows.append(_LmsRow(sex, agemos, l, m, s))
    if not rows:
        raise ValueError("CDC table has no rows")
    for sex in ("M", "F"):
        series = [row.agemos for row in rows if row.sex == sex]
        if not series or any(not later > earlier for earlier, later in itertools.pairwise(series)):
            raise ValueError("CDC table ages must be unique and increasing for each sex")
    return tuple(rows)


def _read_regular(path: Path) -> bytes:
    try:
        metadata = path.lstat()
    except OSError:
        raise ValueError("CDC source file is unavailable") from None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("CDC source file must be a regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise ValueError("CDC source file is unavailable") from None
    try:
        return b"".join(iter(lambda: os.read(descriptor, 1024 * 1024), b""))
    finally:
        os.close(descriptor)


def _manifest(root: Path) -> dict[str, tuple[str, int]]:
    manifest_path = root / "data/augment-runtime-manifest.json"
    source = _read_regular(manifest_path)
    if hashlib.sha256(source).hexdigest() != AUGMENTER_RUNTIME_MANIFEST_SHA256:
        raise ValueError("runtime manifest digest mismatch")
    try:
        manifest = json.loads(source.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("runtime manifest is invalid") from exc
    entries = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(entries, list) or len(entries) != _EXPECTED_MANIFEST_COUNT:
        raise ValueError("runtime manifest is invalid")
    result: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise TypeError("runtime manifest is invalid")
        raw = entry.get("path")
        if not isinstance(raw, str) or "\\" in raw:
            raise ValueError("runtime manifest path is invalid")
        pure = PurePosixPath(raw)
        if pure.is_absolute() or pure.as_posix() != raw or any(part in {"", ".", ".."} for part in pure.parts):
            raise ValueError("runtime manifest path is invalid")
        if raw in result or entry.get("source_relative_name") != raw:
            raise ValueError("runtime manifest entries are invalid")
        digest = entry.get("sha256")
        count = entry.get("bytes")
        if not isinstance(digest, str) or len(digest) != 64 or isinstance(count, bool) or not isinstance(count, int):
            raise ValueError("runtime manifest entries are invalid")
        path = root / Path(*pure.parts)
        data = _read_regular(path)
        if len(data) != count or hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("runtime source digest mismatch")
        result[raw] = (digest, count)
    return result


class CdcGrowthReference:
    def __init__(self, series: dict[tuple[str, str], tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]], source_sha256: str) -> None:
        self._series = series
        self._source_sha256 = source_sha256

    @classmethod
    def from_repository(cls, repository_root: Path) -> CdcGrowthReference:
        root = Path(repository_root)
        manifest = _manifest(root)
        data_dir = root / "data"
        try:
            data_metadata = data_dir.lstat()
        except OSError:
            raise ValueError("CDC source directory is unavailable") from None
        if stat.S_ISLNK(data_metadata.st_mode) or not stat.S_ISDIR(data_metadata.st_mode):
            raise ValueError("CDC source directory is invalid")
        parsed: dict[str, tuple[_LmsRow, ...]] = {}
        for table in _TABLE_NAMES:
            path = root / "data" / table
            manifest_digest, manifest_bytes = manifest[f"data/{table}"]
            source_bytes = _read_regular(path)
            if len(source_bytes) != manifest_bytes or hashlib.sha256(source_bytes).hexdigest() != manifest_digest:
                raise ValueError("runtime source digest mismatch")
            parsed[table] = _parse_lms_table(source_bytes, table)
        series: dict[tuple[str, str], tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
        for metric, table in _TABLES.items():
            for sex in ("M", "F"):
                rows = tuple(row for row in parsed[table] if row.sex == sex)
                ages = np.array([row.agemos for row in rows], dtype=float)
                ls = np.array([row.l for row in rows], dtype=float)
                ms = np.array([row.m for row in rows], dtype=float)
                ss = np.array([row.s for row in rows], dtype=float)
                series[(metric, sex)] = (ages, ls, ms, ss)
        fingerprint = {"mapping": _MAPPING_TOKEN, "reference_id": _REFERENCE_ID, "tables": [{"name": name, "sha256": manifest[f"data/{name}"][0]} for name in _TABLE_NAMES]}
        canonical = json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode()
        return cls(series, hashlib.sha256(canonical).hexdigest())

    @property
    def reference_id(self) -> str:
        return _REFERENCE_ID

    @property
    def source_sha256(self) -> str:
        return self._source_sha256

    @property
    def metrics(self) -> tuple[str, ...]:
        return ("bmi", "head_circumference_cm", "height_cm", "length_cm", "weight_kg")

    @property
    def min_age_days(self) -> int:
        return 0

    @property
    def max_age_days(self) -> int:
        return 7305

    def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
        if metric not in self.metrics:
            raise KeyError(metric)
        if not isinstance(age_days, int) or isinstance(age_days, bool):
            raise TypeError("age_days must be an integer")
        if age_days < 0:
            raise ValueError("age_days must be nonnegative")
        if reference_sex not in {"M", "F"}:
            raise ValueError("reference_sex must be M or F")
        try:
            score = float(z)
        except (TypeError, ValueError) as exc:
            raise ValueError("z must be finite") from exc
        if not math.isfinite(score):
            raise ValueError("z must be finite")
        months = 24.0 if metric == "bmi" and age_days == 730 else age_days / 30.4375
        ages, ls, ms, ss = self._series[(metric, reference_sex)]
        if months < ages[0] or months > ages[-1]:
            raise ValueError("age_days is outside the domain")
        l, m, s = (float(np.interp(months, ages, values)) for values in (ls, ms, ss))
        return _inverse_lms(l, m, s, score)

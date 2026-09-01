import csv
from pathlib import Path

from synthetic.derivation import DerivationResult
from synthetic.derivation_binding import DerivationBinding
from synthetic.schema_contract import EXPECTED_SCHEMA_FINGERPRINT, resource_spec


def test_derivation_binding() -> DerivationBinding:
    """Fictional, test-only binding with intentionally unevaluable evidence."""
    return DerivationBinding.from_mapping(
        {
            "binding_version": "derivation-binding-v1",
            "binding_id": "binding-ci-v1",
            "schema_fingerprint": EXPECTED_SCHEMA_FINGERPRINT,
            "oracle": {
                "oracle_id": "identity-preserving-test-oracle-v1",
                "implementation_fingerprint": "0123456789abcdef" * 4,
                "source_revision": "revision-ci-v1",
                "dependency_fingerprint": "a" * 64,
                "source_kind": "approved_parity_harness",
            },
            "reference_standard": {
                "standard_id": "standard-ci-v1",
                "standard_fingerprint": "b" * 64,
                "version": "standard-ci-v1",
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


test_derivation_binding.__test__ = False


class LinearTestReference:
    """Test-only deterministic reference; it makes no clinical claim."""

    reference_id = "linear-test-reference-v1"

    def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
        del reference_sex
        age_years = age_days / 365.25
        if metric == "height_cm":
            return 80.0 + 5.5 * age_years + 4.0 * z
        if metric == "bmi":
            return 16.0 + 0.25 * age_years + 1.2 * z
        raise KeyError(metric)


class RegimeLinearTestReference:
    """Test-only reference with all metrics required by the age-regime kernel."""

    reference_id = "regime-linear-test-reference-v1"
    min_age_days = 0
    max_age_days = 7305

    def value(self, metric: str, age_days: int, reference_sex: str, z: float) -> float:
        del reference_sex
        age_years = age_days / 365.25
        standing_height = 74.0 + 5.5 * age_years + 3.0 * z
        if metric == "length_cm":
            return standing_height + 0.7
        if metric == "weight_kg":
            return 8.5 + 2.0 * age_years + 0.5 * z
        if metric == "head_circumference_cm":
            return 46.0 + 1.5 * age_years + 1.0 * z
        if metric == "height_cm":
            return standing_height
        if metric == "bmi":
            return 15.5 + 0.2 * age_years + 0.5 * z
        raise KeyError(metric)


class IdentityPreservingTestDerivationOracle:
    """Test-only augmentation oracle that copies visible identity fields."""

    oracle_id = "identity-preserving-test-oracle-v1"
    implementation_fingerprint = "0123456789abcdef" * 4

    def derive(self, package_root: Path, descriptor: dict) -> DerivationResult:
        with (package_root / "patients.csv").open(encoding="utf-8", newline="") as handle:
            patients = list(csv.DictReader(handle))
        with (package_root / "visits.csv").open(encoding="utf-8", newline="") as handle:
            visits = list(csv.DictReader(handle))
        visits_by_patient: dict[str, list[dict[str, str]]] = {}
        for visit in visits:
            visits_by_patient.setdefault(visit["patient_id"], []).append(visit)

        patient_resource = resource_spec(descriptor, "patients_augmented")
        patient_fields = patient_resource["schema"]["fields"]
        patient_rows = []
        for patient in patients:
            row = {
                field["name"]: 0
                if field["type"] == "integer"
                and field.get("constraints", {}).get("required")
                else ""
                for field in patient_fields
            }
            observed = visits_by_patient.get(patient["patient_id"], [])
            ages = [int(visit["age_in_days"]) for visit in observed]
            row.update(
                {
                    "patient_id": patient["patient_id"],
                    "sex": patient["sex"],
                    "healthy_flag": 1,
                    "visits_count": len(observed),
                    "visits_count_pre_dx": len(observed),
                    "min_visit_age_days": min(ages) if ages else "",
                    "max_visit_age_days": max(ages) if ages else "",
                    "visits_span_days": max(ages) - min(ages) if ages else 0,
                }
            )
            patient_rows.append(row)

        visit_resource = resource_spec(descriptor, "visits_augmented")
        visit_fields = visit_resource["schema"]["fields"]
        sex_by_patient = {patient["patient_id"]: patient["sex"] for patient in patients}
        visit_rows = []
        for visit in visits:
            row = {
                field["name"]: 0
                if field["type"] == "integer"
                and field.get("constraints", {}).get("required")
                else ""
                for field in visit_fields
            }
            for name in row:
                if name in visit:
                    row[name] = visit[name]
            row.update(
                {
                    "patient_id": visit["patient_id"],
                    "visit_id": visit["visit_id"],
                    "sex": sex_by_patient[visit["patient_id"]],
                    "bmi": visit["BMI"],
                }
            )
            visit_rows.append(row)

        for resource, rows in (
            (patient_resource, patient_rows),
            (visit_resource, visit_rows),
        ):
            fields = [field["name"] for field in resource["schema"]["fields"]]
            with (package_root / resource["path"]).open(
                "w", encoding=resource["encoding"], newline=""
            ) as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
        return DerivationResult(self.oracle_id, self.implementation_fingerprint, True)

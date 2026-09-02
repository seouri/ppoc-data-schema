"""Tests for the package-level project metadata contract."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_datapackage_declares_project_governance_and_funding() -> None:
    """Detect a descriptor that omits the approved governance and funding metadata."""
    descriptor = json.loads((ROOT / "datapackage.json").read_text(encoding="utf-8"))

    assert descriptor["x-projectGovernance"] == {
        "primaryProject": {
            "title": "Artificial Intelligence Analysis of Growth Charts to Identify Abnormal Growth Patterns",
            "institution": "Harvard Medical School",
            "protocols": [
                {"type": "IRB", "identifier": "IRB24-0638"},
                {"type": "Data Safety and Security", "identifier": "DAT24-0223"},
            ],
            "dataUseAgreement": {
                "title": "Data Use Agreement",
                "identifier": "DUA24-0257",
                "parties": [
                    "Harvard Medical School",
                    "Pediatric Physicians' Organization, LLC (PPOC)",
                ],
            },
        },
        "dataAccess": {
            "requiredTraining": [
                "IRB training",
                "information-security training",
            ],
            "requiredDocumentation": "Certificates documenting completion of all required training.",
            "authorization": "Personnel must be formally listed as study personnel on the approved IRB protocol.",
        },
        "funding": {
            "project": "Using Large Language Models for Pediatric Diagnosis",
            "sponsors": ["Charles H. Hood Foundation", "Yosemite"],
        },
    }

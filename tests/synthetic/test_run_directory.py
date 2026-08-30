from pathlib import Path

import pytest

from synthetic.run_directory import RunDirectory


def test_refuses_existing_target(tmp_path: Path) -> None:
    target = tmp_path / "run"
    target.mkdir()
    with pytest.raises(FileExistsError):
        RunDirectory.start(target, "abc")


def test_promotes_partial_directory_atomically(tmp_path: Path) -> None:
    run = RunDirectory.start(tmp_path / "run", "abc")
    (run.partial_path / "patients.csv").write_text("patient_id\n", encoding="utf-8")
    assert run.promote() == tmp_path / "run"
    assert not run.partial_path.exists()


def test_failure_keeps_evidence_outside_target(tmp_path: Path) -> None:
    run = RunDirectory.start(tmp_path / "run", "abc")
    failed = run.fail("derivation unavailable")
    assert failed.name == ".run.abc.failed"
    assert "derivation unavailable" in (failed / "failure.json").read_text()

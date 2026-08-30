from pathlib import Path
from types import SimpleNamespace

import pytest

from synthetic import run_directory
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


def test_refuses_existing_partial_or_failed_path(tmp_path: Path) -> None:
    partial = tmp_path / ".run.abc.partial"
    partial.mkdir()
    with pytest.raises(FileExistsError):
        RunDirectory.start(tmp_path / "run", "abc")

    partial.rmdir()
    (tmp_path / ".run.abc.failed").mkdir()
    with pytest.raises(FileExistsError):
        RunDirectory.start(tmp_path / "run", "abc")


def test_promotion_refuses_target_collision_without_overwriting(tmp_path: Path) -> None:
    run = RunDirectory.start(tmp_path / "run", "abc")
    (run.partial_path / "patients.csv").write_text("patient_id\n", encoding="utf-8")
    run.target.mkdir()
    (run.target / "existing.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        run.promote()

    assert (run.target / "existing.txt").read_text(encoding="utf-8") == "keep"
    assert (run.partial_path / "patients.csv").exists()


def test_failure_preserves_partial_contents(tmp_path: Path) -> None:
    run = RunDirectory.start(tmp_path / "run", "abc")
    source = run.partial_path / "patients.csv"
    source.write_text("patient_id\nP1\n", encoding="utf-8")

    failed = run.fail("derivation unavailable")

    assert (failed / "patients.csv").read_text(encoding="utf-8") == "patient_id\nP1\n"


def test_repeated_lifecycle_calls_fail_without_overwriting(tmp_path: Path) -> None:
    run = RunDirectory.start(tmp_path / "run", "abc")
    run.promote()
    with pytest.raises(FileNotFoundError):
        run.promote()

    failed_run = RunDirectory.start(tmp_path / "failed-run", "abc")
    failed_run.fail("unavailable")
    with pytest.raises(FileNotFoundError):
        failed_run.fail("changed")


@pytest.mark.parametrize("run_id", ["", "../escape", "a/b", ".", ".."])
def test_rejects_invalid_run_id_tokens(tmp_path: Path, run_id: str) -> None:
    with pytest.raises(ValueError):
        RunDirectory.start(tmp_path / "run", run_id)


def test_linux_dispatch_uses_no_replace_rename(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []

    class FakeRename:
        def __call__(self, *args: object) -> int:
            calls.append(args)
            return 0

    fake_libc = SimpleNamespace(renameat2=FakeRename())
    monkeypatch.setattr(run_directory.sys, "platform", "linux")
    monkeypatch.setattr(run_directory.ctypes, "CDLL", lambda *args, **kwargs: fake_libc)

    run_directory._rename_without_replacing(Path("source"), Path("target"))

    assert calls and calls[0][-1] == 1


def test_linux_missing_renameat2_is_controlled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_directory.sys, "platform", "linux")
    monkeypatch.setattr(run_directory.ctypes, "CDLL", lambda *args, **kwargs: SimpleNamespace())

    with pytest.raises(NotImplementedError, match="renameat2 is unavailable"):
        run_directory._rename_without_replacing(Path("source"), Path("target"))

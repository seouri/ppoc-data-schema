from __future__ import annotations

import json
import ctypes
import errno
import os
import re
from dataclasses import dataclass
from pathlib import Path


_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def _rename_without_replacing(source: Path, target: Path) -> None:
    """Atomically rename a path while refusing an existing destination."""
    if os.uname().sysname == "Darwin":
        renamex_np = ctypes.CDLL(None, use_errno=True).renamex_np
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        result = renamex_np(os.fsencode(source), os.fsencode(target), 0x4)
        if result == 0:
            return
        if ctypes.get_errno() == errno.EEXIST:
            raise FileExistsError(target)
        raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()), target)
    raise NotImplementedError("no-replace directory rename is only supported on macOS")


@dataclass
class RunDirectory:
    target: Path
    partial_path: Path
    failed_path: Path

    @classmethod
    def start(cls, target: Path, run_id: str) -> "RunDirectory":
        if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
            raise ValueError("run_id must be a non-empty filesystem-safe token")
        target = target.resolve()
        partial = target.parent / f".{target.name}.{run_id}.partial"
        failed = target.parent / f".{target.name}.{run_id}.failed"
        for path in (target, partial, failed):
            if path.exists():
                raise FileExistsError(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial.mkdir()
        return cls(target=target, partial_path=partial, failed_path=failed)

    def promote(self) -> Path:
        _rename_without_replacing(self.partial_path, self.target)
        return self.target

    def fail(self, reason: str) -> Path:
        (self.partial_path / "failure.json").write_text(
            json.dumps({"status": "FAILED", "reason": reason}, indent=2) + "\n",
            encoding="utf-8",
        )
        _rename_without_replacing(self.partial_path, self.failed_path)
        return self.failed_path

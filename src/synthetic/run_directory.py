from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunDirectory:
    target: Path
    partial_path: Path
    failed_path: Path

    @classmethod
    def start(cls, target: Path, run_id: str) -> "RunDirectory":
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
        if self.target.exists():
            raise FileExistsError(self.target)
        os.replace(self.partial_path, self.target)
        return self.target

    def fail(self, reason: str) -> Path:
        (self.partial_path / "failure.json").write_text(
            json.dumps({"status": "FAILED", "reason": reason}, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(self.partial_path, self.failed_path)
        return self.failed_path

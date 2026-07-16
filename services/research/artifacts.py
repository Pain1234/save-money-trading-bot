"""Atomic research artifact layout (Issue #143 / P4-03)."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any


def artifact_dir(root: Path, experiment_id: str, run_id: str) -> Path:
    return root / "artifacts" / "research" / experiment_id / run_id


def _checksums_for_dir(directory: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.name != "checksums.json":
            rel = path.relative_to(directory).as_posix()
            out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


class ArtifactWriter:
    """Write run artifacts to a temp dir, then atomically finalize."""

    def __init__(self, final_dir: Path) -> None:
        self.final_dir = final_dir
        self._tmpdir: tempfile.TemporaryDirectory[str] | None = None
        self.work_dir: Path | None = None

    def __enter__(self) -> ArtifactWriter:
        if self.final_dir.exists():
            msg = f"refusing to overwrite existing artifacts at {self.final_dir}"
            raise FileExistsError(msg)
        self._tmpdir = tempfile.TemporaryDirectory(prefix="research-run-")
        self.work_dir = Path(self._tmpdir.name)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._tmpdir is not None:
            self._tmpdir.cleanup()
            self._tmpdir = None
            self.work_dir = None

    def write_bytes(self, name: str, data: bytes) -> Path:
        assert self.work_dir is not None
        path = self.work_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def write_text(self, name: str, text: str) -> Path:
        return self.write_bytes(name, text.encode("utf-8"))

    def write_json(self, name: str, payload: Any) -> Path:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return self.write_text(name, raw + "\n")

    def finalize(self) -> Path:
        assert self.work_dir is not None
        checksums = _checksums_for_dir(self.work_dir)
        self.write_json("checksums.json", checksums)
        self.final_dir.parent.mkdir(parents=True, exist_ok=True)
        if self.final_dir.exists():
            msg = f"refusing to overwrite existing artifacts at {self.final_dir}"
            raise FileExistsError(msg)
        # Move work dir into place (portable across Windows/POSIX).
        shutil.move(str(self.work_dir), str(self.final_dir))
        self._tmpdir = None
        self.work_dir = None
        return self.final_dir


def load_checksums(run_dir: Path) -> dict[str, str]:
    path = run_dir / "checksums.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = "checksums.json must be an object"
        raise ValueError(msg)
    return {str(k): str(v) for k, v in data.items()}


def verify_checksums(run_dir: Path) -> None:
    expected = load_checksums(run_dir)
    for rel, digest in expected.items():
        path = run_dir / rel
        if not path.is_file():
            msg = f"missing artifact {rel}"
            raise FileNotFoundError(msg)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != digest:
            msg = f"checksum mismatch for {rel}"
            raise ValueError(msg)


def remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)

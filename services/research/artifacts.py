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


def compute_artifact_checksums(run_dir: Path) -> dict[str, str]:
    """SHA-256 of all files under run_dir except checksums.json itself."""
    return _checksums_for_dir(run_dir)


def verify_checksums(run_dir: Path) -> None:
    """Verify using on-disk checksums.json (helper; not the registry trust anchor)."""
    expected = load_checksums(run_dir)
    verify_checksums_against(run_dir, expected)


def verify_checksums_against(
    run_dir: Path,
    expected: dict[str, str],
    *,
    exclude_names: frozenset[str] | None = None,
) -> None:
    """Verify artifact files against a trusted checksum snapshot.

    Fail-closed on missing files, digest mismatch, or unexpected extra files
    (aside from ``checksums.json``, which may be present as a helper seal).
    """
    excluded = exclude_names or frozenset({"checksums.json"})
    expected_keys = set(expected)
    unexpected_files: list[str] = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(run_dir).as_posix()
        if rel in excluded:
            continue
        if rel not in expected_keys:
            unexpected_files.append(rel)
    if unexpected_files:
        msg = f"unexpected artifacts not in trusted checksums: {unexpected_files}"
        raise ValueError(msg)
    for rel, digest in sorted(expected.items()):
        path = run_dir / rel
        if not path.is_file():
            msg = f"missing artifact {rel}"
            raise FileNotFoundError(msg)
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != digest:
            msg = f"checksum mismatch for {rel} (trusted snapshot)"
            raise ValueError(msg)


def remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)

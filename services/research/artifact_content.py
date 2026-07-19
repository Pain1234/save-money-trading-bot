"""Fail-closed read of a single sealed Research run artifact (#357).

Serves only files that are:
- pinned on an active scorecard's run ``artifact_checksums``
- present in the completed run's trusted checksum manifest
- canonicalized inside the registry run directory
- checksum-verified before the body is returned

No directory listing, ZIP export, mutation, or recompute.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from research.artifacts import load_checksums
from research.registry import ExperimentRegistry
from research.scorecard_detail import LAYER_FILES
from research.scorecard_evaluator import (
    ScorecardEvaluationError,
    ScorecardRecord,
    verify_scorecard_record_artifact_checksums,
)
from research.scorecard_policy import ScorecardPolicyError, verify_scorecard_policy_content_hash
from research.service import resolve_under_root

# Hard cap — research layer JSON/text only; never stream unbounded blobs.
MAX_ARTIFACT_BYTES: Final[int] = 2 * 1024 * 1024

# Relative paths under the run dir only (posix-style). No absolute / drive / %.
_SAFE_RELATIVE_PATH = re.compile(r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$")

_TEXT_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".txt", ".md", ".csv", ".log", ".tsv"}
)
_JSON_SUFFIX: Final[str] = ".json"


@dataclass(frozen=True)
class ArtifactContentResult:
    relative_path: str
    checksum_sha256: str
    media_kind: str  # "json" | "text"
    content_type: str
    payload: Any  # parsed JSON object/array or decoded text
    byte_length: int


class ArtifactContentError(Exception):
    """Structured fail-closed error for artifact content GET."""

    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status

    def as_detail(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message}


def _reject(code: str, message: str, *, status: int = 400) -> None:
    raise ArtifactContentError(code=code, message=message, status=status)


def normalize_relative_path(raw: str) -> str:
    """Normalize and reject traversal / encoding / absolute-path tricks."""
    if raw is None:
        _reject("not_allowlisted", "relative_path is required")
    if not isinstance(raw, str):
        _reject("not_allowlisted", "relative_path must be a string")
    if "\x00" in raw:
        _reject("not_allowlisted", "relative_path must not contain null bytes")
    # Reject undecoded / double-encoded escapes and Windows separators.
    if "%" in raw or "\\" in raw:
        _reject("not_allowlisted", "relative_path contains illegal encoding or separators")
    stripped = raw.strip()
    if not stripped or stripped != raw:
        _reject("not_allowlisted", "relative_path must be a non-empty relative path")
    if stripped.startswith("/") or stripped.startswith("\\"):
        _reject("not_allowlisted", "absolute paths are not allowed")
    # Windows drive / UNC
    if len(stripped) >= 2 and stripped[1] == ":":
        _reject("not_allowlisted", "absolute paths are not allowed")
    if stripped.startswith("//") or stripped.startswith("\\\\"):
        _reject("not_allowlisted", "absolute paths are not allowed")
    if not _SAFE_RELATIVE_PATH.fullmatch(stripped):
        _reject(
            "not_allowlisted",
            "relative_path is not allowlisted (illegal characters or traversal)",
        )
    parts = stripped.split("/")
    if any(p in {"", ".", ".."} for p in parts):
        _reject("not_allowlisted", "relative_path must not contain '.' or '..' segments")
    return stripped


def _run_pinned_checksums(record: ScorecardRecord) -> dict[str, str]:
    """Checksum keys that bind files inside the experiment run directory."""
    return {
        k: v
        for k, v in record.artifact_checksums.items()
        if not k.startswith("scorecard/") and not k.startswith("robustness/")
    }


def _is_pinned_run_path(record: ScorecardRecord, relative_path: str) -> bool:
    pinned = _run_pinned_checksums(record)
    if relative_path in pinned:
        return True
    # Layer inventory names are always candidates when sealed on the record.
    return relative_path in LAYER_FILES and relative_path in record.artifact_checksums


def _media_for_path(relative_path: str) -> tuple[str, str]:
    lower = relative_path.lower()
    if lower.endswith(_JSON_SUFFIX):
        return "json", "application/json; charset=utf-8"
    suffix = Path(lower).suffix
    if suffix in _TEXT_SUFFIXES:
        return "text", "text/plain; charset=utf-8"
    _reject(
        "unsupported_media_type",
        f"unsupported media type for {relative_path!r}",
        status=415,
    )
    raise AssertionError("unreachable")  # pragma: no cover


def _assert_not_symlink_escape(run_dir: Path, candidate: Path) -> Path:
    """Resolve candidate and ensure it stays inside the canonical run directory."""
    run_resolved = run_dir.resolve()
    # Reject symlink / junction at any path component under the run dir.
    try:
        relative = candidate.relative_to(run_dir)
    except ValueError as exc:
        _reject(
            "not_allowlisted",
            "artifact path escapes canonical run directory",
            status=400,
        )
        raise AssertionError("unreachable") from exc

    cursor = run_dir
    for part in relative.parts:
        cursor = cursor / part
        if cursor.exists() and cursor.is_symlink():
            _reject(
                "not_allowlisted",
                "symlink or junction escape is not allowed",
                status=400,
            )

    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(run_resolved)
    except ValueError as exc:
        _reject(
            "not_allowlisted",
            "artifact path escapes canonical run directory",
            status=400,
        )
        raise AssertionError("unreachable") from exc
    return resolved


def read_sealed_artifact_content(
    root: Path,
    record: ScorecardRecord,
    *,
    relative_path: str,
) -> ArtifactContentResult:
    """Return verified artifact bytes/text for an active, sealed scorecard pin."""
    if record.status == "invalidated":
        _reject(
            "invalidated_evidence",
            "scorecard evidence is invalidated",
            status=409,
        )

    try:
        verify_scorecard_policy_content_hash(
            record.policy_version, record.policy_content_hash
        )
    except ScorecardPolicyError as exc:
        _reject(
            "invalidated_evidence",
            f"scorecard policy seal failed: {exc}",
            status=409,
        )

    # Path allowlist / pin checks before any filesystem body read.
    rel = normalize_relative_path(relative_path)
    if not _is_pinned_run_path(record, rel):
        _reject(
            "not_pinned",
            f"artifact {rel!r} is not pinned on this scorecard",
            status=404,
        )
    pinned_digest = record.artifact_checksums.get(rel)
    if not pinned_digest:
        _reject(
            "not_pinned",
            f"artifact {rel!r} has no pinned checksum",
            status=404,
        )

    media_kind, content_type = _media_for_path(rel)

    registry = ExperimentRegistry(root.resolve())
    try:
        entry = registry.show(record.run_id, verify=False)
    except KeyError as exc:
        _reject("not_found", f"run not found: {record.run_id}", status=404)
        raise AssertionError("unreachable") from exc

    if entry.status != "complete":
        _reject(
            "unsealed_run",
            f"run status is {entry.status!r}; content requires complete sealed run",
            status=409,
        )

    artifacts_root = registry.artifacts_root.resolve()
    try:
        run_dir = resolve_under_root(artifacts_root, Path(entry.artifact_path))
    except PermissionError as exc:
        _reject("unsealed_run", str(exc), status=409)
        raise AssertionError("unreachable") from exc

    # Full scorecard + run seal (directory sealed). Map missing *requested*
    # artifact to not_found; other seal failures stay fail-closed.
    try:
        verify_scorecard_record_artifact_checksums(root, record)
    except ScorecardEvaluationError as exc:
        msg = str(exc)
        if f"missing artifact {rel}" in msg:
            _reject("not_found", f"artifact file not found: {rel}", status=404)
        if "checksum mismatch" in msg.lower() or "mismatch" in msg.lower():
            _reject(
                "checksum_mismatch",
                f"scorecard artifact seal failed: {exc}",
                status=409,
            )
        _reject(
            "unsealed_run",
            f"run directory is not sealed: {exc}",
            status=409,
        )

    try:
        manifest = load_checksums(run_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _reject("unsealed_run", f"checksum manifest unreadable: {exc}", status=409)
        raise AssertionError("unreachable") from exc

    if rel not in manifest and rel not in entry.checksums:
        _reject(
            "not_allowlisted",
            f"artifact {rel!r} is not in the run checksum manifest",
            status=404,
        )

    manifest_digest = manifest.get(rel) or entry.checksums.get(rel)
    if manifest_digest and manifest_digest != pinned_digest:
        _reject(
            "checksum_mismatch",
            f"pinned checksum disagrees with run manifest for {rel!r}",
            status=409,
        )

    candidate = run_dir / rel
    target = _assert_not_symlink_escape(run_dir, candidate)

    if not target.exists():
        _reject("not_found", f"artifact file not found: {rel}", status=404)
    if target.is_dir():
        _reject(
            "not_allowlisted",
            "directories cannot be served (no listing)",
            status=400,
        )
    if not target.is_file():
        _reject("not_found", f"artifact is not a regular file: {rel}", status=404)

    size = target.stat().st_size
    if size > MAX_ARTIFACT_BYTES:
        _reject(
            "too_large",
            f"artifact exceeds size limit ({MAX_ARTIFACT_BYTES} bytes)",
            status=413,
        )

    data = target.read_bytes()
    if len(data) > MAX_ARTIFACT_BYTES:
        _reject(
            "too_large",
            f"artifact exceeds size limit ({MAX_ARTIFACT_BYTES} bytes)",
            status=413,
        )

    digest = hashlib.sha256(data).hexdigest()
    if digest != pinned_digest:
        _reject(
            "checksum_mismatch",
            f"checksum mismatch for {rel}",
            status=409,
        )
    if manifest_digest and digest != manifest_digest:
        _reject(
            "checksum_mismatch",
            f"checksum mismatch vs run manifest for {rel}",
            status=409,
        )

    if media_kind == "json":
        try:
            parsed: Any = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            _reject(
                "unsupported_media_type",
                f"artifact is not valid UTF-8 JSON: {exc}",
                status=415,
            )
            raise AssertionError("unreachable") from exc
        if not isinstance(parsed, (dict, list)):
            _reject(
                "unsupported_media_type",
                "JSON artifact must be an object or array",
                status=415,
            )
        payload: Any = parsed
    else:
        try:
            payload = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            _reject(
                "unsupported_media_type",
                f"text artifact is not valid UTF-8: {exc}",
                status=415,
            )
            raise AssertionError("unreachable") from exc

    return ArtifactContentResult(
        relative_path=rel,
        checksum_sha256=digest,
        media_kind=media_kind,
        content_type=content_type,
        payload=payload,
        byte_length=len(data),
    )


__all__ = [
    "MAX_ARTIFACT_BYTES",
    "ArtifactContentError",
    "ArtifactContentResult",
    "normalize_relative_path",
    "read_sealed_artifact_content",
]

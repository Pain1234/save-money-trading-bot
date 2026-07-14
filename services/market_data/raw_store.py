"""Immutable filesystem raw artifact store (ADR-013)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from market_data.content_hash import hash_raw_bytes


@dataclass(frozen=True)
class RawArtifactRecord:
    raw_dataset_id: str
    content_hash: str
    storage_relpath: str
    source: str
    fetch_metadata: dict[str, Any]


class RawArtifactStoreError(Exception):
    """Fail-closed raw store error."""


class FileRawArtifactStore:
    """Content-addressed raw JSON store under ``root/raw/{hash}.json``."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._raw_dir = root / "raw"
        self._raw_dir.mkdir(parents=True, exist_ok=True)

    def store(
        self,
        payload: bytes,
        *,
        source: str,
        fetch_metadata: dict[str, Any],
    ) -> RawArtifactRecord:
        content_hash = hash_raw_bytes(payload)
        relpath = f"raw/{content_hash}.json"
        path = self._root / relpath
        if path.exists():
            existing = path.read_bytes()
            if existing != payload:
                msg = f"hash collision or content mismatch for {content_hash}"
                raise RawArtifactStoreError(msg)
        else:
            path.write_bytes(payload)
        raw_dataset_id = content_hash[:32]
        return RawArtifactRecord(
            raw_dataset_id=raw_dataset_id,
            content_hash=content_hash,
            storage_relpath=relpath,
            source=source,
            fetch_metadata=fetch_metadata,
        )

    def load(self, content_hash: str) -> bytes:
        path = self._root / "raw" / f"{content_hash}.json"
        if not path.is_file():
            msg = f"raw artifact not found: {content_hash}"
            raise RawArtifactStoreError(msg)
        data = path.read_bytes()
        if hash_raw_bytes(data) != content_hash:
            msg = f"raw artifact corrupt: {content_hash}"
            raise RawArtifactStoreError(msg)
        return data

    def new_fetch_id(self) -> str:
        """Unique id when same bytes stored as new observation."""
        return uuid.uuid4().hex[:32]

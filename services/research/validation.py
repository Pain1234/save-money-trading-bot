"""Validation helpers for ExperimentSpec (secrets + JSON Schema)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "experiment_spec.schema.json"

# Fail-closed: reject credential-like keys anywhere in the document tree.
FORBIDDEN_SECRET_KEY_FRAGMENTS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "password",
        "passwd",
        "secret",
        "token",
        "private_key",
        "access_key",
        "secret_key",
    }
)


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace("-", "_")


def is_forbidden_secret_key(key: str) -> bool:
    """Return True if a key name looks like a secret/credential field."""
    normalized = _normalize_key(key)
    if normalized in FORBIDDEN_SECRET_KEY_FRAGMENTS:
        return True
    return any(fragment in normalized for fragment in ("password", "secret", "token", "api_key"))


def collect_secret_keys(value: Any, *, path: str = "") -> list[str]:
    """Walk a JSON-compatible tree and return paths of forbidden keys."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if is_forbidden_secret_key(str(key)):
                found.append(child_path)
            found.extend(collect_secret_keys(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(collect_secret_keys(child, path=f"{path}[{index}]"))
    return found


def assert_no_secrets(data: dict[str, Any]) -> None:
    """Raise ValueError if the payload contains forbidden secret-like keys."""
    hits = collect_secret_keys(data)
    if hits:
        joined = ", ".join(hits)
        msg = f"ExperimentSpec must not contain secrets; forbidden keys: {joined}"
        raise ValueError(msg)


def load_json_schema() -> dict[str, Any]:
    """Load the shipped ExperimentSpec JSON Schema document."""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_against_json_schema(data: dict[str, Any]) -> None:
    """Validate a raw dict against the machine-readable JSON Schema.

    Raises ``jsonschema.ValidationError`` / ``jsonschema.SchemaError`` on failure.
    """
    schema = load_json_schema()
    jsonschema.validate(instance=data, schema=schema)

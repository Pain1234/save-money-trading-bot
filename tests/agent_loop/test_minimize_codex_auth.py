"""Unit tests for minimize_codex_auth.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / ".agent-loop" / "minimize_codex_auth.py"


def _run(auth: dict, tmp_path: Path) -> tuple[int, dict | None, str]:
    src = tmp_path / "auth.json"
    out = tmp_path / "mini.json"
    src.write_text(json.dumps(auth), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--auth-json", str(src), "--out-file", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    data = None
    if out.is_file():
        data = json.loads(out.read_text(encoding="utf-8"))
    return proc.returncode, data, proc.stderr


def test_minimize_strips_api_key_and_extra_fields(tmp_path: Path) -> None:
    code, data, err = _run(
        {
            "OPENAI_API_KEY": "sk-leak",
            "CODEX_API_KEY": "sk-also",
            "auth_mode": "chatgpt",
            "last_refresh": "secret-meta",
            "tokens": {
                "access_token": "access",
                "id_token": "id",
                "refresh_token": "refresh",
                "account_id": "acct",
                "extra_token_field": "nope",
            },
            "extra": "nope",
        },
        tmp_path,
    )
    assert code == 0, err
    assert data is not None
    assert "OPENAI_API_KEY" not in data
    assert "CODEX_API_KEY" not in data
    assert "extra" not in data
    assert "last_refresh" not in data
    assert data["auth_mode"] == "chatgpt"
    assert data["tokens"] == {
        "access_token": "access",
        "id_token": "id",
        "refresh_token": "refresh",
        "account_id": "acct",
    }
    assert "sk-leak" not in err


def test_minimize_requires_id_and_access(tmp_path: Path) -> None:
    code, data, _err = _run(
        {"tokens": {"access_token": "only-access"}},
        tmp_path,
    )
    assert code == 1
    assert data is None

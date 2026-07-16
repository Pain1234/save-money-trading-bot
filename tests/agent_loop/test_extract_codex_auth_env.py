"""Unit tests for extract_codex_auth_env.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTRACT_SCRIPT = REPO_ROOT / ".agent-loop" / "extract_codex_auth_env.py"


def _load():
    spec = importlib.util.spec_from_file_location("extract_codex_auth_env", EXTRACT_SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_extract_from_access_token(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    auth = tmp_path / "auth.json"
    auth.write_text(
        '{"tokens":{"access_token":"tok-abc","refresh_token":"r"}}\n',
        encoding="utf-8",
    )
    out = mod.extract_env_assignments(auth)
    assert out == {"OPENAI_API_KEY": "tok-abc"}


def test_extract_prefers_existing_env(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.setenv("OPENAI_API_KEY", "from-env")
    auth = tmp_path / "auth.json"
    auth.write_text(
        '{"tokens":{"access_token":"tok-abc"}}\n',
        encoding="utf-8",
    )
    out = mod.extract_env_assignments(auth)
    assert out == {"OPENAI_API_KEY": "from-env"}


def test_extract_writes_out_file_without_stdout_secrets(tmp_path, monkeypatch, capsys):
    mod = _load()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    auth = tmp_path / "auth.json"
    auth.write_text('{"OPENAI_API_KEY":"sk-test"}\n', encoding="utf-8")
    out_file = tmp_path / "env.txt"
    code = mod.main(["--auth-json", str(auth), "--out-file", str(out_file)])
    assert code == 0
    assert out_file.read_text(encoding="utf-8") == "OPENAI_API_KEY=sk-test\n"
    captured = capsys.readouterr()
    assert "sk-test" not in captured.out
    assert "sk-test" not in captured.err


def test_extract_missing_returns_1(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    missing = tmp_path / "missing.json"
    out_env = tmp_path / "o.env"
    code = mod.main(["--auth-json", str(missing), "--out-file", str(out_env)])
    assert code == 1

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


def _clear_auth_env(monkeypatch) -> None:
    for key in (
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "CODEX_ACCESS_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)


def test_extract_from_access_token(tmp_path, monkeypatch):
    mod = _load()
    _clear_auth_env(monkeypatch)
    auth = tmp_path / "auth.json"
    auth.write_text(
        '{"tokens":{"access_token":"tok-abc","refresh_token":"r"}}\n',
        encoding="utf-8",
    )
    out = mod.extract_env_assignments(auth)
    assert out == {"CODEX_ACCESS_TOKEN": "tok-abc"}
    assert "OPENAI_API_KEY" not in out


def test_extract_prefers_existing_codex_access_token(tmp_path, monkeypatch):
    mod = _load()
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("CODEX_ACCESS_TOKEN", "from-env")
    auth = tmp_path / "auth.json"
    auth.write_text(
        '{"tokens":{"access_token":"tok-abc"}}\n',
        encoding="utf-8",
    )
    out = mod.extract_env_assignments(auth)
    assert out == {"CODEX_ACCESS_TOKEN": "from-env"}


def test_extract_prefers_existing_codex_api_key(tmp_path, monkeypatch):
    mod = _load()
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("CODEX_API_KEY", "sk-from-env")
    auth = tmp_path / "auth.json"
    auth.write_text('{"OPENAI_API_KEY":"sk-ignored"}\n', encoding="utf-8")
    out = mod.extract_env_assignments(auth)
    assert out == {"CODEX_API_KEY": "sk-from-env"}


def test_extract_maps_legacy_openai_env_to_codex_api_key(tmp_path, monkeypatch):
    mod = _load()
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-legacy")
    auth = tmp_path / "auth.json"
    auth.write_text(
        '{"tokens":{"access_token":"tok-abc"}}\n',
        encoding="utf-8",
    )
    out = mod.extract_env_assignments(auth)
    assert out == {"CODEX_API_KEY": "sk-legacy"}
    assert "OPENAI_API_KEY" not in out


def test_extract_auth_json_api_key_to_codex_api_key(tmp_path, monkeypatch):
    mod = _load()
    _clear_auth_env(monkeypatch)
    auth = tmp_path / "auth.json"
    auth.write_text('{"OPENAI_API_KEY":"sk-test"}\n', encoding="utf-8")
    out = mod.extract_env_assignments(auth)
    assert out == {"CODEX_API_KEY": "sk-test"}


def test_extract_writes_out_file_without_stdout_secrets(tmp_path, monkeypatch, capsys):
    mod = _load()
    _clear_auth_env(monkeypatch)
    auth = tmp_path / "auth.json"
    auth.write_text('{"OPENAI_API_KEY":"sk-test"}\n', encoding="utf-8")
    out_file = tmp_path / "env.txt"
    code = mod.main(["--auth-json", str(auth), "--out-file", str(out_file)])
    assert code == 0
    expected = "CODEX" + "_API" + "_KEY=" + "sk-test" + "\n"
    assert out_file.read_text(encoding="utf-8") == expected
    captured = capsys.readouterr()
    assert "sk-test" not in captured.out
    assert "sk-test" not in captured.err


def test_extract_missing_returns_1(tmp_path, monkeypatch):
    mod = _load()
    _clear_auth_env(monkeypatch)
    missing = tmp_path / "missing.json"
    out_env = tmp_path / "o.env"
    code = mod.main(["--auth-json", str(missing), "--out-file", str(out_env)])
    assert code == 1

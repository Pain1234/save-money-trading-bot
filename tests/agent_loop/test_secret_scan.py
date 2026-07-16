"""Tests for .agent-loop/secret_scan.py."""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout


def test_clean_text_no_matches(secret_scan_mod):
    assert secret_scan_mod.scan_text("hello world\nno secrets here\n") == []


def test_each_pattern_family_triggers(secret_scan_mod):
    samples = {
        "api_key_assignment": "api_key=abc",
        "aws_access_key_id": "AKIA" + ("0" * 16),
        "aws_secret_access_key": "aws_secret_access_key=xyz",
        "private_key_block": "-----BEGIN RSA PRIVATE KEY-----",
        "bearer_token": "Authorization: Bearer abcdefghijklmnop",
        "postgres_url_with_password": "postgres://user:pass@localhost/db",
        "sqlalchemy_postgres_url_with_password": (
            "postgresql+psycopg://user:pass@localhost/db"
        ),
        "mysql_url_with_password": "mysql://user:pass@localhost/db",
        "generic_db_url_password": "mongodb://user:pass@localhost/db",
        "database_url_with_password": "DATABASE_URL=customdb://user:pass@localhost/db",
        "railway_token_assignment": "RAILWAY_TOKEN=tok_abc123",
        "session_secret_assignment": "SESSION_SECRET=session_value_here",
        "github_pat": "ghp_" + ("a" * 20),
        "slack_token": "xoxb-" + ("a" * 12),
        "openai_sk": "sk-" + ("a" * 20),
    }
    for name, line in samples.items():
        matches = secret_scan_mod.scan_text(line + "\n")
        assert matches, f"expected match for {name}"
        assert matches[0].pattern_name == name


def test_sqlalchemy_dialect_variants(secret_scan_mod):
    lines = [
        "postgresql+psycopg://user:password@host/db",
        "postgresql+asyncpg://user:password@host/db",
        "postgres+psycopg2://user:password@host/db",
    ]
    for line in lines:
        matches = secret_scan_mod.scan_text(line + "\n")
        assert matches, f"expected sqlalchemy match for {line}"
        assert matches[0].pattern_name == "sqlalchemy_postgres_url_with_password"


def test_format_matches_never_includes_secret_values(secret_scan_mod):
    password = "supersecret"
    text = f"password={password}\nDATABASE_URL=postgres://u:{password}@localhost/db\n"
    matches = secret_scan_mod.scan_text(text)
    assert matches
    formatted = secret_scan_mod.format_matches(matches)
    assert password not in formatted
    assert "line " in formatted
    for m in matches:
        assert f"[{m.pattern_name}]" in formatted
        assert f"line {m.line_number}" in formatted
    assert not hasattr(matches[0], "line_preview") or "line_preview" not in formatted


def test_cli_stderr_does_not_leak_secret_values(secret_scan_mod, tmp_path):
    secret_value = "supersecret"
    diff = tmp_path / "leak.diff"
    diff.write_text(
        "diff --git a/x b/x\n"
        f"+password={secret_value}\n"
        f"+DATABASE_URL=postgres://user:{secret_value}@localhost/db\n",
        encoding="utf-8",
    )
    err = io.StringIO()
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = secret_scan_mod.main(["--diff", str(diff)])
    assert code == 1
    stderr = err.getvalue()
    assert secret_value not in stderr
    assert "postgres_url_with_password" in stderr or "database_url_with_password" in stderr
    assert "line " in stderr


def test_cli_secret_diff_exit_1(secret_scan_mod, fixtures_dir):
    code = secret_scan_mod.main(["--diff", str(fixtures_dir / "secret.diff")])
    assert code == 1


def test_cli_secret_sqlalchemy_diff_exit_1(secret_scan_mod, fixtures_dir):
    code = secret_scan_mod.main(["--diff", str(fixtures_dir / "secret_sqlalchemy.diff")])
    assert code == 1


def test_cli_sample_diff_exit_0(secret_scan_mod, fixtures_dir):
    code = secret_scan_mod.main(["--diff", str(fixtures_dir / "sample.diff")])
    assert code == 0


def test_secret_match_has_no_line_preview(secret_scan_mod):
    matches = secret_scan_mod.scan_text("api_key=abc\n")
    assert matches
    assert not hasattr(matches[0], "line_preview")

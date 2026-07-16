"""Tests for .agent-loop/secret_scan.py."""

from __future__ import annotations


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
        "mysql_url_with_password": "mysql://user:pass@localhost/db",
        "generic_db_url_password": "mongodb://user:pass@localhost/db",
        "github_pat": "ghp_" + ("a" * 20),
        "slack_token": "xoxb-" + ("a" * 12),
        "openai_sk": "sk-" + ("a" * 20),
    }
    for name, line in samples.items():
        matches = secret_scan_mod.scan_text(line + "\n")
        assert matches, f"expected match for {name}"
        assert matches[0].pattern_name == name


def test_cli_secret_diff_exit_1(secret_scan_mod, fixtures_dir):
    code = secret_scan_mod.main(["--diff", str(fixtures_dir / "secret.diff")])
    assert code == 1


def test_cli_sample_diff_exit_0(secret_scan_mod, fixtures_dir):
    code = secret_scan_mod.main(["--diff", str(fixtures_dir / "sample.diff")])
    assert code == 0

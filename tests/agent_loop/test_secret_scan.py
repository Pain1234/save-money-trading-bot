"""Tests for .agent-loop/secret_scan.py."""

from __future__ import annotations

import io
import subprocess
from contextlib import redirect_stderr, redirect_stdout

import secret_fragments as sf


def test_clean_text_no_matches(secret_scan_mod):
    assert secret_scan_mod.scan_text("hello world\nno secrets here\n") == []


def test_each_pattern_family_triggers(secret_scan_mod):
    samples = {
        "api_key_assignment": sf.api_key_assignment(),
        "aws_access_key_id": sf.aws_access_key_id(),
        "aws_secret_access_key": sf.aws_secret_access_key_assignment(),
        "private_key_block": sf.private_key_begin("RSA"),
        "bearer_token": sf.bearer_token(),
        "postgres_url_with_password": sf.postgres_url(),
        "sqlalchemy_postgres_url_with_password": sf.sqlalchemy_postgres_url(),
        "mysql_url_with_password": sf.mysql_url(),
        "generic_db_url_password": sf.mongodb_url(),
        "database_url_with_password": sf.database_url_assignment(),
        "railway_token_assignment": sf.railway_token_assignment(),
        "session_secret_assignment": sf.session_secret_assignment(),
        "github_pat": sf.github_pat(),
        "slack_token": sf.slack_token(),
        "openai_sk": sf.openai_sk(),
    }
    for name, line in samples.items():
        matches = secret_scan_mod.scan_text(line + "\n")
        assert matches, f"expected match for {name}"
        assert matches[0].pattern_name == name


def test_sqlalchemy_dialect_variants(secret_scan_mod):
    lines = [
        sf.sqlalchemy_postgres_url(dialect="psycopg", password="password"),
        sf.sqlalchemy_postgres_url(dialect="asyncpg", password="password"),
        "postgres" + "+psycopg2://" + "user:password@host/db",
    ]
    for line in lines:
        matches = secret_scan_mod.scan_text(line + "\n")
        assert matches, f"expected sqlalchemy match for {line}"
        assert matches[0].pattern_name == "sqlalchemy_postgres_url_with_password"


def test_format_matches_never_includes_secret_values(secret_scan_mod):
    password = "supersecret"
    text = (
        "password="
        + password
        + "\n"
        + "DATABASE"
        + "_URL="
        + sf.postgres_url(user="u", password=password)
        + "\n"
    )
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
        "+password="
        + secret_value
        + "\n"
        "+"
        + "DATABASE"
        + "_URL="
        + sf.postgres_url(user="user", password=secret_value)
        + "\n",
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


def test_cli_secret_diff_exit_1(secret_scan_mod, tmp_path):
    diff = tmp_path / "secret.diff"
    diff.write_text(sf.secret_diff_text(), encoding="utf-8")
    code = secret_scan_mod.main(["--diff", str(diff)])
    assert code == 1


def test_cli_secret_sqlalchemy_diff_exit_1(secret_scan_mod, tmp_path):
    diff = tmp_path / "secret_sqlalchemy.diff"
    diff.write_text(sf.secret_sqlalchemy_diff_text(), encoding="utf-8")
    code = secret_scan_mod.main(["--diff", str(diff)])
    assert code == 1


def test_cli_sample_diff_exit_0(secret_scan_mod, fixtures_dir):
    code = secret_scan_mod.main(["--diff", str(fixtures_dir / "sample.diff")])
    assert code == 0


def test_secret_match_has_no_line_preview(secret_scan_mod):
    matches = secret_scan_mod.scan_text(sf.api_key_assignment() + "\n")
    assert matches
    assert not hasattr(matches[0], "line_preview")


def test_runtime_fragments_cover_key_families(secret_scan_mod):
    """Runtime-built API key / DB URL / PEM header must still trip the scanner."""
    for text in (
        sf.api_key_assignment("runtime"),
        sf.postgres_url(password="runtime_pw"),
        sf.private_key_begin("OPENSSH"),
    ):
        assert secret_scan_mod.scan_text(text + "\n")


def test_diff_scan_only_added_lines(secret_scan_mod):
    """Deletion hunks with secret-like text must not abort; additions still do."""
    deleted = (
        "diff --git a/old.env b/old.env\n"
        "--- a/old.env\n"
        "+++ b/old.env\n"
        "@@ -1 +0,0 @@\n"
        "-"
        + sf.api_key_assignment("gone")
        + "\n"
    )
    assert secret_scan_mod.scan_text(deleted) == []
    added = (
        "diff --git a/new.env b/new.env\n"
        "--- a/new.env\n"
        "+++ b/new.env\n"
        "@@ -0,0 +1 @@\n"
        "+"
        + sf.api_key_assignment("fresh")
        + "\n"
    )
    assert secret_scan_mod.scan_text(added)


def test_pr_diff_against_origin_main_is_secret_clean(secret_scan_mod, repo_root, tmp_path):
    """Branch worktree vs origin/main merge-base must be secret_scan clean."""
    mb = subprocess.run(
        ["git", "merge-base", "origin/main", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert mb.returncode == 0 and mb.stdout.strip(), mb.stderr
    merge_base = mb.stdout.strip()
    # Include unstaged/uncommitted edits so the check works before commit.
    proc = subprocess.run(
        ["git", "diff", merge_base],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
    patch = tmp_path / "pr-range.patch"
    patch.write_bytes(proc.stdout)
    # Also scan new untracked agent-loop test helpers that will ship in the PR.
    extras = [
        repo_root / "tests" / "agent_loop" / "secret_fragments.py",
        repo_root / "tests" / "agent_loop" / "fixtures" / "mock_codex_hang_tree.py",
    ]
    for path in extras:
        status = subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path.relative_to(repo_root))],
            cwd=repo_root,
            capture_output=True,
            check=False,
        )
        if status.returncode != 0 and path.is_file():
            with patch.open("ab") as fh:
                fh.write(f"diff --git a/{path.name} b/{path.name}\n".encode())
                fh.write(b"--- /dev/null\n")
                fh.write(f"+++ b/{path.name}\n".encode())
                text = path.read_text(encoding="utf-8")
                fh.write(f"@@ -0,0 +1,{len(text.splitlines())} @@\n".encode())
                for line in text.splitlines():
                    fh.write(("+" + line + "\n").encode())
    code = secret_scan_mod.main(["--diff", str(patch)])
    assert code == 0, (
        "PR diff must be secret_scan clean; rebuild fixtures from fragments. "
        f"See {patch}"
    )


def test_versioned_fixtures_have_no_full_secret_literals(fixtures_dir, secret_scan_mod):
    """No committed fixture file under fixtures/ may itself match secret patterns."""
    for path in sorted(fixtures_dir.rglob("*")):
        if not path.is_file() or path.name == ".gitkeep":
            continue
        if path.suffix in {".pyc"}:
            continue
        matches = secret_scan_mod.scan_file(path)
        assert not matches, f"{path.name} still contains secret-like literals: {matches}"

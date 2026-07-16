#!/usr/bin/env python3
"""Build an allowlisted review workspace for Codex (secret isolation).

Loads reviewed-head blobs via `git show` into an out-dir (never copies from the
worktree). Copies only prompt/schema/diff as file artifacts; AGENTS.md is loaded
from the git blob at --git-rev when present.

Deny-listed paths in the diff fail closed (exit 1) — no usable workspace.

Exit codes:
  0 - success
  1 - deny-listed path / symlink rejected
  2 - usage / I/O error
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path

DIFF_PATH_RE = re.compile(
    r'^(?:\+\+\+|---) (?:(?P<unquoted>[ab]/.+)|"(?P<quoted>.*)")$'
)
RENAME_COPY_RE = re.compile(
    r'^(?:rename|copy) (?:from|to) (?P<path>.+)$'
)
BINARY_FILES_RE = re.compile(
    r'^Binary files (?:(?P<a_unquoted>a/.+?)|"(?P<a_quoted>.*)") '
    r'and (?:(?P<b_unquoted>b/.+?)|"(?P<b_quoted>.*)") differ$'
)

# Paths that must never be copied into the review workspace (even if in the diff).
DENY_PATTERNS: tuple[str, ...] = (
    ".env",
    ".env.*",
    ".codex",
    ".codex/*",
    ".codex/**",
    "*secret*",
    "*/secret*",
    "**/secret*",
    "credentials*",
    "*/credentials*",
    "**/credentials*",
    "auth.json",
    "*/auth.json",
    "**/auth.json",
    "*.pem",
    "id_rsa",
    "id_rsa.*",
    "id_ed25519",
    "id_ed25519.*",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.keystore",
)


def normalize_rel(path: str) -> str:
    p = path.replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    return p


def decode_c_quoted_path(raw: str) -> str:
    """Decode a git C-quoted path body (contents inside the surrounding quotes).

    Octal escapes (\\NNN) are bytes: consecutive octal escapes are collected into
    a bytearray and UTF-8-decoded as a run (e.g. \\303\\266 → ö).
    """
    out: list[str] = []
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        if i + 1 >= n:
            out.append("\\")
            break
        nxt = raw[i + 1]
        if nxt == "n":
            out.append("\n")
            i += 2
        elif nxt == "t":
            out.append("\t")
            i += 2
        elif nxt == "r":
            out.append("\r")
            i += 2
        elif nxt == "b":
            out.append("\b")
            i += 2
        elif nxt == "f":
            out.append("\f")
            i += 2
        elif nxt == '"':
            out.append('"')
            i += 2
        elif nxt == "\\":
            out.append("\\")
            i += 2
        elif nxt in "01234567":
            # Consecutive \\NNN octal escapes are UTF-8 bytes, not Latin-1 codepoints.
            byte_vals = bytearray()
            while i < n and raw[i] == "\\" and i + 1 < n and raw[i + 1] in "01234567":
                j = i + 1
                oct_digits: list[str] = []
                while j < n and len(oct_digits) < 3 and raw[j] in "01234567":
                    oct_digits.append(raw[j])
                    j += 1
                byte_vals.append(int("".join(oct_digits), 8))
                i = j
            out.append(byte_vals.decode("utf-8", errors="replace"))
        else:
            # Unknown escape: keep the escaped character
            out.append(nxt)
            i += 2
    return "".join(out)


def _next_diff_path_token(s: str, start: int = 0) -> tuple[str, bool, int] | None:
    """Parse one git diff path token.

    Returns (raw_or_quoted_body, was_quoted, next_index).
    """
    while start < len(s) and s[start].isspace():
        start += 1
    if start >= len(s):
        return None
    if s[start] == '"':
        i = start + 1
        while i < len(s):
            if s[i] == "\\":
                i += 2 if i + 1 < len(s) else 1
                continue
            if s[i] == '"':
                return s[start + 1 : i], True, i + 1
            i += 1
        return None
    i = start
    while i < len(s) and not s[i].isspace():
        i += 1
    return s[start:i], False, i


def _normalize_diff_path_token(token: str, *, quoted: bool) -> str:
    decoded = decode_c_quoted_path(token) if quoted else token
    return normalize_rel(_strip_ab_prefix(decoded))


def _add_path(found: list[str], seen: set[str], rel: str) -> None:
    if not rel or rel == "/dev/null":
        return
    if rel not in seen:
        seen.add(rel)
        found.append(rel)


def paths_from_diff_git_line(line: str) -> list[str]:
    """Extract paths from a `diff --git ...` header line."""
    if not line.startswith("diff --git "):
        return []
    rest = line[len("diff --git ") :]
    paths: list[str] = []
    pos = 0
    for _ in range(2):
        parsed = _next_diff_path_token(rest, pos)
        if parsed is None:
            break
        token, quoted, pos = parsed
        rel = _normalize_diff_path_token(token, quoted=quoted)
        if rel and rel != "/dev/null":
            paths.append(rel)
    return paths


def _strip_ab_prefix(path: str) -> str:
    """Strip leading a/ or b/ from a git diff path."""
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def is_denied(rel_path: str) -> bool:
    rel = normalize_rel(rel_path)
    if not rel or rel == "/dev/null":
        return False
    parts = rel.split("/")
    # Any .codex segment
    if ".codex" in parts:
        return True
    # .env or .env.* at any depth (basename)
    base = parts[-1]
    if base == ".env" or fnmatch(base, ".env.*"):
        return True
    for pattern in DENY_PATTERNS:
        if fnmatch(rel, pattern) or fnmatch(base, pattern):
            return True
        # Also match patterns against each path suffix (e.g. foo/credentials.json)
        for i in range(len(parts)):
            suffix = "/".join(parts[i:])
            if fnmatch(suffix, pattern):
                return True
    return False


def paths_from_diff(diff_text: str) -> list[str]:
    """Extract all file paths mentioned in a unified / git diff (fail-closed inputs)."""
    found: list[str] = []
    seen: set[str] = set()
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            for rel in paths_from_diff_git_line(line):
                _add_path(found, seen, rel)
            continue

        m = DIFF_PATH_RE.match(line)
        if m:
            if m.group("quoted") is not None:
                decoded = decode_c_quoted_path(m.group("quoted"))
                rel = normalize_rel(_strip_ab_prefix(decoded))
            else:
                rel = normalize_rel(_strip_ab_prefix(m.group("unquoted")))
            _add_path(found, seen, rel)
            continue

        m = RENAME_COPY_RE.match(line)
        if m:
            # rename/copy lines have no a_/b_ prefix; may still be C-quoted.
            raw_path = m.group("path")
            if raw_path.startswith('"') and raw_path.endswith('"') and len(raw_path) >= 2:
                rel = normalize_rel(decode_c_quoted_path(raw_path[1:-1]))
            else:
                rel = normalize_rel(raw_path)
            _add_path(found, seen, rel)
            continue

        m = BINARY_FILES_RE.match(line)
        if m:
            if m.group("a_quoted") is not None:
                a_rel = normalize_rel(
                    _strip_ab_prefix(decode_c_quoted_path(m.group("a_quoted")))
                )
            else:
                a_rel = normalize_rel(_strip_ab_prefix(m.group("a_unquoted")))
            if m.group("b_quoted") is not None:
                b_rel = normalize_rel(
                    _strip_ab_prefix(decode_c_quoted_path(m.group("b_quoted")))
                )
            else:
                b_rel = normalize_rel(_strip_ab_prefix(m.group("b_unquoted")))
            _add_path(found, seen, a_rel)
            _add_path(found, seen, b_rel)
    return found


def safe_copy_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def _git(
    repo_root: Path,
    args: list[str],
    *,
    check: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        check=check,
    )


def git_ls_tree_mode(repo_root: Path, git_rev: str, rel: str) -> str | None:
    """Return tree entry mode for path at rev, or None if missing."""
    proc = _git(repo_root, ["ls-tree", git_rev, "--", rel], check=False)
    if proc.returncode != 0:
        return None
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    if not out:
        return None
    # Format: <mode> <type> <object>\t<file>
    first = out.splitlines()[0]
    mode = first.split(None, 1)[0]
    return mode


def git_show_blob(repo_root: Path, git_rev: str, rel: str) -> bytes | None:
    """Load blob bytes at rev:path. None if missing / failed."""
    proc = _git(repo_root, ["show", f"{git_rev}:{rel}"], check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout


def build_workspace(
    *,
    repo_root: Path,
    diff_path: Path,
    out_dir: Path,
    prompt_path: Path,
    schema_path: Path,
    git_rev: str,
) -> dict:
    raw = diff_path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    diff_text = raw.decode("utf-8", errors="replace")

    diff_paths = paths_from_diff(diff_text)
    denied_in_diff = [rel for rel in diff_paths if is_denied(rel)]
    if denied_in_diff:
        names = ", ".join(sorted(set(denied_in_diff)))
        raise PermissionError(
            f"deny-listed path(s) in diff (fail-closed): {names}"
        )

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    allowlisted: list[str] = []
    skipped_missing: list[str] = []

    # Always copy core review artifacts (names fixed inside workspace).
    core_copies = [
        (prompt_path, out_dir / "codex-review-prompt.md", "codex-review-prompt.md"),
        (schema_path, out_dir / "codex-review-schema.json", "codex-review-schema.json"),
        (diff_path, out_dir / "current-diff.patch", "current-diff.patch"),
    ]
    for src, dest, rel_name in core_copies:
        if not src.is_file():
            raise FileNotFoundError(f"required input missing: {src}")
        if is_denied(rel_name):
            raise PermissionError(f"refuse to copy deny-listed path: {rel_name}")
        safe_copy_file(src, dest)
        allowlisted.append(rel_name)

    # AGENTS.md from committed blob only (never worktree copy).
    agents_blob = git_show_blob(repo_root, git_rev, "AGENTS.md")
    if agents_blob is not None:
        if is_denied("AGENTS.md"):
            raise PermissionError("refuse to materialize deny-listed path: AGENTS.md")
        (out_dir / "AGENTS.md").write_bytes(agents_blob)
        allowlisted.append("AGENTS.md")

    for rel in diff_paths:
        # Denied already fail-closed above; keep guard for defense in depth.
        if is_denied(rel):
            raise PermissionError(f"refuse to materialize deny-listed path: {rel}")

        dest = out_dir / rel
        try:
            dest.resolve().relative_to(out_dir.resolve())
        except ValueError as exc:
            raise PermissionError(f"path escapes workspace: {rel}") from exc

        mode = git_ls_tree_mode(repo_root, git_rev, rel)
        if mode == "120000":
            raise PermissionError(f"symlink rejected at {git_rev}: {rel}")

        blob = git_show_blob(repo_root, git_rev, rel)
        if blob is None:
            skipped_missing.append(rel)
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
        allowlisted.append(rel)

    manifest = {
        "allowlisted": sorted(set(allowlisted)),
        "skipped_missing": sorted(set(skipped_missing)),
        "denied": [],  # empty on success; deny fails before workspace build
        "git_rev": git_rev,
        "out_dir_name": out_dir.name,
    }
    manifest_path = out_dir / "workspace-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build allowlisted Codex review workspace (secret isolation)."
    )
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--diff", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--prompt", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument(
        "--git-rev",
        required=True,
        help="Reviewed HEAD SHA/ref; blobs loaded via git show <rev>:<path>.",
    )
    # Deprecated: previously copied worktree AGENTS.md; ignored — always use git blob.
    parser.add_argument("--agents", type=Path, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    git_rev = args.git_rev.strip()
    if not git_rev:
        print("build_review_workspace: error: --git-rev is required", file=sys.stderr)
        return 2

    out_dir = args.out_dir.resolve()
    try:
        build_workspace(
            repo_root=args.repo_root.resolve(),
            diff_path=args.diff.resolve(),
            out_dir=out_dir,
            prompt_path=args.prompt.resolve(),
            schema_path=args.schema.resolve(),
            git_rev=git_rev,
        )
    except PermissionError as exc:
        # Do not leave a usable workspace for Codex after deny/symlink rejection.
        if out_dir.exists():
            shutil.rmtree(out_dir, ignore_errors=True)
        print(f"build_review_workspace: DENIED: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"build_review_workspace: error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

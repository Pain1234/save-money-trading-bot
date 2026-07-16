#!/usr/bin/env python3
"""Build an allowlisted review workspace for Codex (secret isolation).

Copies only prompt/schema/diff/AGENTS.md and non-denied files referenced by the
diff into a clean out-dir. Never copies .env, .codex, credentials, or secret-like
paths. Writes workspace-manifest.json listing allowlisted paths.

Exit codes:
  0 - success
  1 - deny-listed path requested / copy refused
  2 - usage / I/O error
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from fnmatch import fnmatch
from pathlib import Path

DIFF_PATH_RE = re.compile(
    r"^(?:\+\+\+|\-\-\-) [ab]/(?P<path>.+)$"
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
    "*.pem",
    "id_rsa",
    "id_rsa.*",
    "*.key",
    "*.p12",
    "*.pfx",
)


def normalize_rel(path: str) -> str:
    p = path.replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    return p


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
    found: list[str] = []
    seen: set[str] = set()
    for line in diff_text.splitlines():
        m = DIFF_PATH_RE.match(line)
        if not m:
            continue
        rel = normalize_rel(m.group("path"))
        if not rel or rel == "/dev/null":
            continue
        if rel not in seen:
            seen.add(rel)
            found.append(rel)
    return found


def safe_copy_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def build_workspace(
    *,
    repo_root: Path,
    diff_path: Path,
    out_dir: Path,
    prompt_path: Path,
    schema_path: Path,
    agents_path: Path | None,
) -> dict:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw = diff_path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    diff_text = raw.decode("utf-8", errors="replace")

    allowlisted: list[str] = []
    skipped_missing: list[str] = []
    denied_in_diff: list[str] = []

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

    if agents_path is not None and agents_path.is_file():
        if is_denied("AGENTS.md"):
            raise PermissionError("refuse to copy deny-listed path: AGENTS.md")
        safe_copy_file(agents_path, out_dir / "AGENTS.md")
        allowlisted.append("AGENTS.md")

    for rel in paths_from_diff(diff_text):
        if is_denied(rel):
            denied_in_diff.append(rel)
            continue
        src = repo_root / rel
        if not src.is_file():
            skipped_missing.append(rel)
            continue
        # Defense in depth: never copy deny paths even if logic above missed.
        if is_denied(rel):
            raise PermissionError(f"refuse to copy deny-listed path: {rel}")
        dest = out_dir / rel
        # Prevent path escape
        try:
            dest.resolve().relative_to(out_dir.resolve())
        except ValueError as exc:
            raise PermissionError(f"path escapes workspace: {rel}") from exc
        safe_copy_file(src, dest)
        allowlisted.append(rel)

    manifest = {
        "allowlisted": sorted(set(allowlisted)),
        "skipped_missing": sorted(set(skipped_missing)),
        "denied": sorted(set(denied_in_diff)),
        "repo_root": str(repo_root),
        "out_dir": str(out_dir),
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
    parser.add_argument("--agents", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        build_workspace(
            repo_root=args.repo_root.resolve(),
            diff_path=args.diff.resolve(),
            out_dir=args.out_dir.resolve(),
            prompt_path=args.prompt.resolve(),
            schema_path=args.schema.resolve(),
            agents_path=args.agents.resolve() if args.agents else None,
        )
    except PermissionError as exc:
        print(f"build_review_workspace: DENIED: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"build_review_workspace: error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

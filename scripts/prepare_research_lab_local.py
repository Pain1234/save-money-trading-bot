#!/usr/bin/env python3
"""Prepare a local Strategy Lab dataset catalog (Issue #264).

Writes deterministic fixtures under ``examples/research/local_lab/`` and prints
shell env for the Research API process. Does not enable live trading or free
client paths.

Usage (from repo root, with venv active)::

    python scripts/prepare_research_lab_local.py
    python scripts/prepare_research_lab_local.py --print-env-only
    python scripts/prepare_research_lab_local.py --print-dirty-git-exception
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "examples" / "research" / "local_lab"
CATALOG_ID = "local-btc-fixture"
# Fixed provenance metadata so regenerating the catalog does not dirty the tree.
FIXED_CREATED_AT = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)


def _ensure_path() -> None:
    services = REPO_ROOT / "services"
    if str(services) not in sys.path:
        sys.path.insert(0, str(services))
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


def write_local_lab() -> Path:
    _ensure_path()
    from tests.research.fixtures import align_spec_to_bundle, btc_bundle

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bundle = btc_bundle()
    spec = align_spec_to_bundle(
        OUT_DIR,
        bundle,
        symbols=["BTC"],
        created_at=FIXED_CREATED_AT,
    )
    ref = spec.dataset_manifest_ref

    written = Path(ref.manifest_path)
    if not written.is_absolute():
        written = (REPO_ROOT / written).resolve()
    manifest_dest = OUT_DIR / "dataset_manifest.json"
    if written.resolve() != manifest_dest.resolve():
        manifest_dest.write_text(written.read_text(encoding="utf-8"), encoding="utf-8")
        if written.parent == OUT_DIR and written.name != manifest_dest.name:
            written.unlink(missing_ok=True)

    bundle_path = OUT_DIR / "bundle.json"
    bundle_path.write_text(bundle.model_dump_json(), encoding="utf-8")

    manifest = json.loads(manifest_dest.read_text(encoding="utf-8"))
    catalog = [
        {
            "id": CATALOG_ID,
            "label": "Local BTC fixture (dev)",
            "dataset_id": manifest.get("dataset_id") or ref.dataset_id,
            "content_hash": manifest["content_hash"],
            "manifest_path": "examples/research/local_lab/dataset_manifest.json",
            "bundle_path": "examples/research/local_lab/bundle.json",
            "symbols": ["BTC"],
            "time_range": {
                "start": "2023-12-01T00:00:00.000000Z",
                "end": "2024-01-31T23:59:59.000000Z",
            },
        }
    ]
    catalog_path = OUT_DIR / "catalog.json"
    catalog_path.write_text(
        json.dumps({"datasets": catalog}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return catalog_path


def print_env(catalog_path: Path, *, show_dirty_git_exception: bool) -> None:
    artifacts = REPO_ROOT  # ExperimentRegistry uses root/artifacts/research/
    print("# Research API process (PowerShell) — restart after setting:")
    print(f'$env:RESEARCH_REPO_ROOT = "{REPO_ROOT}"')
    print(f'$env:RESEARCH_ARTIFACTS_ROOT = "{artifacts}"')
    print(f'$env:RESEARCH_DATASET_CATALOG_PATH = "{catalog_path}"')
    print()
    print("# Git provenance: keep a clean working tree so resolve_git_commit can")
    print("# record the real HEAD. Do not set RESEARCH_ALLOW_DIRTY_GIT for normal")
    print("# local Lab runs.")
    if show_dirty_git_exception:
        print()
        print("# Documented exception only (tests / explicit local override):")
        print('$env:RESEARCH_ALLOW_DIRTY_GIT = "1"')
    print()
    print("# If RESEARCH_DATASET_CATALOG_PATH is unset, the API also falls back to")
    print("# examples/research/local_lab/catalog.json when that file exists.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-env-only",
        action="store_true",
        help="Do not regenerate fixtures; only print env for existing catalog.",
    )
    parser.add_argument(
        "--print-dirty-git-exception",
        action="store_true",
        help=(
            "Also print RESEARCH_ALLOW_DIRTY_GIT=1. Documented exception only — "
            "not for standard Lab runs (git provenance would be ambiguous)."
        ),
    )
    args = parser.parse_args()
    catalog_path = OUT_DIR / "catalog.json"
    if not args.print_env_only:
        catalog_path = write_local_lab()
        print(f"Wrote {catalog_path.relative_to(REPO_ROOT)}")
    elif not catalog_path.is_file():
        print(
            f"Missing {catalog_path}; run without --print-env-only first.",
            file=sys.stderr,
        )
        return 1
    print_env(
        catalog_path,
        show_dirty_git_exception=bool(args.print_dirty_git_exception),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Private-edge extension boundary

Parent epic: **#176**. This issue: **#180**.

## Goal

Extend the public core from a **separate private repository** without copying private files back into the public tree.

## Dependency direction (required)

```text
private repository
    depends on pinned public-core version (commit tag or release)
    provides private plugins / configuration
    stores private artifacts separately
```

Forbidden direction:

```text
public repository
    imports private files conditionally
    holds secret placeholders with real names
    copies private results into public artifacts/
```

Rules:

1. **Public core never depends on private edge** (no cyclic git/package dependency).
2. Public core contains **no private secrets** and no private result payloads.
3. Private edge **pins** a public-core version (tag or commit SHA) and may only consume published public APIs / packages.
4. Private artifacts stay in the private repo (or private object storage); they are never committed under public rtifacts/research/.

## What stays public vs private

| Layer | Public core | Private edge |
|-------|-------------|--------------|
| Engine / Spec / runner / registry | yes | consumes |
| Generic strategies / plugins | yes (OSS) | may add proprietary plugins |
| API keys, webhook secrets | never | only |
| Research run artifacts with edge alpha | never | only |
| Docs describing *that* a private edge may exist | yes (this file) | details of edge logic stay private |

## Extension points (public, intentional)

Public surfaces private code may call **without** forking core:

- Spec + plugin registry (register private strategies by name in private config)
- RunRequest / runner CLI against a pinned core version
- Artifact layout contract (docs/research/ARTIFACT_LAYOUT.md) for private-side storage mirroring

Public surfaces that **must not** grow private hooks:

- CI secrets for private repos
- Conditional imports of private packages in public Python modules
- Docs that embed private endpoints, keys, or strategy parameters

## Acceptance (issue #180)

- [x] Dependency arrow documented (private -> public only)
- [x] Forbidden reverse dependency listed
- [x] Artifact separation stated
- [x] Extension points vs non-extension points listed

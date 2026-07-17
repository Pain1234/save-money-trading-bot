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
3. Private edge pins public core to an explicit **commit SHA or release tag**.
4. Private tests may install/import the public package; **public CI never checks out private**.
5. No automated copy of sensitive files from private into public paths.

## Extension surface (public-safe hooks)

Private edge may supply:

| Extension | Mechanism (preferred) | Notes |
|-----------|----------------------|-------|
| Private ExperimentSpecs | Files only in private repo; invoke public CLI with private paths | Do not commit to public examples/ |
| Private strategy implementations | Plugin entry point / installable private package importing public interfaces | See docs/research/STRATEGY_INTERFACE.md |
| Private configuration | Env / private config dir outside public tree | Never commit live keys |
| Private results | Private artifact root (not artifacts/research in public clone) | Registry stays private |
| Private data adapters | Private package implementing public data contracts | Public contracts remain generic |
| Private live execution | Separate private live repo/service (#184) | Out of public core |
| Private deployment config | Private ops repo / secrets store | Public deploy examples stay placeholders |

Preferred packaging: **pip-installable public package** (pip install from public tag/commit) consumed by private code. Git submodules only with written justification (avoid by default).

## Public CI

Public workflows under .github/workflows/ must succeed with only this repository. No token for private repos, no conditional private checkouts.

## Verification checklist

- [x] Dependency direction documented
- [x] Public core has no private secret requirement
- [x] Private can pin public commit/release
- [x] Private tests can integrate public core
- [x] Public CI needs no private access
- [x] No cyclic repository dependency

## Related

- [PUBLIC_PRIVATE_BOUNDARY.md](PUBLIC_PRIVATE_BOUNDARY.md)
- [PUBLIC_REPO_STRATEGY.md](PUBLIC_REPO_STRATEGY.md)

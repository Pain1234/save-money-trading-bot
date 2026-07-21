# Security Audit (Auditor C)

**Issue/SHA:** #371 / `7b78eb9996eb16e6d2ec6a00c2e1908c518682d9`
**Boundary:** public-core source/history, dashboard auth, API exposure, artifacts and
public/private controls. No secret value is reproduced in this report.

## Result

No live key, wallet signer, private exchange order path or high-confidence credential was
identified. Secrets used by dashboard/control/database code are environment-only; `.env*`
is ignored except the placeholder `.env.example`; private research directories and
`artifacts/research/**` are ignored. The artifact-content endpoint is strongly fail-closed.

Security remains partial because Research mutations rely on network placement rather than
backend authentication (C-FINDING-01), audit payload redaction is shallow
(C-FINDING-04), auth abuse controls are process-local and trust a proxy header, and the
public response lacks several browser hardening headers.

## Public/private and live boundary

| Contract | Code/repository evidence | Assessment |
|---|---|---|
| No wallet signing/private exchange API | no signer/wallet/private-order implementation; paper README explicitly excludes it | VERIFIED |
| P5/private evidence stays out of public tree | `.gitignore` excludes private-research mirrors and `artifacts/research/**`; governance direction is private -> pinned public core | VERIFIED for tracked tree |
| Public CI does not checkout private repository | no workflow reference found | VERIFIED |
| Runtime volumes contain no private/P5 data | Railway filesystem unavailable | NOT_VERIFIABLE |
| Holdout remained closed during audit | no P5 data command/path accessed | VERIFIED for audit actions |

Canonical contracts: `docs/governance/PUBLIC_PRIVATE_BOUNDARY.md`,
`PRIVATE_EDGE_EXTENSION.md`, `PUBLIC_RELEASE_CHECKLIST.md`. The prior retrospective audit
also classifies historical token-like hits as scanner fixtures/placeholders; this audit
independently repeated a value-suppressing tree/history scan.

## Secret scan (values suppressed)

Method:

1. `git grep -I -l -E <high-risk-patterns>` on the audit tree; output restricted to paths.
2. `git log --all --format=COMMIT:%H --name-only -G <patterns>`; output restricted to
   commit/file names, never patches.
3. tracked env/credential/private-key filename enumeration.
4. spot-check of env readers, test fixtures and ignore rules.

Results:

- 35 current candidate files and 43 historical candidate file paths across 43 commits.
- Candidates were confined to documented local DB URLs/placeholders, config/test code,
  workflow test values and historical secret-scanner fixtures. No value is included here.
- Tracked sensitive-name inventory: `.env.example` and
  `src/lib/auth/credentials.ts`; no tracked `.env`, PEM or key file.
- **Credentials requiring rotation identified by this audit: none.** This does not claim a
  full scan of retained GitHub Actions logs, issues, Railway variables or private storage.

## Dashboard authentication/session

| Control | Evidence | Status |
|---|---|---|
| Session secret minimum | 32-character fail-closed check in middleware/server (`session.ts:19-24`, `middleware.ts:7-13`) | VERIFIED |
| Cookie | HttpOnly, Secure in production, SameSite=Lax, 12-hour max age (`session.ts:8-16`) | VERIFIED |
| Route gate | `/dashboard/*` and `/api/research/*` middleware match (`middleware.ts:22-32`) | VERIFIED in code/CI; authenticated runtime NOT_VERIFIABLE |
| Password storage | bcrypt hash from environment (`credentials.ts:11-28`) | VERIFIED |
| Login response | same 401 response for invalid credentials | VERIFIED in code |
| Login throttling | 10/minute in an in-memory map (`rate-limit.ts:1-21`) | PARTIAL |
| CSRF | SameSite=Lax plus JSON-only write handlers; no CSRF token or Origin validation | PARTIAL |

Rate limiting is per process, resets on restart/deploy and keys on the first
`X-Forwarded-For` element supplied to the app (`login/route.ts:15-18`). Whether Railway
sanitizes that header before it reaches Next is `NOT_VERIFIABLE`; no automated test covers
spoofing, multi-replica behavior, eviction or restart. The map has no cleanup until an IP is
seen again, so cardinality is unbounded over a long-lived process.

The public `/login` returned HTTP 200 at 2026-07-19T16:58:22Z. Observed headers included TLS
delivery, `Content-Type`, cache metadata and Railway/Next identifiers, but not
`Strict-Transport-Security`, `Content-Security-Policy`, `frame-ancestors`/`X-Frame-Options`,
`Referrer-Policy` or `X-Content-Type-Options`. No exploit was attempted; this is a
defense-in-depth gap, not evidence of current compromise.

## API/auth separation

The Next `/api/research/*` proxy is session-gated. The private FastAPI backend itself has no
auth dependency on the Research router; its middleware allows POST solely by path
(`readonly_api.py:98-109`, `research/api.py:791-812`). Railway networking is configured
manually outside the TOMLs. Thus:

- public dashboard auth: CODE_VERIFIED;
- direct API private placement: NOT_VERIFIABLE;
- backend authorization for Research mutations: NOT_IMPLEMENTED;
- paper control endpoints: absent from the standalone readonly app; embedded control API is
  disabled by default and API-key protected when enabled.

No permissive CORS configuration was found. This reduces direct browser attack surface but
does not replace backend authentication for private-network callers or future
misconfiguration.

## Audit-event redaction

`/api/v1/events` applies `_sanitize_payload` before returning payload JSON
(`readonly_api.py:566-605`). The implementation only redacts exact top-level keys
`api_key`, `password`, `secret`, and `database_url` (`paper_trading/api.py:699-706`). It is
not recursive and misses common names such as `token`, `authorization`, `cookie`,
`private_key` and credential-bearing URLs under other keys.

Safe synthetic reproduction (only booleans were printed):

```text
TOP_LEVEL_API_KEY_REDACTED=True
TOKEN_REDACTED=False
NESTED_SECRET_REDACTED=False
```

Current audit-event producers were not found to intentionally persist production secrets,
so no actual exposure is claimed. The protection is nevertheless insufficient as a stable
security boundary.

## Artifact-content security

The endpoint requires an active scorecard, a pinned run path, a trusted run checksum
manifest, matching checksums, a regular non-symlink file, supported JSON/text media and a
size limit (`research/artifact_content.py:71-351`). Traversal, encoded separators, absolute
paths, drive paths, symlink escape, unsealed/missing/tampered/invalidated evidence and media
limits have negative tests. The executed targeted suite passed.

The Next proxy preserves `X-Content-Type-Options: nosniff` and the verified checksum/path
headers (`research-api/proxy.ts:37-59`). It does not forward backend
`Content-Disposition: attachment`; this is a hardening/parity gap, not a demonstrated code
execution path because only JSON/plain text are allowed and `nosniff` is preserved.

## Candidate findings

| ID | Severity | Impact | Confidence | Stop criterion |
|---|---|---|---|---|
| C-FINDING-01 | P1 (High) | Direct Research backend writes are unauthenticated; network misconfiguration/private-network caller could mutate research evidence or start jobs. | High code / runtime exposure unknown | Keep P5 final evidence and holdout actions blocked until auth/isolation contract is accepted and verified. |
| C-FINDING-04 | P2 (Medium) | Nested or differently named credentials in an audit payload would be returned to the authenticated dashboard/API consumer. | High behavior / no current secret payload observed | If any audit producer can persist external/request payloads, stop exposing `/events` until payload provenance is reviewed; rotate only if an actual credential is found. |

## Not verified

- Railway variables, domains on API/worker, service-to-service ACLs and volume content.
- Historical GitHub issue/PR comments and all retained Actions log bodies.
- Authenticated production cookies/pages or rate-limit header behavior at Railway edge.
- Penetration testing, dependency CVE scan and container/image SBOM.

# Security Triage Baseline

This document separates actionable security work from expected audit noise so the security workflow stays meaningful.

## Current Local Audit Snapshot

### Python

Observed from `python -m pip_audit -r requirements.txt`:

- `pypdf==4.2.0` -> multiple CVEs; upgrade target currently lands in the `6.x` line
- `python-jose==3.3.0` -> known advisories; fix target `3.4.0`
- `starlette==0.37.2` -> known advisories; fix targets `0.40.0+` and `0.47.2+`
- `ecdsa==0.19.1` -> advisory present with no fix version reported by `pip-audit`

These are actionable because they affect runtime dependencies.

### Frontend

Observed from `npm audit --json` in `frontend/`:

- moderate advisories in the `vite` / `vitest` / `vite-node` / `@vitest/mocker` chain

These are currently dev-tooling issues, not production runtime dependencies.

## Triage Policy

- fail the security gate for runtime dependency vulnerabilities with a known supported upgrade path
- document and track dev-only advisories separately when they do not ship in production artifacts
- do not silently ignore recurring advisories; capture why they are deferred and what upgrade would clear them
- prefer dependency upgrades over workflow suppression

## Immediate Follow-Up

1. evaluate upgrading `python-jose` to `3.4.0`
2. evaluate the FastAPI / Starlette compatibility path needed to move past the reported `starlette` CVEs
3. test a `pypdf` upgrade on the document-ingest path because the fix jumps across major versions
4. decide whether frontend dev-tooling advisories should be allowed temporarily with this document as the justification until the Vite/Vitest major upgrade is scheduled

## Release Gate Use

Before tagging `v0.x.y`:

- rerun `pip-audit -r requirements.txt`
- rerun `npm audit --audit-level=moderate`
- update this document with the new result state
- reflect any remaining accepted risk in the release notes

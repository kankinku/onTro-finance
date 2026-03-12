# Versioning and Support

## Versioning Policy

- use `v0.x.y` while interfaces and deployment surfaces are still stabilizing
- bump `y` for fixes and operational hardening
- bump `x` for workflow, API, or deployment changes that require migration notes

## Release Inputs

- `CHANGELOG.md`
- green backend/frontend/starter/docker checks
- load baseline results from `scripts/load_baseline.py`
- backup/restore validation for release candidates

## Compatibility Notes

- Python: `3.11` or `3.12`
- frontend runtime: Node `20` in CI
- Docker deployment: single-node compose is the default supported production path

## Official Support Matrix

- `starter/local`: supported for evaluation and contributor onboarding
- `single-node compose`: supported for deployment
- `distributed with Redis`: supported preview for coordinated multi-instance operation
- `Windows EXE starter`: supported for local evaluation, not as the primary production deployment target

## Out of Scope for the Current Baseline

- managed cloud deployment runbooks beyond Docker Compose
- zero-downtime rolling upgrades across multiple app instances
- Kubernetes manifests and cluster operations
- production support for the Windows EXE packaging path
- security exceptions that are not captured in `docs/SECURITY_TRIAGE.md`

## Migration Note Expectation

If a release changes API behavior, env names, or compose profiles, add a short migration section to `CHANGELOG.md` before tagging.

# Release Notes Template

Use this template for the first `v0.x.y` releases.

## Summary

- one-line release goal
- one-line operational or workflow change
- one-line user-visible effect

## Included

- CI / workflow changes:
- runtime / compose changes:
- docs / release process changes:

## Migration Notes

- env changes:
- compose profile changes:
- API or workflow changes requiring operator action:

## Verification

- CI: backend / frontend / starter-smoke / docker-build green
- security: `pip-audit` and `npm audit` reviewed
- runtime: single-node / observability / distributed checks completed
- performance: `scripts/load_baseline.py` results attached

## Image Tags

- `vX.Y.Z`
- `latest`
- `sha-<commit>`

## Known Issues

- issue:
- workaround:

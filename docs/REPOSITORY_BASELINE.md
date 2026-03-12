# Repository Baseline

## Generated Artifact Policy

- Commit source, config, lockfiles, and packaging specs.
- Do not commit generated outputs from local builds or packaging.
- Treat these as generated artifacts:
  - `build/`
  - `dist/`
  - `frontend/dist/`
  - `frontend/node_modules/`
  - `frontend/*.tsbuildinfo`
- `onTroFinanceStarter.py` may serve `frontend/dist`, but that bundle is expected to be rebuilt by CI or packaging steps rather than stored in git.

## Release Baseline

- Use `v0.x.y` tags until the deployment surface is considered stable.
- Record user-visible changes in `CHANGELOG.md`.
- Tag Docker images with:
  - release tag: `vX.Y.Z`
  - moving tag: `latest`
  - optional trace tag: short commit SHA
- First release gate:
  - backend CI green
  - frontend CI green
  - starter smoke green
  - docker smoke green
  - clean working tree from generated artifacts after local build/test

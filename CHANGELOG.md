# Changelog

## Unreleased

### Added

- add the initial release-notes template for `v0.x.y` tags
- add a security triage baseline that separates actionable runtime issues from current dev-tooling noise

### Changed

- fix CI path assumptions and add frontend plus starter smoke coverage
- align starter-first environment defaults and generated artifact policy
- define the initial `v0.x.y` release baseline for tags and Docker images

### Migration Notes

- starter and local-first runs now assume `ONTRO_STORAGE_BACKEND=inmemory` by default in `.env.example`; set the Neo4j variables explicitly when using the compose-backed graph path
- generated outputs under `build/`, `dist/`, and `frontend/dist/` are release artifacts and should be rebuilt in CI or packaging instead of committed to git
- release images are expected to publish with the version tag, `latest`, and the Git SHA tag via `.github/workflows/release.yml`

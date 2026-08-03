# Changelog

All notable changes to this project will be documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses semantic versioning.

## [Unreleased]

### Added

- Cross-platform local bootstrap and launch scripts.
- Docker and Docker Compose deployment with runtime secret mounting.
- Hardened systemd installer with optional supervisor, AI review, and optimizer tiers.
- GitHub CI, community health files, and release documentation.

### Changed

- AI supervisor review now requires explicit `ARENA_SUPERVISOR_AI_ENABLED=true` opt-in.
- Model IDs and model credentials are no longer embedded in systemd units.
- The main systemd service no longer depends on a supervisor refresh timer.

## [0.1.0] - 2026-08-03

### Added

- Deterministic resource-first tactic, structured diagnostics, compatibility monitor, read-only supervisor, and bounded runtime optimizer.

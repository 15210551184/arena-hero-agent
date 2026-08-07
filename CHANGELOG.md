# Changelog

All notable changes to this project will be documented in this file. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses semantic versioning.

## [Unreleased]

### Added

- Hash-locked runtime and build dependency sets shared by local bootstrap, CI, Docker, and systemd installation.
- Versioned systemd releases with atomic `current` activation, interruption journaling, service-state restoration, and a standalone rollback command.
- Public documentation navigation, executable clone-first quick starts, compatibility fields in bug reports, and clearer community reporting guidance.
- Release tags now pass the complete reusable CI workflow before publishing, with version validation, SBOM, provenance, and image-digest reporting.
- Tolerant stationary-Core confirmation across short visibility gaps, while still requiring three real same-position observations before a raid.
- Structured v0.11 upkeep due/paid/deficit and excess-Unit damage diagnostics with deterministic supervisor and optional model-review triggers.
- Bounded long-range raids against confirmed stationary, unprotected Cores, with strike-distance hysteresis and immediate combat-pressure recall.
- Gameplay v0.13 and official SDK 0.2.8 compatibility, including conservative Ranger cell fire against a confirmed stationary Core during short visibility gaps.
- Gameplay v0.14 and official SDK 0.2.9 source compatibility: dynamic Unit
  pricing replaced per-Tick upkeep. The SDK pin now points to the reviewed
  `423d252` source commit (PyPI 0.2.9 not yet published), which drops the
  removed `population_tier` / `upkeep_next_tick` state fields and adds
  `unit_cost()` / `UNIT_BASE_COSTS`.
- Fleet cap raised from 19 to 34 (`MAX_WORKER_TARGET=27`) with cost-aware
  spawning through `unit_cost()`, plus an optional `--resource-target N`
  stockpile mode that banks resources and stops discretionary production and
  shield repair once the target is reached.
- Stockpile mode parks cargo Workers on a full Core (`STOCKPILE_HOLD`) instead
  of the pointless RETURN/CLEAR_CORE shuffle, and skips new harvest routing
  while the bank is full.
- Dashboard responsiveness fixes: `known_obstacles` memory is bounded to 16k
  cells (pruned nearest the Core), live snapshot streams are trimmed to 1000
  rows each, static map layers (explored/obstacles/resources) are cached to
  offscreen canvases, and the system-dynamics panel renders only the latest
  200 entries.
- Core deposit congestion fix: only the closest cargo Worker approaches the
  Core each Tick (`DEPOSIT_QUEUE` holds the rest in place), and a cargo Worker
  on the Core cell always leaves through the reserved delivery lane, using a
  legal second cell slot when the ring is occupied, so returning Workers can
  no longer deadlock around the Core.
- Queued cargo Workers now stage near the Core (move until within 2-3 cells and
  wait there) instead of freezing at their current position, so deposits
  pipeline smoothly once the Core cell frees.
- Pipelined Core deposits: queued cargo Workers advance to the adjacent ring
  while the current depositor is on the Core, and the next Worker enters the
  Core cell in the same Tick the depositor moves out (legal same-Tick swap), so
  the Core cell is never left idle between deposits.
- Fixed stockpile raid never firing when the bank target fills Core capacity:
  the `resource_space >= 10` gate no longer applies in `raid-policy stockpile`
  mode, so reaching the target at full storage still sends the strike group.
- New `--max-fleet-units` cap (19-150, default 34) with panel controls for
  worker target and fleet cap, enabling fleets up to 105 Units and the
  theoretical 525-resource maximum bank.
- New `--raid-policy hunt`: always-on aggression where Worker scouts reveal
  enemies and the spare Vanguards/Rangers patrol a wider ring and attack
  visible enemy Cores and Units (Workers prioritized) without needing
  stationary/unprotected confirmation.
- Dashboard Units, Enemies, and Resources panels now scroll independently
  (max-height 220px) instead of stretching the whole sidebar.
- New `--raid-policy stockpile` offense mode linked to `--resource-target`:
  once the bank target is reached, the Agent raids the nearest enemy Core with
  the spare defense fleet, then returns to stockpiling until the target is
  reached again. Raiding releases stockpile spending holds so heals, repairs,
  and replacement spawns can support the strike.
- Dashboard "运行设置" panel: stockpile target (default now `120`) and raid
  policy can be changed live from the page and persist to `runtime-config.json`
  beside the dashboard memory, so no `.env` edit or rebuild is needed.
- The "运行设置" controls moved to a header button with a popup dialog (like
  "手动探测") instead of an inline sidebar panel.
- Dashboard Units panel gains type filter pills: 全部(总数) / 工人 / 先锋 /
  游侠 with per-type counts; clicking a pill filters the unit list.
- Fixed a table rendering bug where array rows were interpolated directly,
  causing a visible run of commas above the Units/Enemies/Resources tables;
  empty filtered lists now show "无" instead of a blank table.
- Units 职责 column translations added for RETURN / RETURN_BLOCKED /
  CLEAR_CORE / CLEAR_CORE_BLOCKED; all 18 worker roles now render in Chinese.
- Hierarchical lifecycle and threat assessment with explicit posture/reason diagnostics for alerts, pre-evasion, engagement, multi-axis breakout, recovery, and compatibility hold.

### Changed

- The Docker base image is pinned to an immutable multi-architecture digest.
- GitHub Actions are pinned to full commit SHAs while retaining their reviewed major-version annotations.
- systemd upgrades now preflight host requirements, restart the Agent after compatibility validation, and support explicit supervisor, AI, and optimizer disable paths.
- Docker Compose now uses the same graceful `SIGINT` shutdown contract as systemd.
- Resource targets now use deterministic minimum-cost Worker matching with limited intent stickiness instead of preserving a worse assignment indefinitely.
- Scout routes prefer less recently covered chunks and rotate after three consecutive non-improving Ticks.

## [0.1.0] - 2026-08-03

### Added

- Cross-platform local bootstrap and launch scripts.
- Docker and Docker Compose deployment with runtime secret mounting.
- Hardened systemd installer with optional supervisor, AI review, and optimizer tiers.
- GitHub CI, community health files, and release documentation.
- Accepted-Turn heartbeat and deterministic unattended health checks for systemd and Compose.
- Deterministic resource-first tactic, structured diagnostics, compatibility monitor, read-only supervisor, and bounded runtime optimizer.
- Tag-driven GHCR release images for build-free Compose deployment.

### Changed

- AI supervisor review now requires explicit `ARENA_SUPERVISOR_AI_ENABLED=true` opt-in.
- Model IDs and model credentials are no longer embedded in systemd units.
- The main systemd service no longer depends on a supervisor refresh timer.
- systemd installation now requires an immediate compatibility check before starting the Agent.

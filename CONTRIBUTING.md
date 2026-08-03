# Contributing

Contributions should preserve the Agent's deterministic Tick loop, Core-survival priority, and secret-free testability.

## Setup

```bash
python -m venv .venv
python -m pip install -e .
python -m unittest discover -v
```

On Windows, `scripts/bootstrap.ps1` performs the same setup. On POSIX systems, use `sh scripts/bootstrap.sh`.

## Before Opening a Pull Request

Run:

```bash
python -m unittest discover -v
python -m compileall -q arena_farmer.py arena_supervisor.py arena_optimizer.py arena_version_monitor.py
python scripts/check_secrets.py
```

For deployment changes, also validate `docker build .`, `docker compose config`, shell syntax, and systemd units on Linux.

## Change Guidelines

- Use the official Arena Hero SDK; do not reproduce transport or state-model logic.
- Treat every Turn as a complete authoritative replacement and submit only current-Tick plans.
- Keep population below 20 unless the game contract and strategy goal explicitly change.
- Add focused tests for tactic decisions and all configuration behavior.
- Keep model output advisory. A model must not enter the per-Tick action path.
- Document any new process that can write configuration, restart services, or run with elevated privileges.
- Never include live API keys, model credentials, player identifiers, hostnames, IP addresses, or operational logs.

## Pull Requests

Keep each pull request scoped. Explain the observed problem, behavioral change, tests, and operational risk. Rule-dependent changes should cite the compatible game and SDK versions.

By contributing, you agree that your contribution is licensed under Apache-2.0.

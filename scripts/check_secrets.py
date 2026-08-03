from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "reports",
    "state",
}
EXCLUDED_NAMES = {".env", "0.2.4", "arena_farmer.log"}
PATTERNS = {
    "Arena Hero live key": re.compile(r"ah_(?:live|test)_[A-Za-z0-9_-]{20,}"),
    "model provider key": re.compile(r"(?:sk|xai)-[A-Za-z0-9_-]{24,}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def tracked_files() -> list[Path] | None:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        return None
    return [ROOT / item.decode() for item in completed.stdout.split(b"\0") if item]


def public_worktree_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if path.name in EXCLUDED_NAMES or path.name.startswith(".tmp-"):
            continue
        if path.suffix in {".log", ".pyc", ".pyo"}:
            continue
        if path.parent.name == "secrets" and not path.name.endswith(".example.txt"):
            continue
        files.append(path)
    return files


def main() -> int:
    findings: list[tuple[Path, int, str]] = []
    for path in tracked_files() or public_worktree_files():
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
            for label, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append((path.relative_to(ROOT), line_number, label))

    if findings:
        for path, line_number, label in findings:
            print(f"{path}:{line_number}: possible {label}", file=sys.stderr)
        return 1
    print("No credential patterns found in the public file set.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

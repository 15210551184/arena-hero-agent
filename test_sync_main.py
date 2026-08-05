from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parent / "scripts" / "sync-main.py"
SPEC = importlib.util.spec_from_file_location("sync_main", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
sync_main = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync_main)


def git(cwd: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


class SyncMainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.origin = root / "origin.git"
        self.seed = root / "seed"
        self.checkout = root / "checkout"
        git(root, "init", "--bare", str(self.origin))
        git(root, "clone", str(self.origin), str(self.seed))
        git(self.seed, "config", "user.email", "tests@example.invalid")
        git(self.seed, "config", "user.name", "Arena Hero Tests")
        git(self.seed, "switch", "-c", "main")
        (self.seed / "tracked.txt").write_text("one\n", encoding="utf-8")
        git(self.seed, "add", "tracked.txt")
        git(self.seed, "commit", "-m", "initial")
        git(self.seed, "push", "-u", "origin", "main")
        git(self.origin, "symbolic-ref", "HEAD", "refs/heads/main")
        git(root, "clone", str(self.origin), str(self.checkout))
        git(self.checkout, "config", "user.email", "tests@example.invalid")
        git(self.checkout, "config", "user.name", "Arena Hero Tests")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def push_remote_change(self, text: str = "two\n") -> str:
        (self.seed / "tracked.txt").write_text(text, encoding="utf-8")
        git(self.seed, "add", "tracked.txt")
        git(self.seed, "commit", "-m", text.strip())
        git(self.seed, "push", "origin", "main")
        return git(self.seed, "rev-parse", "HEAD")

    def test_current_main_is_accepted(self) -> None:
        commit = sync_main.synchronize(self.checkout)
        self.assertEqual(commit, git(self.checkout, "rev-parse", "origin/main"))

    def test_behind_main_is_fast_forwarded(self) -> None:
        remote = self.push_remote_change()
        commit = sync_main.synchronize(self.checkout)
        self.assertEqual(commit, remote)
        self.assertEqual((self.checkout / "tracked.txt").read_text(), "two\n")

    def test_dirty_tree_is_refused(self) -> None:
        (self.checkout / "untracked.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(sync_main.SyncError, "not clean"):
            sync_main.synchronize(self.checkout)

    def test_non_main_branch_is_refused(self) -> None:
        git(self.checkout, "switch", "-c", "topic")
        with self.assertRaisesRegex(sync_main.SyncError, "expected branch main"):
            sync_main.synchronize(self.checkout)

    def test_local_ahead_is_refused(self) -> None:
        (self.checkout / "local.txt").write_text("local\n", encoding="utf-8")
        git(self.checkout, "add", "local.txt")
        git(self.checkout, "commit", "-m", "local")
        with self.assertRaisesRegex(sync_main.SyncError, "ahead"):
            sync_main.synchronize(self.checkout)

    def test_diverged_main_is_refused(self) -> None:
        (self.checkout / "local.txt").write_text("local\n", encoding="utf-8")
        git(self.checkout, "add", "local.txt")
        git(self.checkout, "commit", "-m", "local")
        self.push_remote_change()
        with self.assertRaisesRegex(sync_main.SyncError, "diverged"):
            sync_main.synchronize(self.checkout)


if __name__ == "__main__":
    unittest.main()

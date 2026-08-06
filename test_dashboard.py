from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

import dashboard.server as server


class DashboardServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.snapshot_path = self.root / "snapshot.json"
        self.httpd = server.start_dashboard_thread(
            port=0,
            host="127.0.0.1",
            snapshot_path=self.snapshot_path,
            status_provider=lambda: {
                "pid": 123,
                "last_tick": 9,
                "last_activity_seconds_ago": 1.0,
            },
            api_key="test-only-key",
        )
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.directory.cleanup()

    def get(self, path: str) -> tuple[int, str]:
        with urlopen(self.base + path, timeout=5) as response:
            return response.status, response.read().decode("utf-8")

    def test_serves_light_index_page(self) -> None:
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("Arena Hero", body)
        self.assertNotIn("data-theme", body)

    def test_api_data_reports_missing_then_serves_snapshot(self) -> None:
        with patch.object(server, "MAX_WAIT", 0.3):
            status, body = self.get("/api/data")
        self.assertEqual(status, 200)
        self.assertIn("no data yet", body)

        snapshot = {"tick": 5, "resources": 10, "memory": {}}
        server.atomic_write_json(self.snapshot_path, snapshot)
        status, body = self.get("/api/data?since_mtime=0")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["tick"], 5)
        self.assertIn("_mtime", payload)

    def test_api_data_long_polls_for_update(self) -> None:
        with patch.object(server, "MAX_WAIT", 2.0):
            result: list[dict[str, object]] = []

            def request() -> None:
                _, body = self.get("/api/data?since_mtime=0")
                result.append(json.loads(body))

            thread = threading.Thread(target=request)
            thread.start()
            time.sleep(0.2)
            server.atomic_write_json(
                self.snapshot_path, {"tick": 6, "resources": 20, "memory": {}}
            )
            thread.join(timeout=3)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["tick"], 6)

    def test_unknown_route_returns_404(self) -> None:
        with self.assertRaises(HTTPError):
            self.get("/nope")

    def test_api_state_returns_status_provider(self) -> None:
        status, body = self.get("/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["last_tick"], 9)

    def test_api_probe_returns_verdict_shape(self) -> None:
        fake = {
            "at": "12:00:00",
            "target": "https://api.arenahero.io",
            "snapshot": {"exists": True, "fresh": True},
            "verdict": "一切正常",
        }
        with patch.object(server, "run_probe", return_value=fake):
            status, body = self.get("/api/probe")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["verdict"], "一切正常")


if __name__ == "__main__":
    unittest.main()

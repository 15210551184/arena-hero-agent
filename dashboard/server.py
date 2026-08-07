#!/usr/bin/env python3
"""Arena Hero 亮色数据面板服务（内嵌线程 + 独立模式）。"""

from __future__ import annotations

import json
import os
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from arena_health import atomic_write_json

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
ARENA_BASE = os.environ.get("ARENA_HERO_BASE_URL", "https://api.arenahero.io")
WEBSOCKET_PATH = "/api/v1/game/ws"
PROBE_TIMEOUT = 5

SNAPSHOT: Path = PROJECT / "snapshot.json"
STATE: Path = PROJECT / "state.json"
STATUS_PROVIDER: Callable[[], dict[str, Any] | None] | None = None
API_KEY: str | None = None
CONFIG_STORE: Any = None

POLL_STEP = 0.2
MAX_WAIT = 25.0


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def snapshot_probe(path: Path) -> dict[str, object]:
    try:
        mtime = os.path.getmtime(path)
        age = time.time() - mtime
        data = read_json(path)
        return {
            "exists": True,
            "tick": data.get("tick") if data else None,
            "age_seconds": round(age, 1),
            "fresh": age < 60,
        }
    except OSError:
        return {"exists": False}


def derive_ws_url(base_url: str) -> str:
    parsed = urllib.parse.urlsplit(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = parsed.path.rstrip("/") + WEBSOCKET_PATH
    return urllib.parse.urlunsplit((scheme, parsed.netloc, path, "", ""))


def ws_probe() -> dict[str, object]:
    ws_url = os.environ.get("ARENA_HERO_WS_URL") or derive_ws_url(ARENA_BASE)
    try:
        from websockets.sync.client import connect

        with connect(ws_url, open_timeout=PROBE_TIMEOUT, close_timeout=2):
            return {"ok": True, "url": ws_url, "note": "握手成功"}
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (401, 403):
            return {
                "ok": True,
                "url": ws_url,
                "note": f"服务端 HTTP {status}（通道可达）",
            }
        return {"ok": False, "url": ws_url, "error": f"{type(exc).__name__}: {exc}"}


def auth_ws_probe(recv_timeout: int = 15) -> dict[str, object]:
    key = API_KEY or _load_api_key()
    if not key:
        return {"ok": False, "note": "未找到 API key"}
    ws_url = os.environ.get("ARENA_HERO_WS_URL") or derive_ws_url(ARENA_BASE)
    try:
        from websockets.sync.client import connect

        headers = {"Authorization": f"Bearer {key}"}
        with connect(
            ws_url,
            additional_headers=headers,
            open_timeout=8,
            close_timeout=2,
            max_size=2 * 1024 * 1024,
        ) as ws:
            try:
                ws.recv(timeout=recv_timeout)
                return {"ok": True, "note": f"握手成功，{recv_timeout}s 内收到消息"}
            except TimeoutError:
                return {
                    "ok": False,
                    "note": f"握手成功但 {recv_timeout}s 内未收到消息",
                }
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (401, 403):
            return {"ok": False, "error": f"握手被拒绝 HTTP {status}（API key 无效？）"}
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _load_api_key() -> str | None:
    key = os.environ.get("ARENA_HERO_API_KEY")
    if key:
        return key
    env_file = PROJECT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ARENA_HERO_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def run_probe(bot=None) -> dict[str, object]:
    result: dict[str, object] = {"at": time.strftime("%H:%M:%S")}
    result["target"] = ARENA_BASE
    result["snapshot"] = snapshot_probe(SNAPSHOT)
    result["ws"] = ws_probe()
    result["ws_auth"] = auth_ws_probe()

    host = urllib.parse.urlparse(ARENA_BASE).hostname
    try:
        infos = socket.getaddrinfo(host, 443)
        result["dns"] = {"ok": True, "ip": infos[0][4][0]}
    except Exception as exc:
        result["dns"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    if result["dns"].get("ok"):
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((host, 443), timeout=PROBE_TIMEOUT) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    result["tls"] = {"ok": True, "tls_version": ssock.version()}
        except Exception as exc:
            result["tls"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    else:
        result["tls"] = {"ok": False, "error": "DNS 失败，跳过"}

    try:
        req = urllib.request.Request(ARENA_BASE, method="GET")
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as resp:
            result["http"] = {"ok": True, "status": resp.status}
    except urllib.error.HTTPError as exc:
        result["http"] = {"ok": True, "status": exc.code}
    except Exception as exc:
        result["http"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    snap_ok = bool(result["snapshot"].get("fresh"))
    net_ok = bool(result["http"].get("ok")) or bool(result["ws"].get("ok"))
    bot_ok = bot is not None and bot.get("last_activity_seconds_ago", 999) < 60
    if bot is None:
        result["verdict"] = "未检测到 bot 循环 → 数据页为独立模式"
    elif snap_ok and net_ok:
        result["verdict"] = "一切正常：数据在更新，服务器可达"
    elif bot_ok and net_ok:
        result["verdict"] = "bot 在运行但数据未更新 → 可能仍在连接/重连"
    elif net_ok:
        result["verdict"] = "网络可达但数据未更新 → bot 循环卡住"
    else:
        result["verdict"] = "网络不可达 → 检查本地网络 / 代理 / VPN"
    result["bot"] = bot
    return result


def wait_for_snapshot_change(
    path: Path,
    since_mtime: float,
    timeout: float = MAX_WAIT,
):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = None
        if mtime is not None and (since_mtime <= 0 or mtime > since_mtime):
            data = read_json(path)
            if data is not None:
                return mtime, data
        time.sleep(POLL_STEP)
    data = read_json(path)
    if data is None:
        return None, None
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None
    return mtime, data


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path, _, query = self.path.partition("?")
        if path in ("/", "/index.html"):
            self._send_file(ROOT / "index.html", "text/html; charset=utf-8")
        elif path == "/api/data":
            since_mtime = 0.0
            for part in query.split("&"):
                if part.startswith("since_mtime="):
                    try:
                        since_mtime = float(part.split("=", 1)[1])
                    except ValueError:
                        since_mtime = 0.0
            mtime, data = wait_for_snapshot_change(
                SNAPSHOT, since_mtime, timeout=MAX_WAIT
            )
            if data is None:
                body = json.dumps({"error": "no data yet"}).encode("utf-8")
            else:
                data["_mtime"] = mtime
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send_bytes(body, "application/json; charset=utf-8")
        elif path == "/api/state":
            data = STATUS_PROVIDER() if STATUS_PROVIDER else read_json(STATE)
            body = (
                json.dumps({"error": "no data yet"}).encode("utf-8")
                if data is None
                else json.dumps(data, ensure_ascii=False).encode("utf-8")
            )
            self._send_bytes(body, "application/json; charset=utf-8")
        elif path == "/api/probe":
            bot_status = STATUS_PROVIDER() if STATUS_PROVIDER else None
            self._send_bytes(
                json.dumps(run_probe(bot=bot_status), ensure_ascii=False).encode(
                    "utf-8"
                ),
                "application/json; charset=utf-8",
            )
        elif path == "/api/config":
            if CONFIG_STORE is None:
                self._send_bytes(
                    json.dumps({"error": "config store unavailable"}).encode(
                        "utf-8"
                    ),
                    "application/json; charset=utf-8",
                    status=404,
                )
            else:
                self._send_bytes(
                    json.dumps(
                        CONFIG_STORE.snapshot(),
                        ensure_ascii=False,
                    ).encode("utf-8"),
                    "application/json; charset=utf-8",
                )
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        path, _, _ = self.path.partition("?")
        if path != "/api/config":
            self.send_error(404)
            return
        if CONFIG_STORE is None:
            self._send_bytes(
                json.dumps({"error": "config store unavailable"}).encode(
                    "utf-8"
                ),
                "application/json; charset=utf-8",
                status=404,
            )
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("body must be a JSON object")
            snapshot = CONFIG_STORE.apply(payload)
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_bytes(
                json.dumps({"error": str(exc)}).encode("utf-8"),
                "application/json; charset=utf-8",
                status=400,
            )
            return
        self._send_bytes(
            json.dumps(snapshot, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _send_file(self, path: Path, ctype: str) -> None:
        if not path.exists():
            self.send_error(404)
            return
        self._send_bytes(path.read_bytes(), ctype)

    def _send_bytes(self, body: bytes, ctype: str, *, status: int = 200) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("[dashboard] %s\n" % (fmt % args))


def start_dashboard_thread(
    port: int = 8765,
    host: str = "127.0.0.1",
    snapshot_path: Path | None = None,
    status_provider=None,
    api_key: str | None = None,
    config_store=None,
):
    global SNAPSHOT, STATUS_PROVIDER, API_KEY, CONFIG_STORE
    if snapshot_path is not None:
        SNAPSHOT = Path(snapshot_path)
    STATUS_PROVIDER = status_provider
    API_KEY = api_key
    CONFIG_STORE = config_store
    try:
        httpd = ThreadingHTTPServer((host, port), Handler)
    except OSError as exc:
        print(f"[dashboard] 启动失败（端口 {port} 被占用？）: {exc}", flush=True)
        return None
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    print(
        f"dashboard: http://{host}:{port}  (与 bot pid={os.getpid()} 一起运行)",
        flush=True,
    )
    return httpd


def main() -> None:
    global SNAPSHOT
    SNAPSHOT = Path(
        os.environ.get("ARENA_HERO_SNAPSHOT_FILE", str(PROJECT / "snapshot.json"))
    )
    port = int(
        os.environ.get(
            "DASHBOARD_PORT", sys.argv[1] if len(sys.argv) > 1 else "8765"
        )
    )
    print(f"dashboard: http://127.0.0.1:{port}  (Ctrl-C 停止)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()

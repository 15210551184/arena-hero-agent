# 亮色数据面板（Light Dashboard）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给无人值守 agent 增加内嵌亮色数据面板：每 Tick 导出 snapshot.json，面板进程内
提供服务（默认 127.0.0.1:8765），浏览器可看实时地图、HUD、单位/敌方/资源、指令队列、
事件流与网络探测。

**Architecture:** agent（`arena_farmer.py`）每 Tick 构建并原子写一份快照 JSON；
新增 `dashboard/` 包提供内嵌线程 HTTP 服务（长轮询快照文件）与独立模式；页面为单文件
亮色 HTML（从本机参考实现 `arena-hero-balanced/dashboard/` 改编）。

**Tech Stack:** Python 3.11+、stdlib `http.server`/`threading`/`json`（不新增第三方依赖）、
项目现有 unittest 测试体系、Docker Compose。

## Global Constraints

- 改源码/文档前必须先跑 `python scripts/sync-main.py`，且必须报告 `up-to-date` 或
  `fast-forwarded`；树必须干净、分支必须为 `main`。
- Python >= 3.11；测试命令 `python -m unittest discover -v`（CI 同款）。
- 不新增第三方依赖；面板服务只用标准库。
- 面板默认绑定 `127.0.0.1`；密钥绝不写入快照、日志或页面。
- 快照 `schema_version: 1`；列表类记忆上限：轨迹每单位 40、日志/事件/历史各 200、
  探索单元格 5000。
- 页面仅亮色主题（不保留深色主题与切换按钮）。
- 每个 Task 结束必须提交（commit message 遵循 `feat:` / `test:` / `docs:` 前缀）。

---

## File Structure

| 文件 | 动作 | 职责 |
| --- | --- | --- |
| `arena_farmer.py` | 修改 | `DashboardMemory`、快照构建函数、CLI 参数、`play()` 集成 |
| `dashboard/__init__.py` | 新建 | 空包标记 |
| `dashboard/server.py` | 新建 | 内嵌/独立 HTTP 服务、探测、长轮询 |
| `dashboard/index.html` | 新建 | 亮色单文件页面（参考页改编） |
| `test_arena_farmer.py` | 修改 | 快照构建、CLI、`play()` 写快照测试 |
| `test_dashboard.py` | 新建 | server 路由/长轮询/探测测试 |
| `pyproject.toml` | 修改 | setuptools 打包纳入 `dashboard` 包 |
| `Dockerfile` | 修改 | 镜像内 `COPY dashboard ./dashboard` |
| `compose.yaml` | 修改 | agent 命令加 `--snapshot-file`，可选端口映射 |
| `README.md`、`docs/configuration.md` | 修改 | 面板使用说明、CLI 表格 |

接口约定（后续 Task 引用）：

- `DashboardMemory`：`update(turn, tactic) -> None`、`view(tactic) -> dict`
- `build_snapshot(turn, tactic, memory) -> dict`
- `arena_farmer.play(..., snapshot_file, dashboard_port, dashboard_host, dashboard_enabled)`
- `dashboard.server.start_dashboard_thread(port, host, snapshot_path, status_provider, api_key)`
- `dashboard.server.main()`（独立模式）

---

### Task 1: 快照构建（DashboardMemory + build_snapshot）

**Files:**
- Modify: `arena_farmer.py`（导入、常量、新类与函数；放在 `ResourceLedgerSnapshot`
  定义之前）
- Test: `test_arena_farmer.py`

**Interfaces:**
- Produces: `DashboardMemory`、`build_snapshot(turn, tactic, memory)`、
  `_tick_log_rows(turn, tactic)`、`_event_log_row(event)`、`_core_view(turn)`、
  `_units_view(turn)`、`_enemies_view(turn)`、`_enemy_sightings_view(tactic)`、
  `_threat_ghosts_view(tactic)`

- [ ] **Step 1: 写失败测试**

在 `test_arena_farmer.py` 的 import 里追加：

```python
from arena_farmer import (
    DashboardMemory,
    build_snapshot,
)
```

在 `ResourceLedgerTests` 类后新增 `DashboardSnapshotTests`：

```python
class DashboardSnapshotTests(unittest.TestCase):
    def test_snapshot_contains_turn_and_tactic_state(self) -> None:
        turn = make_turn(
            tick=7,
            units=[
                unit(WORKER_1, "WORKER", (0, 0), cargo=3),
                unit(VANGUARD_1, "VANGUARD", (1, 1)),
            ],
            enemies=[enemy_core(ENEMY_1, (5, 5))],
            resource_cells=[(2, 2)],
            obstacles=[(3, 3)],
            resources=42,
            core=True,
        )
        tactic = CoreFarmer()
        tactic.choose_actions(turn)
        memory = DashboardMemory()
        memory.update(turn, tactic)
        snapshot = build_snapshot(turn, tactic, memory)

        self.assertEqual(snapshot["schema_version"], 1)
        self.assertEqual(snapshot["tick"], 7)
        self.assertEqual(snapshot["resources"], 42)
        self.assertEqual(len(snapshot["units"]), 2)
        self.assertEqual(snapshot["units"][0]["cargo"], 3)
        self.assertIsNotNone(snapshot["core"])
        self.assertEqual(len(snapshot["visible_enemies"]), 1)
        self.assertIn([2, 2], snapshot["visible_resources"])
        self.assertIn([3, 3], snapshot["known_obstacles"])
        self.assertIn("unit_actions", snapshot["plan"])
        self.assertEqual(snapshot["tactic"]["worker_target"], 12)
        self.assertIn("strategy_phase", snapshot["tactic"])
        self.assertIn("global_posture", snapshot["tactic"])

    def test_memory_tracks_explored_resources_and_trajectories(self) -> None:
        turn = make_turn(tick=1, units=[unit(WORKER_1, "WORKER", (0, 0))])
        tactic = CoreFarmer()
        tactic.choose_actions(turn)
        memory = DashboardMemory()
        memory.update(turn, tactic)
        view = memory.view(tactic)
        self.assertIn([0, 0], view["explored"])
        self.assertIn("0,0", view["trajectories"])
        self.assertEqual(view["trajectories"]["0,0"][-1], [0, 0])

    def test_memory_caps_trajectory_and_rows(self) -> None:
        memory = DashboardMemory(max_trajectory=2, max_rows=1)
        tactic = CoreFarmer()
        for tick, position in ((1, (0, 0)), (2, (1, 0)), (3, (2, 0))):
            turn = make_turn(
                tick=tick,
                units=[unit(WORKER_1, "WORKER", position)],
            )
            tactic.choose_actions(turn)
            memory.update(turn, tactic)
        self.assertEqual(len(memory.trajectories[UUID(WORKER_1)]), 2)
        self.assertEqual(len(memory.tick_log), 1)

    def test_snapshot_round_trips_through_json_file(self) -> None:
        turn = make_turn(tick=1, units=[unit(WORKER_1, "WORKER", (0, 0))])
        tactic = CoreFarmer()
        tactic.choose_actions(turn)
        memory = DashboardMemory()
        memory.update(turn, tactic)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            from arena_health import atomic_write_json

            atomic_write_json(path, build_snapshot(turn, tactic, memory))
            loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["tick"], 1)
        self.assertIn("generated_at", loaded)
```

注意：测试文件顶部需要 `import json`（已存在）和 `import tempfile`（已存在）、
`from pathlib import Path`（已存在）。`make_turn`/`unit`/`enemy_core` 使用文件中
已有 fixture。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m unittest -v test_arena_farmer.DashboardSnapshotTests`
Expected: FAIL（`ImportError: cannot import name 'DashboardMemory'`）

- [ ] **Step 3: 实现**

`arena_farmer.py` 修改导入与常量：

```python
from dataclasses import dataclass, field
from datetime import UTC, datetime
from arena_health import atomic_write_json, write_heartbeat
```

```python
DEFAULT_DASHBOARD_PORT = 8765
DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_SNAPSHOT_FILE = Path("snapshot.json")
SNAPSHOT_SCHEMA_VERSION = 1
DASHBOARD_MAX_TRAJECTORY = 40
DASHBOARD_MAX_ROWS = 200
DASHBOARD_MAX_EXPLORED = 5000
```

在 `ThreatAssessment` 类之后、`ResourceLedgerSnapshot` 之前加入：

```python
@dataclass(slots=True)
class DashboardMemory:
    max_trajectory: int = DASHBOARD_MAX_TRAJECTORY
    max_rows: int = DASHBOARD_MAX_ROWS
    max_explored: int = DASHBOARD_MAX_EXPLORED
    trajectories: dict[UUID, deque[Position]] = field(default_factory=dict)
    explored: dict[Position, int] = field(default_factory=dict)
    resources_first_seen: dict[Position, int] = field(default_factory=dict)
    resources_last_seen: dict[Position, int] = field(default_factory=dict)
    tick_log: deque[dict[str, object]] = field(default_factory=deque)
    event_log: deque[dict[str, object]] = field(default_factory=deque)
    history: deque[dict[str, object]] = field(default_factory=deque)
    last_phase: str | None = None
    last_threat_level: str | None = None
    last_recovery: bool | None = None
    last_compatibility_hold: bool | None = None

    def update(self, turn: Turn, tactic: CoreFarmer) -> None:
        for unit in turn.units:
            self.trajectories.setdefault(
                unit.id, deque(maxlen=self.max_trajectory)
            ).append(unit.position)
            self._observe(unit.position, turn.tick)
        for enemy in turn.visible_enemies:
            self._observe(enemy.position, turn.tick)
        if turn.core is not None:
            self._observe(turn.core.position, turn.tick)
        for position in turn.obstacle_cells:
            self._observe(position, turn.tick)
        for position in turn.resource_cells:
            self.resources_last_seen[position] = turn.tick
            self.resources_first_seen.setdefault(position, turn.tick)

        for row in _tick_log_rows(turn, tactic):
            self.tick_log.append(row)
        while len(self.tick_log) > self.max_rows:
            self.tick_log.popleft()
        for event in turn.events:
            self.event_log.append(_event_log_row(event))
        while len(self.event_log) > self.max_rows:
            self.event_log.popleft()

        phase = tactic.strategy_phase(turn)
        threat_level = tactic.threat_assessment.level.value
        recovery = tactic.recovery_mode
        compatibility_hold = tactic.compatibility_hold
        current = (phase, threat_level, recovery, compatibility_hold)
        previous = (
            self.last_phase,
            self.last_threat_level,
            self.last_recovery,
            self.last_compatibility_hold,
        )
        if current != previous:
            self.history.append(
                {
                    "tick": turn.tick,
                    "text": (
                        f"phase={phase} threat={threat_level} "
                        f"recovery={int(recovery)} "
                        f"compatibility_hold={int(compatibility_hold)}"
                    ),
                }
            )
            while len(self.history) > self.max_rows:
                self.history.popleft()
            (
                self.last_phase,
                self.last_threat_level,
                self.last_recovery,
                self.last_compatibility_hold,
            ) = current

    def _observe(self, position: Position, tick: int) -> None:
        if position in self.explored:
            return
        self.explored[position] = tick
        if len(self.explored) > self.max_explored + self.max_explored // 10:
            oldest = sorted(self.explored, key=self.explored.get)[
                : self.max_explored // 10
            ]
            for key in oldest:
                del self.explored[key]

    def view(self, tactic: CoreFarmer) -> dict[str, object]:
        resources: dict[str, dict[str, object]] = {}
        for position, last_seen in self.resources_last_seen.items():
            key = f"{position[0]},{position[1]}"
            resources[key] = {
                "position": list(position),
                "source": "RESOURCE",
                "first_seen_tick": self.resources_first_seen.get(
                    position, last_seen
                ),
                "last_seen_tick": last_seen,
                "confirmed_empty": False,
            }
        return {
            "explored": [list(position) for position in self.explored],
            "obstacles": [list(position) for position in tactic.known_obstacles],
            "resources": resources,
            "trajectories": {
                str(unit_id): [list(position) for position in trail]
                for unit_id, trail in self.trajectories.items()
            },
            "enemy_sightings": _enemy_sightings_view(tactic),
            "threat_ghosts": _threat_ghosts_view(tactic),
        }


def _enemy_sightings_view(tactic: CoreFarmer) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for enemy_id, sighting in tactic.enemy_unit_sightings.items():
        motion = tactic.enemy_unit_motion.get(enemy_id)
        rows.append(
            {
                "id": str(enemy_id),
                "kind": "UNIT",
                "unit_type": (
                    motion.unit_type.value if motion is not None else "UNKNOWN"
                ),
                "position": list(sighting.position),
                "last_seen_tick": sighting.last_tick,
                "stationary": False,
            }
        )
    for enemy_id, sighting in tactic.enemy_core_sightings.items():
        rows.append(
            {
                "id": str(enemy_id),
                "kind": "CORE",
                "unit_type": "CORE",
                "position": list(sighting.position),
                "last_seen_tick": sighting.last_tick,
                "stationary": enemy_id in tactic.stationary_core_memory,
            }
        )
    return rows


def _threat_ghosts_view(tactic: CoreFarmer) -> list[dict[str, object]]:
    return [
        {
            "id": str(ghost.id),
            "position": list(ghost.position),
            "unit_type": ghost.unit_type.value,
            "expires_tick": ghost.expires_tick,
        }
        for ghost in tactic.recent_attack_threats.values()
    ]


def _tick_log_rows(turn: Turn, tactic: CoreFarmer) -> list[dict[str, object]]:
    plan = turn.plan.model_dump(mode="json", exclude_none=True)
    actions = plan.get("unit_actions", {})
    rows: list[dict[str, object]] = []
    for unit in sorted(turn.units, key=lambda candidate: str(candidate.id)):
        action = actions.get(str(unit.id), {})
        action_type = action.get("type", "NONE")
        direction = action.get("direction")
        next_position: list[int] | None = None
        if direction is not None:
            delta = Direction(direction).delta
            next_position = [
                unit.position[0] + delta[0],
                unit.position[1] + delta[1],
            ]
        rows.append(
            {
                "tick": turn.tick,
                "unit_id": str(unit.id),
                "unit_type": unit.unit_type.value,
                "pos": list(unit.position),
                "next": next_position,
                "action": action_type,
                "hp": unit.hp,
                "cargo": unit.cargo if hasattr(unit, "cargo") else None,
                "role": tactic.worker_modes.get(unit.id, "—"),
            }
        )
    return rows


def _event_log_row(event: object) -> dict[str, object]:
    return {
        "tick": event.tick,
        "type": event.event_type,
        "reason": event.reason_code,
        "actor": str(event.actor_id) if event.actor_id is not None else None,
        "target": str(event.target_id) if event.target_id is not None else None,
        "pos": list(event.position) if event.position is not None else None,
    }


def _core_view(turn: Turn) -> dict[str, object] | None:
    if turn.core is None:
        return None
    return turn.core.view.model_dump(mode="json", exclude_none=True)


def _units_view(turn: Turn) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for unit in turn.units:
        view = unit.view.model_dump(mode="json", exclude_none=True)
        rows.append(
            {
                "id": view["id"],
                "unit_type": view["unit_type"],
                "position": view["position"],
                "hp": view["hp"],
                "cargo": view.get("cargo"),
            }
        )
    return rows


def _enemies_view(turn: Turn) -> list[dict[str, object]]:
    return [
        enemy.model_dump(mode="json", exclude_none=True)
        for enemy in turn.visible_enemies
    ]


def build_snapshot(
    turn: Turn,
    tactic: CoreFarmer,
    memory: DashboardMemory,
) -> dict[str, object]:
    threat = tactic.threat_assessment
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC)
        .astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "tick": turn.tick,
        "resources": turn.resources,
        "resource_capacity": turn.resource_capacity,
        "resource_space": turn.resource_space,
        "core": _core_view(turn),
        "units": _units_view(turn),
        "visible_enemies": _enemies_view(turn),
        "visible_resources": [list(p) for p in sorted(turn.resource_cells)],
        "known_obstacles": [list(p) for p in sorted(tactic.known_obstacles)],
        "plan": turn.plan.model_dump(mode="json", exclude_none=True),
        "tactic": {
            "strategy_phase": tactic.strategy_phase(turn),
            "worker_target": tactic.worker_target,
            "beacon_policy": tactic.beacon_policy,
            "global_posture": threat.global_posture.value,
            "threat_level": threat.level.value,
            "threat_reason": threat.primary_reason,
            "recovery": tactic.recovery_mode,
            "combat_pressure": threat.combat_pressure,
            "compatibility_hold": tactic.compatibility_hold,
            "worker_modes": {
                str(unit_id): mode for unit_id, mode in tactic.worker_modes.items()
            },
            "worker_targets": {
                str(unit_id): list(target)
                for unit_id, target in tactic.worker_targets.items()
            },
        },
        "memory": memory.view(tactic),
        "tick_log": list(memory.tick_log),
        "event_log": list(memory.event_log),
        "history": list(memory.history),
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m unittest -v test_arena_farmer.DashboardSnapshotTests`
Expected: PASS（4 个测试）

- [ ] **Step 5: 全量回归**

Run: `python -m unittest discover -v`
Expected: 现有 + 新增全部 PASS

- [ ] **Step 6: 提交**

```bash
git add arena_farmer.py test_arena_farmer.py
git commit -m "feat: build per-tick dashboard snapshot"
```

---

### Task 2: CLI 参数

**Files:**
- Modify: `arena_farmer.py`（`build_parser`）
- Test: `test_arena_farmer.py`（`EventLoopTests`）

**Interfaces:**
- Produces: `args.snapshot_file: Path`、`args.dashboard_port: int`、
  `args.dashboard_host: str`、`args.no_dashboard: bool`

- [ ] **Step 1: 写失败测试**

在 `EventLoopTests` 中追加：

```python
    def test_dashboard_cli_flags_parse(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "--no-dashboard",
                "--dashboard-port",
                "9000",
                "--dashboard-host",
                "0.0.0.0",
                "--snapshot-file",
                "/tmp/arena-hero-snapshot.json",
            ]
        )
        self.assertTrue(args.no_dashboard)
        self.assertEqual(args.dashboard_port, 9000)
        self.assertEqual(args.dashboard_host, "0.0.0.0")
        self.assertEqual(args.snapshot_file, Path("/tmp/arena-hero-snapshot.json"))

    def test_dashboard_defaults(self) -> None:
        args = build_parser().parse_args([])
        self.assertFalse(args.no_dashboard)
        self.assertEqual(args.dashboard_port, 8765)
        self.assertEqual(args.dashboard_host, "127.0.0.1")
        self.assertEqual(args.snapshot_file, Path("snapshot.json"))
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m unittest -v test_arena_farmer.EventLoopTests.test_dashboard_cli_flags_parse`
Expected: FAIL（AttributeError / 参数解析报错）

- [ ] **Step 3: 实现**

在 `build_parser()` 的 `--stale-turn-timeout-seconds` 之后追加：

```python
    parser.add_argument(
        "--snapshot-file",
        type=Path,
        default=DEFAULT_SNAPSHOT_FILE,
        help="Atomically write a dashboard snapshot JSON after every accepted Turn.",
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=DEFAULT_DASHBOARD_PORT,
        help="Port for the embedded light dashboard (default 8765).",
    )
    parser.add_argument(
        "--dashboard-host",
        default=DEFAULT_DASHBOARD_HOST,
        help="Bind address for the embedded dashboard (default 127.0.0.1).",
    )
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Disable the embedded dashboard server.",
    )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m unittest -v test_arena_farmer.EventLoopTests.test_dashboard_cli_flags_parse test_arena_farmer.EventLoopTests.test_dashboard_defaults`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add arena_farmer.py test_arena_farmer.py
git commit -m "feat: add dashboard CLI flags"
```

---

### Task 3: play() 集成（写快照 + 内嵌面板线程）

**Files:**
- Modify: `arena_farmer.py`（`play`、`main`）
- Test: `test_arena_farmer.py`（`EventLoopTests`）

**Interfaces:**
- Consumes: Task 1 的 `DashboardMemory`/`build_snapshot`；Task 2 的 CLI 参数
- Produces: `play(..., snapshot_file: Path, dashboard_port: int,
  dashboard_host: str, dashboard_enabled: bool)`；依赖
  `dashboard.server.start_dashboard_thread`（Task 4 实现，本 Task 用 `ImportError`
  兜底）

- [ ] **Step 1: 写失败测试**

在 `EventLoopTests` 中追加：

```python
    def test_play_writes_dashboard_snapshot(self) -> None:
        events: list[Turn] = [make_turn(tick=3, units=[unit(WORKER_1, "WORKER", (0, 0))])]

        class FakeGame:
            def __init__(self, **_kwargs: object) -> None:
                self.closed = threading.Event()

            def __enter__(self) -> FakeGame:
                return self

            def __exit__(self, *_args: object) -> None:
                self.close()

            def close(self) -> None:
                self.closed.set()

            def events(self):
                yield from events
                self.closed.wait(timeout=0.1)

        with tempfile.TemporaryDirectory() as directory:
            snapshot_file = Path(directory) / "snapshot.json"
            with patch("arena_farmer.ArenaHeroClient", FakeGame):
                with self.assertRaises(OSError):
                    play(
                        "test-only-key",
                        base_url="https://example.test",
                        worker_target=12,
                        beacon_policy="retreat",
                        snapshot_file=snapshot_file,
                        dashboard_enabled=False,
                        stale_turn_timeout_seconds=0.05,
                    )
            loaded = json.loads(snapshot_file.read_text(encoding="utf-8"))
        self.assertEqual(loaded["tick"], 3)
        self.assertEqual(len(loaded["units"]), 1)
        self.assertIn("memory", loaded)
```

注意：FakeGame 构造用 `**_kwargs` 接收新参数；事件流结束/超时后 `play` 抛
`OSError`（与现有 `test_stale_turn_watchdog_closes_stream_for_supervisor_restart`
一致），所以测试用 `assertRaises(OSError)` 包住调用，快照在抛出前已写入。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m unittest -v test_arena_farmer.EventLoopTests.test_play_writes_dashboard_snapshot`
Expected: FAIL（TypeError: play() got an unexpected keyword argument 'snapshot_file'）

- [ ] **Step 3: 实现**

`play()` 签名追加参数：

```python
def play(
    api_key: str,
    *,
    base_url: str,
    worker_target: int,
    beacon_policy: str,
    compatibility_marker: Path | None = DEFAULT_COMPATIBILITY_MARKER,
    heartbeat_file: Path | None = None,
    stale_turn_timeout_seconds: float = DEFAULT_STALE_TURN_TIMEOUT_SECONDS,
    snapshot_file: Path = DEFAULT_SNAPSHOT_FILE,
    dashboard_port: int = DEFAULT_DASHBOARD_PORT,
    dashboard_host: str = DEFAULT_DASHBOARD_HOST,
    dashboard_enabled: bool = True,
) -> None:
```

在 `play()` 中、`resource_ledger_snapshot` 初始化之后（`with ArenaHeroClient(...)`
之前）加入：

```python
    memory = DashboardMemory()
    activity = {"monotonic": time.monotonic()}
    if dashboard_enabled:
        try:
            from dashboard.server import start_dashboard_thread
        except ImportError as exc:
            print(f"WARNING dashboard unavailable: {exc}", file=sys.stderr)
        else:
            start_dashboard_thread(
                port=dashboard_port,
                host=dashboard_host,
                snapshot_path=snapshot_file,
                status_provider=lambda: {
                    "pid": os.getpid(),
                    "last_tick": last_accepted_tick,
                    "last_activity_seconds_ago": round(
                        time.monotonic() - activity["monotonic"], 1
                    ),
                },
                api_key=api_key,
            )
```

`last_accepted_tick: int | None = None` 在 `tactic` 之后已初始化（现有代码），
lambda 引用的是外层变量，闭包读取最新值。

在 Tick 循环里 `watchdog.mark_accepted()` 之后追加：

```python
                activity["monotonic"] = time.monotonic()
                memory.update(turn, tactic)
                snapshot = build_snapshot(turn, tactic, memory)
                try:
                    atomic_write_json(snapshot_file, snapshot)
                except OSError as exc:
                    print(
                        f"WARNING dashboard snapshot write failed: {exc}",
                        file=sys.stderr,
                    )
```

`main()` 里 `play(...)` 调用追加参数：

```python
        play(
            api_key,
            base_url=args.base_url,
            worker_target=args.worker_target,
            beacon_policy=args.beacon_policy,
            compatibility_marker=args.compatibility_marker,
            heartbeat_file=args.heartbeat_file,
            stale_turn_timeout_seconds=args.stale_turn_timeout_seconds,
            snapshot_file=args.snapshot_file,
            dashboard_port=args.dashboard_port,
            dashboard_host=args.dashboard_host,
            dashboard_enabled=not args.no_dashboard,
        )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m unittest -v test_arena_farmer.EventLoopTests.test_play_writes_dashboard_snapshot`
Expected: PASS（快照文件存在且 tick=3）

- [ ] **Step 5: 全量回归**

Run: `python -m unittest discover -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add arena_farmer.py test_arena_farmer.py
git commit -m "feat: write dashboard snapshot each tick and start embedded server"
```

---

### Task 4: dashboard/server.py

**Files:**
- Create: `dashboard/__init__.py`（空文件）
- Create: `dashboard/server.py`
- Test: `test_dashboard.py`（新建）
- Modify: `pyproject.toml`（打包包含 `dashboard` 包）

**Interfaces:**
- Produces: `start_dashboard_thread(port, host, snapshot_path, status_provider,
  api_key) -> ThreadingHTTPServer | None`；`main()`（独立模式，端口参数可选）；
  `Handler`（`/`、`/index.html`、`/api/data?since_mtime=`、`/api/state`、
  `/api/probe`）

- [ ] **Step 1: 写失败测试**

新建 `test_dashboard.py`：

```python
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

import dashboard.server as server


class DashboardServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.snapshot_path = self.root / "snapshot.json"
        self.state_path = self.root / "state.json"
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
        with self.assertRaises(Exception):
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
```

文件头部补 `import time`。`atomic_write_json` 从 `arena_health` 导入到
`dashboard/server.py` 并在测试里用 `server.atomic_write_json` 引用。

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m unittest -v test_dashboard`
Expected: FAIL（ModuleNotFoundError: No module named 'dashboard'）

- [ ] **Step 3: 实现 dashboard/server.py**

创建 `dashboard/__init__.py`（空文件）与 `dashboard/server.py`（从参考实现
`/Users/xushaofan/java/project/ai/arena-hero-balanced/dashboard/server.py`
移植，按下列差异改写）：

```python
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

from arena_health import atomic_write_json

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
ARENA_BASE = os.environ.get("ARENA_HERO_BASE_URL", "https://api.arenahero.io")
WEBSOCKET_PATH = "/api/v1/game/ws"
PROBE_TIMEOUT = 5

SNAPSHOT: Path = PROJECT / "snapshot.json"
STATE: Path = PROJECT / "state.json"
STATUS_PROVIDER = None
API_KEY: str | None = None

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


def wait_for_snapshot_change(path: Path, since_mtime: float, timeout: float = MAX_WAIT):
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
            mtime, data = wait_for_snapshot_change(SNAPSHOT, since_mtime)
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
        else:
            self.send_error(404)

    def _send_file(self, path: Path, ctype: str) -> None:
        if not path.exists():
            self.send_error(404)
            return
        self._send_bytes(path.read_bytes(), ctype)

    def _send_bytes(self, body: bytes, ctype: str) -> None:
        try:
            self.send_response(200)
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
):
    global SNAPSHOT, STATUS_PROVIDER, API_KEY
    if snapshot_path is not None:
        SNAPSHOT = Path(snapshot_path)
    STATUS_PROVIDER = status_provider
    API_KEY = api_key
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
```

`pyproject.toml` 追加（保持 `py-modules` 不变）：

```toml
[tool.setuptools.packages.find]
include = ["dashboard*"]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m unittest -v test_dashboard`
Expected: PASS（6 个测试）

- [ ] **Step 5: 全量回归**

Run: `python -m unittest discover -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add dashboard/__init__.py dashboard/server.py test_dashboard.py pyproject.toml
git commit -m "feat: add embedded dashboard server with long-poll and probes"
```

---

### Task 5: dashboard/index.html（亮色页面）

**Files:**
- Create: `dashboard/index.html`

**Interfaces:**
- Consumes: Task 1 的快照 schema（`data.units`、`data.visible_enemies`、
  `data.core`、`data.plan`、`data.memory.*`、`data.tick_log`、
  `data.event_log`、`data.history`、`data.tactic`）
- Produces: 供 `Handler` 直接吐出的单文件页面

- [ ] **Step 1: 复制参考页并应用改动**

```bash
cp /Users/xushaofan/java/project/ai/arena-hero-balanced/dashboard/index.html dashboard/index.html
```

然后做以下精确修改：

1. **主题**：删除 `:root` 块里的深色变量与 `:root[data-theme="light"]` 块，只保留
   亮色变量的取值，直接作为 `:root`（`color-scheme: light; --bg: #f2f4f8; ...`，
   从参考页第 45-81 行复制亮色值）。
2. **删除主题切换**：删除 HTML 里 `<button ... id="theme-btn">亮色</button>`；
   删除 JS 里 `applyTheme`/`initTheme` 及其调用。
3. **数据字段适配**（全部在 JS 内）：
   - `data.enemies` → `data.visible_enemies`
   - `data.trajectories` → `mem().trajectories`
   - `mem().roles` → `data.tactic.worker_modes`；`roleOf(uid)` 返回
     `data.tactic.worker_modes[uid] || "—"`
   - `mem().threats` → 由 `mem().enemy_sightings` + `mem().threat_ghosts` 组装，
     新增函数：

```javascript
function threats() {
  const out = {};
  for (const s of (mem().enemy_sightings || [])) {
    out[s.id] = { enemy_id: s.id, kind: s.kind, unit_type: s.unit_type,
      positions: [s.position], stationary: !!s.stationary,
      last_seen_tick: s.last_seen_tick, hp: null };
  }
  for (const g of (mem().threat_ghosts || [])) {
    out[g.id] = { enemy_id: g.id, kind: "UNIT", unit_type: g.unit_type,
      positions: [g.position], stationary: false,
      last_seen_tick: data.tick, hp: null, expires_tick: g.expires_tick };
  }
  return out;
}
```

   - 把页面中所有 `mem().threats` 引用替换为 `threats()`；`renderHud` 的
     “威胁”数量用 `Object.keys(threats()).length`。
   - `mem().unreachable`：删除 `layout()` 和 `drawMap()` 里的
     `m.unreachable` 循环。
   - `renderPlan()`：`unit_actions` 值现在是对象
     `{type, direction}`，替换为：

```javascript
    Object.entries(pa).map(([uid, a]) => {
      const u = units.get(uid);
      const verb = ((a && a.type) || "WAIT").toLowerCase();
      const target = (a && (a.direction || a.position)) || "";
      return `<div class="plan-item">
        <span class="tag ${u ? "friend" : "neutral"}">${u ? u.unit_type : "?"}</span>
        <span class="mono">${uid.slice(0, 6)}</span>
        <span class="verb ${verb}">${(a && a.type) || "WAIT"}</span>
        <span class="right"><span class="target mono">${target}</span>${etaFor(u, a)}</span>
      </div>`;
    }).join("");
```

   - `renderPlan()` 的 core_action 部分替换为
     `data.plan.core_action.type` / `data.plan.core_action.direction`。
   - `etaFor(u, a)` 重写：目标从 `data.tactic.worker_targets[uid]` 取，
     方向用下表换算：

```javascript
const DIR_DELTA = { UP: [0, -1], DOWN: [0, 1], LEFT: [-1, 0], RIGHT: [1, 0] };
function etaFor(u, action) {
  if (!action || action.type !== "MOVE") return '<span class="eta now">本帧</span>';
  let tgt = null;
  if (action.direction && DIR_DELTA[action.direction]) {
    const d = DIR_DELTA[action.direction];
    tgt = [u.position[0] + d[0], u.position[1] + d[1]];
  } else {
    tgt = (data.tactic.worker_targets || {})[u.id];
  }
  if (!tgt) return '<span class="eta">?帧</span>';
  const dist = Math.abs(u.position[0] - tgt[0]) + Math.abs(u.position[1] - tgt[1]);
  if (dist === 0) return '<span class="eta now">本帧</span>';
  const secs = dist * TICK_SECONDS;
  return `<span class="eta ${secs > 60 ? "slow" : ""}">≈${dist}帧 · ${secs}s</span>`;
}
```

   - `drawMap()` 里计划箭头的目标同样用上述方向换算（`a.type === "MOVE"` 且
     `a.direction` 时用 `DIR_DELTA` 计算目标点）。
   - `renderHistory()`：参考页渲染 `h.units/h.enemies/h.actions/h.core/h.ms`，
     我们的行是 `{tick, text}`，替换主体为
     `<span class="lmsg">${h.text}</span>`。
   - `renderEnemies()` 的“记忆”行改用 `threats()` 值（字段已对齐）。
4. **标题**：`<title>` 改为 `Arena Hero 数据面板`。
5. **清理**：删除对 `data.plan.unit_actions[uid][0]`/`[1]` 数组语法的所有残留引用。

- [ ] **Step 2: 语法自检**

Run: `python - <<'EOF'
from pathlib import Path
html = Path("dashboard/index.html").read_text(encoding="utf-8")
assert "data-theme" not in html, "deep-theme remnants"
assert "theme-btn" not in html, "theme toggle remnants"
assert "data.enemies" not in html, "old enemy key"
assert "data.trajectories" not in html, "old trajectory key"
assert "m.unreachable" not in html, "old unreachable key"
print("index.html adaptation checks passed")
EOF`
Expected: `index.html adaptation checks passed`

- [ ] **Step 3: 手动冒烟**

先生成一份示例快照并独立启动服务，浏览器人工确认亮色页面与地图渲染：

```bash
.venv/bin/python - <<'EOF'
import json, tempfile, subprocess, sys
from pathlib import Path
sample = {
  "schema_version": 1, "tick": 1, "resources": 10, "resource_capacity": 20,
  "resource_space": 10, "core": {"id": "c", "position": [0, 0], "hp": 5,
  "shield": 5, "state": "NORMAL"},
  "units": [{"id": "u1", "unit_type": "WORKER", "position": [1, 0], "hp": 2, "cargo": 1}],
  "visible_enemies": [], "visible_resources": [[2, 0]], "known_obstacles": [],
  "plan": {"unit_actions": {"u1": {"type": "MOVE", "direction": "RIGHT"}},
           "core_action": {"type": "NONE"}},
  "tactic": {"strategy_phase": "EXPANSION", "worker_target": 12,
             "global_posture": "NORMAL", "threat_level": "NORMAL",
             "worker_modes": {"u1": "HARVEST"}, "worker_targets": {"u1": [2, 0]}},
  "memory": {"explored": [[0, 0], [1, 0], [2, 0]], "obstacles": [],
             "resources": {}, "trajectories": {"u1": [[0, 0], [1, 0]]},
             "enemy_sightings": [], "threat_ghosts": []},
  "tick_log": [], "event_log": [], "history": [],
}
path = Path(tempfile.gettempdir()) / "arena-hero-sample-snapshot.json"
path.write_text(json.dumps(sample), encoding="utf-8")
print(path)
EOF
ARENA_HERO_SNAPSHOT_FILE=/tmp/arena-hero-sample-snapshot.json python dashboard/server.py 8765
```

浏览器打开 `http://127.0.0.1:8765` 确认：亮色背景、HUD 显示、地图有格子与单位、
单位表有行、无 JS 报错。

- [ ] **Step 4: 提交**

```bash
git add dashboard/index.html
git commit -m "feat: add light dashboard page"
```

---

### Task 6: 部署与文档

**Files:**
- Modify: `Dockerfile`
- Modify: `compose.yaml`
- Modify: `README.md`、`docs/configuration.md`

- [ ] **Step 1: 改 Dockerfile**

在现有 `COPY arena_farmer.py ... ./` 行后追加：

```dockerfile
COPY dashboard ./dashboard
```

- [ ] **Step 2: 改 compose.yaml**

agent 服务的 `command` 追加：

```yaml
      - --snapshot-file
      - /tmp/arena-hero-snapshot.json
```

并在服务下追加端口映射（只绑宿主机回环）：

```yaml
    ports:
      - "127.0.0.1:8765:8765"
```

- [ ] **Step 3: 改文档**

`README.md` 的 Linux/macOS 快速开始后追加小节：

```markdown
### 数据面板

Agent 启动时默认在 `127.0.0.1:8765` 提供亮色数据面板（每 Tick 导出
`snapshot.json`，页面可看实时地图、HUD、单位/敌方/资源、指令队列、事件流与
网络探测）。远程查看请用 SSH 转发：`ssh -L 8765:127.0.0.1:8765 user@host`，
然后打开 <http://127.0.0.1:8765>。关闭面板：`--no-dashboard`。
```

`docs/configuration.md` 的 CLI 表格追加三行：

| `--snapshot-file` | `./snapshot.json` | Atomically write dashboard snapshot JSON per accepted Turn. |
| `--dashboard-port` | `8765` | Embedded dashboard port. |
| `--dashboard-host` | `127.0.0.1` | Embedded dashboard bind address. |
| `--no-dashboard` | off | Disable the embedded dashboard server. |

- [ ] **Step 4: 校验**

Run: `python -m unittest discover -v`
Expected: 全部 PASS

Run: `python scripts/sync-main.py`
Expected: `source-sync status=up-to-date ...`

Run（本机有 docker 时）：`docker compose config`
Expected: 解析成功且 agent command 包含 `--snapshot-file`

- [ ] **Step 5: 提交**

```bash
git add Dockerfile compose.yaml README.md docs/configuration.md
git commit -m "feat: wire dashboard into Docker deployment and docs"
```

---

### Task 7: 全量验收

**Files:** 无新增

- [ ] **Step 1: 全量测试**

Run: `python -m unittest discover -v`
Expected: 全部 PASS

- [ ] **Step 2: 同步校验**

Run: `python scripts/sync-main.py`
Expected: `up-to-date`（若 fetch 需要网络/权限，按环境提示处理）

- [ ] **Step 3: 提交剩余改动并推送**

```bash
git status --short
git push fork main
```

Expected: push 到 `https://github.com/15210551184/arena-hero-agent.git` 成功

- [ ] **Step 4: 服务器部署提示（写给用户，不自动执行）**

在服务器 `/data/ai/arena-hero-agent`：

```bash
git pull
docker compose up -d --build
docker compose logs -f agent
```

访问面板：SSH 转发 `ssh -L 8765:127.0.0.1:8765 root@服务器IP` 后浏览器打开
`http://127.0.0.1:8765`。

---

## Self-Review

- **Spec 覆盖**：架构（Task 1/3/4/5）、快照契约（Task 1）、探索记忆（Task 1）、
  服务 API（Task 4）、亮色页面（Task 5）、错误处理（Task 1/3/4 的 try/except）、
  测试（各 Task）、Docker 部署（Task 6/7）均已覆盖。
- **占位符检查**：无 TBD/TODO；所有代码步骤含具体实现。
- **类型一致性**：`DashboardMemory.update/view`、`build_snapshot`、
  `start_dashboard_thread(port, host, snapshot_path, status_provider, api_key)`
  在 Task 1/3/4 间签名一致；`play()` 参数与 `main()` 传参一致。

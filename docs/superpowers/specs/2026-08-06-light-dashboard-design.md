# 亮色数据面板（Light Dashboard）设计

- 日期：2026-08-06
- 状态：已确认（等待实现计划）
- 仓库：arena-hero-agent（fork：15210551184/arena-hero-agent）

## 目标

为无人值守 agent 增加一个内嵌的亮色数据面板：浏览器打开页面即可实时查看
Tick、资源、兵力构成、Core 状态、地图探索、指令队列、单位/敌方/资源列表、
事件流与网络探测。参考实现为本地 `arena-hero-balanced/dashboard/`（深色/亮色
可切换的战术监控页），本设计只保留亮色主题，数据源改为本 agent 的 Turn 状态
与内部记忆。

## 决策摘要

- 范围：完整复刻参考页（地图 + HUD + 各列表 + 指令队列 + 事件流 + 探测）。
- 运行方式：内嵌模式——面板作为后台线程跑在 agent 进程内（默认开启，
  `--no-dashboard` 可关闭）；另保留独立模式 `python dashboard/server.py`
  读取同一份快照文件。
- 数据流：agent 每个 Tick 原子写一份 `snapshot.json`（路径可配），
  内嵌服务对文件做长轮询，与参考实现同构。
- 主题：仅亮色。
- 地图：累积探索地图——快照携带 agent 的探索记忆（已知障碍、资源记忆、
  单位轨迹、威胁幽灵、敌人目击）。
- 访问：默认绑定 `127.0.0.1:8765`；远程访问走 SSH 转发或 1Panel/nginx 反代，
  不直接暴露公网。
- 部署：现有 Docker Compose 流程不变，compose 内 agent 命令追加
  `--snapshot-file /tmp/arena-hero-snapshot.json`，可选发布
  `127.0.0.1:8765:8765` 端口。

## 架构与组件

新增 `dashboard/` 包：

- `dashboard/server.py`
  - `ThreadingHTTPServer`，路由：
    - `/`、`/index.html` → 页面
    - `/api/data?since_mtime=` → 长轮询快照文件 mtime 变化
    - `/api/state` → agent 内部状态
    - `/api/probe` → 网络与数据新鲜度探测
  - `start_dashboard_thread(port, host, status_provider)`：内嵌后台线程入口，
    daemon 线程，端口占用时打印警告并返回 `None`，不阻止 agent 运行。
  - `main()`：独立模式，`python dashboard/server.py [port]`。
- `dashboard/index.html`：亮色主题单文件页面（由参考页改编，删除深色主题）。
- `dashboard/__init__.py`：空包标记。

`arena_farmer.py` 改动：

- 新增快照构建与写入函数（纯函数便于测试）：
  - `build_snapshot(turn, tactic, memory_view, tick_log, event_log, history) -> dict`
  - `write_snapshot(path, data)`：临时文件 + `os.replace` 原子替换
- `play()` 的 Tick 循环：提交成功后构建快照并写入
  `--snapshot-file`（默认 `Path.cwd() / "snapshot.json"`），同时刷新
  内嵌面板的状态提供者（最近活动时间）。
- CLI 新增参数：
  - `--dashboard-port`（默认 8765）
  - `--dashboard-host`（默认 127.0.0.1）
  - `--no-dashboard`（默认开启面板）
  - `--snapshot-file`（默认 `./snapshot.json`）

## 快照数据契约

每 Tick 一份 JSON，顶层字段：

```json
{
  "schema_version": 1,
  "generated_at": "ISO8601 Z",
  "tick": 123,
  "resources": 100,
  "resource_capacity": 120,
  "resource_space": 20,
  "core": {"id": "...", "position": [x, y], "hp": 100, "shield": 50,
           "state": "NORMAL", "move_direction": null,
           "move_progress": null, "destination": null},
  "units": [{"id": "...", "unit_type": "WORKER", "position": [x, y],
             "hp": 20, "cargo": 5}],
  "visible_enemies": [{"id": "...", "kind": "UNIT", "unit_type": "RANGER",
                       "position": [x, y], "hp": 10, "shield": 0,
                       "owner_username": "..."}],
  "visible_resources": [[x, y]],
  "known_obstacles": [[x, y]],
  "plan": {"unit_actions": {"uid": {"type": "MOVE", "direction": "N"}},
           "core_action": {"type": "NONE"}},
  "tactic": {"strategy_phase": "EXPANSION", "worker_target": 12,
             "beacon_policy": "retreat", "global_posture": "NORMAL",
             "threat_level": "NORMAL", "threat_reason": "NONE",
             "recovery": false, "combat_pressure": false,
             "worker_modes": {"uid": "HARVEST"},
             "worker_targets": {"uid": [x, y]}},
  "memory": {"obstacles": [[x, y]],
             "resources": [[x, y, last_seen_tick]],
             "trajectories": {"uid": [[x, y]]},
             "threat_ghosts": [{"id": "...", "position": [x, y],
                                "unit_type": "RANGER", "expires_tick": 200}],
             "enemy_sightings": [{"id": "...", "position": [x, y],
                                  "unit_type": "RANGER", "kind": "UNIT",
                                  "last_seen_tick": 199}]},
  "tick_log": [{"tick": 199, "unit": "...", "position": [x, y],
                "next": [x, y], "action": "HARVEST", "hp": 20,
                "cargo": 5, "role": "HARVEST"}],
  "event_log": [{"tick": 199, "event": "UNIT_HARVEST_SUCCEEDED",
                 "reason": null, "amount": 5}],
  "history": [{"tick": 190, "text": "phase=EXPANSION"}]
}
```

字段映射：

- `core`：`turn.core.view`（HP/盾/状态/移动字段）。
- `units`：`turn.units` 的 `view` 字段 + `tactic.worker_modes` /
  `tactic.worker_targets` 作为角色与目标。
- `visible_enemies`：`turn.visible_enemies`。
- `visible_resources`：`turn.resource_cells`；`known_obstacles`：
  `tactic.known_obstacles`。
- `plan`：`turn.plan.model_dump(mode="json", exclude_none=True)`。
- `tactic`：`tactic.strategy_phase(turn)`、`threat_assessment`
  （`global_posture` / `level` / `primary_reason` / `combat_pressure`）、
  `recovery_mode`、配置目标。
- `memory`：`tactic` 的探索与威胁记忆（见下节）。
- `tick_log`：参考页日志抽屉所需行（单位 id、当前位置、下一步、动作、
  HP、货舱、职责）。
- `event_log`：`turn.events` 的 `event_type` / `reason_code` / 关键数值。
- `history`：阶段变化、威胁等级变化、恢复/兼容性保持等系统动态。

## 累积探索记忆

快照中的 `memory` 由 agent 内部记忆导出，页面端不额外累积。agent 在
`play()` 作用域内维护一个快照记忆对象（`DashboardMemory`），每个 Tick 更新：

- `known_obstacles`：`tactic.known_obstacles` 全集。
- `resources`：`tactic.resource_last_seen`（位置 → 最后可见 Tick）。
- `trajectories`：`DashboardMemory` 维护每单位最近位置
  `deque(maxlen=40)`，每 Tick 追加一次，防止无限增长。
- `threat_ghosts`：`tactic.recent_attack_threats` / 敌人目击记忆导出，
  带 `expires_tick`。
- `enemy_sightings`：`tactic.enemy_unit_sightings` /
  `tactic.enemy_core_sightings` 的最新值。
- 列表类记忆统一设置上限（`tick_log` / `event_log` / `history` /
  `enemy_sightings` 默认各 200 条），超出丢最旧，避免长期运行膨胀。

## 服务与 API 行为

- `/api/data?since_mtime=`：0.2 秒步进轮询快照文件，最多等 25 秒；
  文件更新后立即返回 `{...快照, "_mtime": mtime}`；文件不存在返回
  `{"error": "no data yet"}`。响应带 `Cache-Control: no-store`。
- `/api/probe`：DNS 解析、TCP+TLS 握手、HTTP 状态、未鉴权 WS 握手、
  带鉴权 WS 收消息（复用已加载的 API key，绝不输出 key 本身）、快照新鲜度
  （`age_seconds` / `fresh`）、bot 最近活动秒数；按参考页判定逻辑输出
  `verdict`。
- 浏览器断连（`BrokenPipeError` / `ConnectionResetError`）静默忽略。
- 端口占用：面板启动失败只打印警告，agent 继续运行。

## 页面（亮色主题）

单文件 `index.html`，无构建步骤，由内嵌服务直接吐出：

- 顶部 HUD：TICK、资源/容量、人口、W/V/R、威胁等级/态势、状态点
  （在线/离线/数据过期）、上次更新时间；右上角“手动探测”按钮。
- 主区左：Canvas 累积探索地图（障碍、资源、敌人、威胁幽灵、单位轨迹、
  当前视野内对象；支持“适应视图”）。
- 主区右：Core 面板（HP/盾分段条、状态、位置、移动信息）、本帧指令队列、
  单位表、敌方与威胁表、资源表。
- 底部：系统动态 / 事件流 + 日志抽屉（每帧单位动作明细表）。
- 仅亮色主题；删除参考页的深色主题与切换按钮。

## 错误处理

- 快照写入失败：记录警告并继续 Tick 循环（面板显示最后一份成功快照）。
- 面板线程内部异常：daemon 线程，异常仅记录，不终止 agent。
- 探测失败：单项返回 `ok: false` 与错误信息，不影响整体。
- 数据过期判定：页面按快照 `age_seconds` 展示“数据过期”状态，
  与现有 heartbeat 的健康检查语义一致。

## 测试（unittest，沿用仓库现有风格）

- 快照构建：构造 Turn/战术状态 fixture，校验顶层字段与数值；
  校验原子写入（临时文件清理、异常时不损坏旧快照）。
- 记忆累积：轨迹 `deque` 上限、资源记忆更新、列表裁剪。
- server Handler：`/api/data` 长轮询更新/超时、无数据响应、404、
  `/api/probe` JSON 结构（mock DNS/TLS/HTTP/WS）。
- CLI：`--no-dashboard`、`--dashboard-port`、`--snapshot-file` 解析。
- 新增 `test_dashboard.py`；`arena_farmer.py` 相关改动补进现有测试文件。

## 部署（Docker Compose）

现有流程不变（`mkdir -p secrets` → 复制密钥模板 → 替换占位值 →
`docker compose up -d --build`）。`compose.yaml` 的 agent 服务改动：

- `command` 追加 `--snapshot-file /tmp/arena-hero-snapshot.json`
  （容器根文件系统只读，快照写入 tmpfs `/tmp`）。
- 可选：`ports: ["127.0.0.1:8765:8765"]`——仅在需要从宿主机/反代访问面板时
  添加，不暴露公网。
- 其余（密钥 secret 挂载、健康检查、`restart: unless-stopped`、
  150 秒超时）保持不变。
- systemd 部署无需改动（内嵌模式）。

## 安全

- 快照只含游戏数据（单位/位置/HP 等），绝不包含 API key 或 .env 内容。
- 面板默认绑定回环地址；公网访问必须经反向代理或转发。
- `load_api_key` / probe 的密钥只存在于 agent 进程内，不写日志。

## 范围外（YAGNI）

- 深色主题。
- 面板鉴权（当前按回环绑定 + 反代处理）。
- Docker 独立面板容器（当前内嵌；独立模式已预留）。
- 地图拖拽/缩放交互（当前仅“适应视图”）。

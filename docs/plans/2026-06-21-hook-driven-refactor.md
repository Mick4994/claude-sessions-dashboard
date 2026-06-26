# 重构方案：Hook 驱动状态机 + 进程驱动列表

> 日期：2026-06-21 | 审计状态：待用户确认

## 0. 核心决策

| 决策 | 结论 |
|------|------|
| JSONL 扫描保留干什么 | 仅 metadata：标题、context%、subtitle。**不做状态推断** |
| 状态机 | 7 条纯 hook 规则，无 JSONL 推断 |
| 列表增删 | 仅靠 ProcessPoller 轮询 psutil |
| 指示灯颜色 | 仅靠 HookServer 收 hook POST |
| JSONL fallback | **不做**（用户明确拒绝） |
| 自动写 settings.json | **不做**（用户手动配 hook） |
| 端口 | `localhost:18721`（15721 被 CC Switch 占） |

## 1. 架构

```
┌───────────────────────────────────────────────────────────┐
│                    Dashboard 进程                          │
│                                                           │
│  ProcessPoller (QTimer 2s)          HookServer (aiohttp)  │
│       │ psutil                            ▲ HTTP POST     │
│       ▼                                   │               │
│  SessionRegistry ◄────────────────────────┘               │
│       │                                                   │
│       ├── added/removed ──> SessionListWidget             │
│       └── status_changed ─> IndicatorWidget               │
│                                                           │
│  JSONL Reader (后台线程, 仅 metadata)                     │
│       └── title / context% / subtitle ──> SessionRow      │
└───────────────────────────────────────────────────────────┘
         ▲                                   ▲
         │ psutil                            │ curl POST (CC hook command)
         │                                   │
   ┌─────┴─────┐                       ┌─────┴─────┐
   │ CC 进程   │                       │ CC hook    │
   │ (PID,CWD) │                       │ 触发时执行  │
   └───────────┘                       └───────────┘
```

**职责边界（硬约束）**：
- ProcessPoller **不读** JSONL、**不收** hook
- HookServer **不读** JSONL、**不扫** 进程
- JSONL Reader **不改** status、**不管** 进程

## 2. Hook 事件与状态规则（纯 hook，7 条）

| # | 收到 hook | 新状态 |
|---|-----------|--------|
| 1 | `UserPromptSubmit` | WORKING 🟡 |
| 2 | `Stop`（含 ESC 中断） | IDLE 🟢 |
| 3 | `StopFailure` | IDLE 🟢 |
| 4 | `PermissionRequest` | PERMISSION 🔴 |
| 5 | `PostToolUse` | WORKING 🟡 |
| 6 | `PostToolUseFailure` | WORKING 🟡 |
| 7 | `PermissionDenied` | WORKING 🟡 |

**第 4 态已删除**：之前 UNKNOWN（灰）表示"进程发现但未收到任何 hook"。现已简化为：进程发现后**默认 IDLE（绿）**——直到首个 hook 改变状态为止。不再有灰色。

**PERMISSION 不死锁机制**：60s 超时无新 hook → 自动回退 WORKING。

**ESC 中断**：用户 ESC 取消 CC 已在 `Stop` hook 覆盖范围内（CC 中断后触发 Stop）。

## 3. CC 端配置（用户手动写入 settings.local.json）

```json
{
  "hooks": {
    "UserPromptSubmit":  [{ "hooks": [{ "type": "command", "command": "curl -s -X POST 'http://127.0.0.1:18721/hook/UserPromptSubmit?sid=$CLAUDE_SESSION_ID' -d @- &" }]}],
    "Stop":              [{ "hooks": [{ "type": "command", "command": "curl -s -X POST 'http://127.0.0.1:18721/hook/Stop?sid=$CLAUDE_SESSION_ID' -d @- &" }]}],
    "StopFailure":       [{ "hooks": [{ "type": "command", "command": "curl -s -X POST 'http://127.0.0.1:18721/hook/StopFailure?sid=$CLAUDE_SESSION_ID' -d @- &" }]}],
    "PermissionRequest": [{ "hooks": [{ "type": "command", "command": "curl -s -X POST 'http://127.0.0.1:18721/hook/PermissionRequest?sid=$CLAUDE_SESSION_ID' -d @- &" }]}],
    "PostToolUse":       [{ "hooks": [{ "type": "command", "command": "curl -s -X POST 'http://127.0.0.1:18721/hook/PostToolUse?sid=$CLAUDE_SESSION_ID' -d @- &" }]}],
    "PostToolUseFailure":[{ "hooks": [{ "type": "command", "command": "curl -s -X POST 'http://127.0.0.1:18721/hook/PostToolUseFailure?sid=$CLAUDE_SESSION_ID' -d @- &" }]}],
    "PermissionDenied":  [{ "hooks": [{ "type": "command", "command": "curl -s -X POST 'http://127.0.0.1:18721/hook/PermissionDenied?sid=$CLAUDE_SESSION_ID' -d @- &" }]}]
  }
}
```

- 端口 `localhost:18721`
- `&` 后台执行避免阻塞 CC
- `-d @-` 透传 stdin hook payload
- `$CLAUDE_SESSION_ID` 由 CC 环境变量注入

## 4. 删除清单

### 删除函数/逻辑

| 位置 | 删除 |
|------|------|
| `src/collector/session_parser.py::_determine_status` | 整个函数 |
| `src/collector/collector.py` mtime 过滤逻辑 | `is_current`/`in_grace`/`recency_cutoff` |
| `src/collector/collector.py` STALE→IDLE 转换 | 采集器不再管状态 |
| `src/collector/collector.py` grace period 逻辑 | 进程不在即移除 |
| `src/collector/session_parser.py::STATUS_PRIORITY` | 无用的常量 |

### 删除测试

| 文件 | 删除 |
|------|------|
| `tests/test_session_parser.py` | `test_status_*` 全系列 (~12 个) |
| `tests/test_collector.py` | `test_collector_filters_stale_by_mtime` 等 mtime 相关 (3-4 个) |
| `tests/fixtures/` | 状态相关的 mock JSONL |

## 5. 新增清单

### 新文件

| 文件 | 职责 |
|------|------|
| `src/core/status.py` | `Status` 枚举 (IDLE/WORKING/PERMISSION) + 颜色常量 |
| `src/core/session_registry.py` | 单例注册表，PID↔Session 映射，回调驱动 |
| `src/server/hook_server.py` | aiohttp HTTP server，7 个 POST 端点 |
| `src/server/router.py` | URL→registry 路由层 |

### 改文件

| 文件 | 改动 |
|------|------|
| `src/collector/collector.py` | 砍掉 mtime 过滤和状态逻辑，只做进程→session 映射 |
| `src/collector/session_parser.py` | 删 `_determine_status`，保留 title/pct/subtitle |
| `src/ui/indicator_widget.py` | 颜色映射改为 4 态 |
| `src/ui/session_list_widget.py` | 订阅 registry 信号，不直接调 collector |

## 6. 实施阶段

### Phase 1：核心数据层
- 新增 `src/core/status.py`
- 新增 `src/core/session_registry.py`
- 不改旧代码，纯新增

### Phase 2：Hook Server
- 新增 `src/server/hook_server.py`
- 新增 `src/server/router.py`
- 新增 `src/config.py`
- 独立可跑，不依赖 UI

### Phase 3：UI 解耦 + 删除旧状态机
- 删 `_determine_status`
- 删 mtime 过滤
- UI 改为订阅 registry
- 最大重构阶段

### Phase 4：文档
- 更新 README、architecture.md
- 新增 hook-setup.md

## 7. 关键文件路径

项目根：`D:\Codes\claude-sessions-dashboard\`

| 类别 | 路径 |
|------|------|
| 重构方案（本文件） | `D:\Codes\claude-sessions-dashboard\docs\plans\2026-06-21-hook-driven-refactor.md` |
| 测试方案 | `D:\Codes\claude-sessions-dashboard\docs\plans\2026-06-21-test-plan.md` |

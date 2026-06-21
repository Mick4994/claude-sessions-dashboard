# Claude Sessions Dashboard — 需求规格说明书

> 一个常驻桌面的悬浮状态栏，用指示灯可视化所有活跃 Claude Code 会话状态。

---

## 一、目标与范围

### 1.1 目标
在 Windows 桌面上提供一个**始终置顶**的悬浮窗，实时可视化本机所有正在活动的 Claude Code 会话，使用户无需逐个窗口查看即可掌握：
- 哪些会话正在思考/调工具
- 哪些会话在等用户输入
- 每个会话距离 context 窗口上限还有多远
- 每个会话**当前正在执行的任务**是什么（新增）

### 1.2 范围

**包含**：
- Python 桌面 GUI 程序（PySide6）
- 本机会话数据采集与状态判定
- 悬浮窗口 + 右侧贴边 + 悬停展开/离开收起
- 系统托盘常驻 + 开机自启动
- 右键菜单（退出 / 暂停轮询 / 重载配置）
- 点击卡片激活对应 CC 终端窗口

**不包含**（v1）：
- 跨机器会话监控
- context 内容预览
- 直接介入会话（暂停/继续/发送消息）
- 暗色/亮色切换（v1 固定深色）

---

## 二、用户场景

```
[用户场景 1] 我开了 3 个 CC 会话在跑（一个调工具、一个等待权限、一个空闲），
我盯着 VSCode 写代码 → 余光扫到右侧灯条里：
  - 第 1 个灯闪蓝光（工作中）✓ 不需要切过去看
  - 第 2 个灯亮黄（等权限）✓ 鼠标移过去展开，看清是哪个项目，点了切过去授权
  - 第 3 个灯亮绿（空闲）✓ 知道它没在跑，安心
  鼠标 hover 展开后，每张卡片显示：
    - 标题（项目名/任务名）
    - 副标题（当前正在调的工具，比如 Edit: claude_dashboard.py）
    - context% + 进度条
    - cwd 路径

[用户场景 2] 某个会话跑太久 context% 飘到 87% → 我看到灯条颜色/进度条变化
→ 鼠标移过去展开 → 看到具体百分比 + 副标题（确认在跑啥） → 决定去那个窗口 /compact
```

---

## 三、数据源与采集层

### 3.1 数据源

| 数据 | 来源 | 频率 |
|------|------|------|
| 会话列表 / mtime | `~/.claude/projects/**/<sessionId>.jsonl` 文件元数据 | 每 2s |
| 活跃判定（精） | 同上文件**最后一行**的 `timestamp` 字段 | 每 2s（候选文件） |
| 会话标题 | JSONL 内 `type=ai-title` 的 `aiTitle` 或首条 user 消息内容 | 首次解析后缓存 |
| **副标题（当前任务）** | JSONL 内最后一条 assistant turn 的首个 `tool_use.name` + `input` 摘要 | 每 2s |
| context 占用 | JSONL 内**最后一条 `type=assistant`** 的 `message.usage` | 每 2s |
| 模型 | 最后一条 `assistant` 的 `message.model` | 每 2s |

### 3.2 活跃判定（进程探活）
一个会话被显示在灯条上当且仅当**对应的 Claude Code 进程在跑**：
- **信号**：`psutil.process_iter()` 枚举所有 `node.exe` 进程，匹配命令行含 `claude-code`、`@anthropic-ai/claude-code`、`claude` 的进程
- **CWD 匹配**：进程工作目录 → JSONL session 的 `cwd` 字段 → 匹配成功
- **缓冲期**：最近 5 分钟内有活动的 session，即使 CC 进程已退出（刚关闭 CC），也会继续显示 5 分钟
- **清除**：CC 进程不在跑 + 5 分钟缓冲期已过 → 移除出灯条

> v1 实现用 `psutil` 库；如果没有 psutil（例如 exe 打包），回退到文件 mtime + timestamp 双信号。

### 3.3 context% 计算
公式：
```
tokens_now = usage.input_tokens + usage.cache_creation_input_tokens + usage.cache_read_input_tokens
context_pct = round(tokens_now / max_context_tokens * 100)
```
- `max_context_tokens` 在配置文件中可改（`config.ini`），默认 **1000000**（MiniMax-M3 模型是 1M context）
- 取**最后一条 assistant turn** 的 usage（避免重复计数历史轮次）

### 3.4 会话标题
优先级：
1. JSONL 中 `type=ai-title` 的 `aiTitle` 字段（CC 自动生成的标题，最稳定）
2. 首条 `type=user` 消息内容截断到 32 字符
3. cwd 路径的 basename（如 `claude-status-dashboard`）

### 3.5 副标题（当前任务）—— v1 新增

#### 主规则：取最后一条 assistant turn 的首个 `tool_use` 块

| 工具 | 副标题格式 | 示例 |
|------|-----------|------|
| `Read` / `Write` / `Edit` / `MultiEdit` / `NotebookEdit` | `<Tool>: <file_path basename>` | `Edit: claude_dashboard.py` |
| `Bash` | `Bash: <command 前30字符>` | `Bash: pip install pyside6` |
| `Grep` | `Grep: <pattern>` | `Grep: TODO` |
| `Glob` | `Glob: <pattern>` | `Glob: **/*.py` |
| `Agent` (Task) | `Agent: <subagent_type>: <description 前20字>` | `Agent: explore: Finding auth` |
| `WebFetch` | `WebFetch: <url hostname>` | `WebFetch: github.com` |
| `WebSearch` | `WebSearch: <query 前20字>` | `WebSearch: pyside6 tray` |
| `TodoWrite` | `TodoWrite: 任务列表更新` | `TodoWrite: 任务列表更新` |
| `AskUserQuestion` | `AskUserQuestion: 询问用户` | `AskUserQuestion: 询问用户` |
| `EnterPlanMode` | `Plan: 进入计划模式` | `Plan: 进入计划模式` |
| 其它 | 直接用工具名（无 input 摘要） | `mcp__xxx__tool` |

#### Fallback 链
无 tool_use 时按顺序匹配：
1. 末尾是 assistant `stop_reason=end_turn` 且 content 含 `text` → 截取 text 前 40 字
2. 末尾是 user `tool_result` → 显示 `(完成) <tool_name>`（按 result 的 `tool_use_id` 反查对应 tool_use）
3. 末尾是 user text prompt → 截取前 40 字
4. 都没匹配：
   - working 状态 → `Thinking...`
   - idle 状态 → `Idle`
   - error 状态 → `Last: <上一个副标题>` 或 `Error`

#### 长度与省略
- 单行省略号（`...`），最长字符数 = `subtitle_truncate_chars`（默认 40，可配置）
- 中文字符按 1 字符计数

---

## 四、状态机与可视化

### 4.1 状态机（3 状态，简化版）

| 状态 | 颜色 | 动效 | 触发条件 |
|------|------|------|---------|
| **Working（工作中）** | 黄色 `#EAB308` | **闪烁**（1Hz） | CC 进程在跑 + 最后一条 entry 是 assistant 且 `stop_reason ≠ end_turn` |
| **Permission（请求授权）** | 红色 `#EF4444` | 常亮 | CC 进程在跑 + assistant 有 `tool_use` 但无对应 `tool_result` |
| **Idle（闲置）** | 绿色 `#22C55E` | 常亮 | CC 进程在跑 + 最后一条是 user 或 assistant `end_turn` |

> 如果 CC 进程不在跑（且超过 5 分钟缓冲期），直接不显示指示灯——不需要灰色"Stale"状态。

### 4.2 闪烁实现
- QTimer 1s 周期驱动 `QGraphicsColorEffect.opacity`，0.55→1.0→0.55
- Working 闪烁周期 1.0s
- 收起态也保持闪烁（即使半透明也能看清）

### 4.3 context% 颜色梯度（独立于状态色）
```
<  70%  绿色
70-85%  黄色
>  85%  红色
```
应用于展开卡片的进度条 + 百分比文字。

---

## 五、UI 规格

### 5.1 窗口骨架
- **无边框**（`Qt.FramelessWindowHint`）
- **始终置顶**（`Qt.WindowStaysOnTopHint`）
- **不抢任务栏**（`Qt.Tool`，Windows 下）
- **支持透明背景**（`Qt.WA_TranslucentBackground`）
- 起始尺寸：宽度 **40px**（收起）/ **280px**（展开），高度自适应
- 起始位置：屏幕**右侧**居中，距右边缘 0px

### 5.2 收起态
```
┌──┐
│ ●│  ← 指示灯 12×12px 圆点 + 内圈高光
│ ●│  ← 第二个会话
│ ◐│  ← 闪烁的（工作中）
│ ●│
│ ●│
└──┘
  ↑ 距屏幕右边 0px（贴边吸附），高度=会话数×22px + padding
```
- 背景色：`rgba(20, 20, 24, 0.80)`（半透明）
- 整体不透明度 0.8
- 每个指示灯 hover 上去显示 tooltip：会话标题 + context% + **副标题**

### 5.3 展开态（鼠标进入窗口触发）
```
┌────────────────────────────────────┐
│ ● claude-status-dashboard    87%  │  ← 标题 + context%
│   Edit: claude_dashboard.py        │  ← 新增副标题（次要灰，单行省略号）
│   ████████████░░░░░  87%           │  ← 进度条
│   ~/projects/claude-status-...     │  ← cwd（次要信息）
│────────────────────────────────────│  ← 分隔线
│ ● claude-mem 探索         12%     │
│   Bash: find . -name "*.py"       │
│   ██░░░░░░░░░░░░░░░░░░  12%       │
│   ~/projects/...                   │
└────────────────────────────────────┘
```
- 每张卡片高度约 70px（新增副标题占 ~14px）
- 展开/收起用 `QPropertyAnimation` 推动 `width` 在 200ms 内过渡

### 5.4 交互细节
| 操作 | 行为 |
|------|------|
| 鼠标进入窗口 | 200ms 内展开到 280px |
| 鼠标离开窗口 | 500ms 内收回 40px（带延迟避免闪烁） |
| 单击卡片/指示灯 | 激活对应 CC 终端窗口到前台（Win32 `SetForegroundWindow`） |
| 拖动窗口 | 可拖离贴边位置到任意处；释放时若在屏幕边缘 30px 内自动吸附回右边缘 |
| 双击标题栏区域 | 暂停/恢复轮询（托盘图标变灰提示） |
| 右键 | 弹出菜单：暂停轮询 / 重载配置 / 关于 / 退出 |

### 5.5 点击激活 CC 终端（关键交互）
- 需要从 JSONL 关联到终端进程
- 方案：**通过 `cwd` 字段**，遍历 `tasklist /FI "IMAGENAME eq cmd.exe / powershell.exe / WindowsTerminal.exe"`，找工作目录与 JSONL cwd 匹配的窗口 → `SetForegroundWindow`
- v1 实现：仅匹配 cwd 包含关系；找不到时退化为打开 Windows Terminal 在该 cwd

---

## 六、配置

### 6.1 配置文件 `config.ini`
位置：`%APPDATA%/ClaudeSessionsDashboard/config.ini`

```ini
[general]
poll_interval_ms = 2000
stale_after_minutes = 1440        # v2: 进程探活，此值用于回退
recent_seconds = 60               # 状态判定窗口：60s 内活动 = WORKING
hide_after_seconds = 86400        # v2: 回退场景下隐藏阈值 = 24h
expand_delay_ms = 200
collapse_delay_ms = 500
edge_snap_px = 30
indicator_size_px = 12
collapsed_opacity = 0.8
expanded_opacity = 1.0

[display]
context_max_tokens = 1000000   # MiniMax-M3 模型为 1M 上下文
warning_threshold = 0.70
critical_threshold = 0.85
title_truncate_chars = 32
subtitle_truncate_chars = 40     # 新增
max_visible_sessions = 20

[behavior]
auto_start = true                # 开机自启
start_minimized_to_tray = false  # 启动后是否直接收起到托盘
```

### 6.2 配置文件重载
- 托盘菜单"重载配置" 触发，无需重启
- 文件被外部修改时 1s 内自动检测重载（用 `QFileSystemWatcher`）

---

## 七、部署

### 7.1 运行形态
- **单 .py 启动**：`python claude_dashboard.py`（开发期）
- **打包 .exe**：PyInstaller `--onefile --windowed` → `ClaudeDashboard.exe`
- **系统托盘**：启动后窗口显示在屏幕右侧，托盘图标常驻
- **开机自启**：写入 Windows 任务计划程序 `ClaudeDashboard` 在用户登录时启动（不放在 Startup 文件夹因为容易被杀软扫描；任务计划程序更隐蔽）

### 7.2 退出
- 关闭主窗口 → 最小化到托盘（不退出）
- 托盘右键"退出" → 真正退出

---

## 八、项目结构

```
D:/Codes/claude-sessions-dashboard/      ← 本项目（Python/PySide6）
├── claude_dashboard.py        # 主入口
├── pyproject.toml             # uv 管理的依赖
├── config.ini                  # 默认配置（首次启动拷贝到 %APPDATA%）
├── README.md
├── REQUIREMENTS.md             # 本文档
├── docs/plans/                 # 实现计划
├── src/
│   ├── __init__.py
│   ├── collector/
│   │   ├── session_scanner.py  # 扫描 ~/.claude/projects
│   │   ├── session_parser.py   # 解析单个 JSONL
│   │   └── models.py           # Session dataclass
│   ├── ui/
│   │   ├── main_window.py      # QMainWindow 子类 + 贴边/展开/收起
│   │   ├── indicator_widget.py # 单个指示灯 + 卡片复合控件
│   │   └── tray.py             # QSystemTrayIcon
│   ├── win32/
│   │   ├── windows_focus.py    # 激活 CC 终端窗口
│   │   └── autostart.py        # 任务计划程序封装
│   └── utils/
│       ├── animation.py        # 闪烁动画
│       └── paths.py            # APPDATA / config 路径解析
├── tests/
│   ├── test_session_parser.py
│   ├── test_indicator_widget.py
│   └── fixtures/sample.jsonl
└── scripts/
    └── build_exe.py            # PyInstaller 打包脚本
```

> 注：原 JS/Electron 实现（"AI Status" by IDevUsefulStuff）保留在 `D:/Codes/claude-status-dashboard/` 不再参考。

---

## 九、非功能性需求

| 项 | 要求 |
|---|---|
| 内存占用 | < 100MB |
| CPU 占用（idle） | < 1%（Windows 任务管理器） |
| 启动到首个指示灯显示 | < 2 秒 |
| JSONL 解析延迟 | 单文件 < 50ms（用 tail 而非全量读） |
| Python 版本 | 3.12+ |
| 依赖 | PySide6、watchdog（可选，文件监视） |
| 测试覆盖 | 核心数据层 ≥ 80%（parser / scanner） |

---

## 十、验收标准

- [ ] 启动 3 个 CC 会话（其中 1 个跑长任务触发 working 闪烁），GUI 3 个指示灯同时显示
- [ ] 鼠标进入窗口 → 200ms 内展开显示卡片；离开 → 500ms 内收起
- [ ] 展开后每张卡片显示副标题（当前工具摘要），格式与表格一致
- [ ] 收起态 hover tooltip 也显示副标题
- [ ] 拖动到屏幕左/上/下边缘不吸附，拖到右边缘 30px 内吸附回右
- [ ] 单击卡片能把对应终端窗口带到前台
- [ ] context% 数字与 claude-hud statusLine 显示值误差 < 3%
- [ ] 关闭主窗口不退出进程，托盘图标仍在
- [ ] 重启电脑后自动启动（任务计划程序生效）
- [ ] 进程常驻，1 小时内 CPU < 1%、内存 < 100MB

---

## 十一、风险与开放项

| 风险 | 缓解 |
|------|------|
| JSONL 文件很大（10MB+），全量读会卡 | 只 tail 最后 N 行（如最后 200 行） |
| 点击激活 CC 终端依赖 cwd 匹配，可能误匹配 | v1 仅匹配 cwd 包含关系，失败时给用户 toast 提示 |
| 多显示器时贴边逻辑混乱 | v1 仅主显示器；多屏支持放 v2 |
| 用户自定义模型 max context 不同 | config 可配，默认 1M（MiniMax-M3） |
| 某些会话没有 `ai-title` | fallback 到首条 user 消息，再 fallback 到 cwd basename |
| tool_use 反查 tool_result 需要 UUID 关联 | JSONL 中 user.tool_result 块含 `tool_use_id`，通过 uuid 链反查 |

---

## 十二、变更记录

| 日期 | 变更 | 作者 |
|------|------|------|
| 2026-06-15 | 初版需求 | Claude |
| 2026-06-15 | 新增副标题（当前任务）字段 | Claude |
| 2026-06-15 | 项目目录改到 D:/Codes/claude-sessions-dashboard/；context_max_tokens 默认改为 1000000（MiniMax-M3 = 1M）；明确 uv 管理依赖 + git 版本控制 + 完整 exe + 任务计划程序自启闭环；JS/Electron 版保留在 D:/Codes/claude-status-dashboard/ 不再参考 | Claude |
| 2026-06-21 | **v2**: 活跃判定改为进程探活（psutil 检测 CC node.exe 进程 + CWD 匹配），不再依赖 JSONL 文件时间戳；状态机简化为 3 状态（黄闪=工作中 / 红=请求授权 / 绿=闲置）；新增 `hide_after_seconds` 配置字段用于回退 | Claude |
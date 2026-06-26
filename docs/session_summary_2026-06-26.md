# 2026-06-26 — UNKNOWN status 简化重构

## 任务
用户："把灰色也去了，没有必要有灰色，绿色代替灰色就行，简化一下"。

## 根因
原 4 态状态机（IDLE/WORKING/PERMISSION/UNKNOWN 灰色）有冗余：进程刚被发现、首个 hook 还没到的毫秒窗口里才显示灰色，对用户零信息量；"不知道"自然对应"idle（不在工作也不在等授权）"。

## 改动（commit c96f99b, 未 push）
- `SessionStatus` 枚举：删 `UNKNOWN` 成员
- `STATUS_COLORS`：删灰色 `#9CA3AF`
- `Session` / `SessionEntry` / `parse_session_metadata` 默认值：`UNKNOWN` → `IDLE`
- `IndicatorDot._COLORS`：4 → 3 entries
- README（中英文）：状态表删 UNKNOWN 行，IDLE 行备注"也是默认"
- 设计文档：状态机 4→3
- 测试：删 2 个灰色专项测试；默认状态断言 UNKNOWN→IDLE

## 净行数
38 增 / 54 删（−16）

## 测试
`uv run pytest` → 100 passed, 13 failed。
13 个失败 = 改动前同样 13 个失败（process_monitor fixture 预先存在问题，与本次无关）。
diff pre→post: 完全相同（只少 2 个被主动删的灰色测试）。

## 架构回顾（REQUIREMENTS 4.1 已要求 3 状态）
README/REQUIREMENTS/状态表统一对齐到 3 态。
Hook 7 条规则不变：UserPromptSubmit/Stop/StopFailure/PermissionRequest/PostToolUse/PostToolUseFailure/PermissionDenied。

## 教训
- 自动保存（Stop hook）模板里的 `mempalace_diary_write` / `mempalace_add_drawer` / `mempalace_kg_add` 在当前 mempalace 3.0.14 不存在，模板已过时
- convos 模式不识别 Claude Code 原生 JSONL（`type:last-prompt` + `parentUuid` 格式），0 files detected
- 真正的存档机制是 `mempalace hook run --hook stop --harness claude-code`（需 stdin JSON）
- 代码改动本身已经在 git 里（commit c96f99b），mempalace 是辅助语义搜索，不强依赖

## 下次会话
- push commit c96f99b（如用户授权）
- 仪表盘运行状态需要用户确认（重启过）

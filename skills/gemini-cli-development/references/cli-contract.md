# Gemini CLI 事实合同

## 本机核对

- 核对日期：2026-07-25
- 已发现版本：Gemini CLI `0.45.0`
- 事实来源：本机 `gemini --version` 与 `gemini --help`
- 已验证入口：无参数默认进入交互；`--prompt-interactive` 执行初始 prompt 后保持交互；`-p/--prompt` 是非交互 headless。
- 权限：`--approval-mode` 支持 `default`、`auto_edit`、`yolo`、`plan`；`--skip-trust` 跳过当前 workspace 信任确认。
- 会话：`--resume latest` 或索引恢复当前项目保存的会话，`--list-sessions` 可列出；正常返工应留在现有 TUI，不依赖恢复。

本任务只验证 help/版本与启动合同，没有调用模型、认证、工具写入或恢复会话，故未端到端验证。每次版本变化都重新查 help；不要臆造会话 ID、权限或续接参数。

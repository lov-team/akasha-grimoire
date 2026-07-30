# Gemini CLI 事实合同

## 本机核对

- 核对日期：2026-07-30
- 已发现版本：Gemini CLI `0.53.0`
- 事实来源：本机 `gemini --version` 与 `gemini --help`
- 已验证入口：无参数默认进入交互；`-i, --prompt-interactive` 执行初始 prompt 后保持交互模式；`-p, --prompt` 执行非交互 headless 模式。
- 权限与策略：`--approval-mode` 支持 `default`、`auto_edit`、`yolo`、`plan`（`-y, --yolo` 自动批准所有工具）；`--skip-trust` 跳过当前 workspace 信任确认；`--policy` 与 `--admin-policy` 加载策略文件（`--allowed-tools` 已标记为弃用并推荐 Policy Engine）。
- 会话管理与协议：支持 `--session-file` 从 JSON 加载会话、`--session-id` 手动指定 UUID，`--list-sessions` / `--delete-session` 列出与删除会话，`-r, --resume`（`latest` 或索引）恢复保存会话；支持 `--acp` 启动 ACP 模式（`--experimental-acp` 已弃用）。
- 输出选项：`-o, --output-format` 支持 `text`、`json`、`stream-json`；支持 `--raw-output` 与 `--accept-raw-output-risk`。

本次还用 `--skip-trust --approval-mode yolo --prompt-interactive` 完成了可见 Terminal + tmux 启动、模型响应和受限文件写入 smoke，随后主动停止会话；没有验证恢复、session-file、ACP、raw output 或完整开发交付。每次版本变化都重新查 help；不要臆造会话 ID、权限或续接参数。

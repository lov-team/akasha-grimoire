# Codex CLI 事实合同

## 本机核对

- 核对日期：2026-07-25
- 已发现版本：`codex-cli 0.144.0`
- 事实来源：本机 `codex --version` 与 `codex --help`
- 已验证入口：无子命令时进入交互 TUI；`codex exec` 是非交互模式；`--no-alt-screen` 保留终端 scrollback。
- 工作目录：`-C/--cd <DIR>` 设置工作根；仍用 runner 与 tmux 交叉验证物理路径。
- 权限：`--sandbox` 支持 `read-only`、`workspace-write`、`danger-full-access`；`--ask-for-approval` 支持 `untrusted`、`on-request`、`never`。
- 会话：`codex resume` 恢复保存的交互会话，默认选择器，`--last` 继续最近会话；正常返工留在现有 TUI。

本任务只验证 help/版本与启动合同，没有调用模型、认证、工具写入或恢复会话，故未端到端验证。不要把 Codex App task id 当作 CLI session id；版本变化时重新查 help。

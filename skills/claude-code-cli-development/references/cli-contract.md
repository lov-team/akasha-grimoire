# Claude Code CLI 事实合同

## 本机核对

- 核对日期：2026-08-09
- 已发现版本：Claude Code `2.1.226`
- 事实来源：本机 `claude --version` 与 `claude --help`
- 已验证入口：位置参数 prompt 启动交互；`-p/--print` 为非交互输出。
- 权限：`--permission-mode` 包含 `bypassPermissions`、`auto`、`acceptEdits`、`manual`、`dontAsk`、`plan`；另有 `--dangerously-skip-permissions` 与显式允许开关，使用前须遵守项目安全边界。
- 会话：`-c/--continue` 继续当前目录最近会话，`-r/--resume [value]` 按 ID 或选择器恢复；正常返工留在现有 TUI。
- 会话通讯：Claude Desktop 与 Claude Code CLI 会话已支持互发消息，可用于终态唤醒；状态/交付文件仍是唯一事实源。
- 工作目录：CLI 无 `--cwd`；虽然提供 `-w/--worktree` 与 `--tmux`，本技能仍由 runner 与 tmux `-c` 双重锁定既有 Issue worktree，并在启动前验证 `pwd -P`。

本任务只验证 help/版本与启动合同，没有调用模型、认证、工具写入或恢复会话，故未端到端验证。版本变化时重新查 help，不把其他 CLI 的参数套用到 Claude。

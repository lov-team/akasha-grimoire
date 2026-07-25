# Claude Code CLI 事实合同

## 本机核对

- 核对日期：2026-07-25
- 已发现版本：Claude Code `2.1.146`
- 事实来源：本机 `claude --version` 与 `claude --help`
- 已验证入口：位置参数 prompt 启动交互；`-p/--print` 为非交互输出。
- 权限：`--permission-mode` 包含 `bypassPermissions`；另有 `--dangerously-skip-permissions` 与显式允许开关，使用前须遵守项目安全边界。
- 会话：`-c/--continue` 继续当前目录最近会话，`-r/--resume [value]` 按 ID 或选择器恢复；正常返工留在现有 TUI。
- 工作目录：CLI 无 `--cwd`；必须由 runner 与 tmux `-c` 双重锁定，并在启动前验证 `pwd -P`。

本任务只验证 help/版本与启动合同，没有调用模型、认证、工具写入或恢复会话，故未端到端验证。版本变化时重新查 help，不把其他 CLI 的参数套用到 Claude。

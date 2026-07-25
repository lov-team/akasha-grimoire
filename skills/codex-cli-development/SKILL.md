---
name: codex-cli-development
description: 使用可见 macOS Terminal + tmux 驱动 Codex CLI 在同一交互 TUI 中先给中文计划并自检，再开发、写状态/交付文件并接受主 Agent 独立 Review 与返工。用户要求用 Codex CLI worker、让另一个 Codex 编码、计划后实现、持续监工或复用同一 Codex 会话返工时使用。
---

# Codex CLI 开发与独立验收

把 CLI 中的 Codex 当作实现 worker；当前主 Agent 仍负责需求解释、范围、用户决策、完整 diff Review、风险复测与 Git 结论。不要把 Codex App 任务管理和本 CLI 会话混为一谈。

## 读取规则并核对 CLI

1. 先读项目 `AGENTS.md`、原始需求、相关代码与 Git 现场；一个 worktree 同时只允许一个写入 worker。
2. 首次使用或版本变化时运行 `command -v codex`、`codex --version`、`codex --help`，再读 [references/cli-contract.md](references/cli-contract.md)。参数不匹配就停止更新合同。
3. 主 Agent 自行确定逐条验收、非目标、真实调用链和验证门禁。
4. 权限、凭证、安全、不可逆操作或范围歧义先交给用户决定。

## 建立 prompt contract

写明中文要求、唯一 worktree、目标、决策、非目标、允许/禁止路径、TDD/验证、Git 权限、状态与交付文件。要求 worker 先输出中文计划并自检，再在同一 TUI 原地实现；不派生写入者、不输出思考过程；阶段切换原子覆盖单行状态；最终写中文交付且末行为 `CODEX_DELIVERY_COMPLETE`。

状态仅允许 `CODEX_PLANNING`、`CODEX_IMPLEMENTING`、`CODEX_BLOCKED_USER_DECISION`、`CODEX_DELIVERY_COMPLETE`。交付包含文件、需求映射、Red/Green/Refactor 证据、测试、未验证项、风险和 Git 状态。

## 在可见 Terminal + tmux 启动

先说明将打开 Terminal，再调用 `scripts/launch-visible-cli.zsh <session> <runner> <worktree>`。runner 位于仓库外唯一临时路径且权限为 `700`；runner `cd`、tmux `new-session -c` 与 Codex `-C` 必须指向同一物理 worktree。

在 runner 中使用当前 help 已验证的交互入口：

```bash
cd "$TASK_WORKTREE"
test "$(pwd -P)" = "$(cd "$TASK_WORKTREE" && pwd -P)"
codex -C "$TASK_WORKTREE" \
  --sandbox danger-full-access \
  --ask-for-approval never \
  --no-alt-screen \
  "$PLAN_AND_IMPLEMENT_PROMPT"
```

该权限组合只适用于用户已批准、外部边界明确的任务；不扩大 worktree、Git、凭证或不可逆操作权限。高风险环境改用更窄 sandbox/approval，并让用户确认。不得用 `codex exec` 单轮非交互模式冒充持续 TUI，也不得在隐藏 PTY 启动。

## 低噪声长轮询与同会话返工

启动成功后运行：

```bash
scripts/wait-for-delivery.zsh \
  "$STATUS_FILE" CODEX_DELIVERY_COMPLETE \
  "$HANDOFF_FILE" CODEX_DELIVERY_COMPLETE \
  240
```

让脚本在进程内固定每 5 秒检查一次。默认等待 240 秒；任务明确较长时可提高，但不要用更短等待恢复高频轮询。循环中零输出，双重完成时才输出一行并退出 0，整段超时只输出一次最后状态并退出 124。若宿主先返回运行 session，使用一次支持的最长等待续接，不要由主 Agent 每 5 秒轮询。

退出 0 后只读一次交付文件再 Review。退出 124 时，implementing/missing 重新等待 240 秒或更长，blocked 才请求用户决策，异常状态才做一次最小诊断。不要抓 pane、过程输出、思考、token、进程或中间 diff。正常返工在现有 TUI 中只发送一行读取仓库外返工合同的指令，不调用 `codex resume`。

## 独立验收

主 Agent 亲自检查完整累计 diff、所有变更文件、真实生产调用链和风险相关测试。问题分 P0-P3；P0-P2 必须在同一 TUI 返工并重新完整验收。worker 自述、测试摘要或完成标记不能替代 Review。

只有需求证据齐全、P0-P2 清零、独立验证通过、未验证项披露、Git/远端事实核实后才关闭精确 tmux session 并声称完成。

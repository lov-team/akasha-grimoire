---
name: claude-code-cli-development
description: 在 Epic 监工 App → Issue 负责/验收 App → developer 三层工作流中，使用可见 macOS Terminal + tmux 驱动 Claude Code 作为最底层唯一写入 worker，先给中文计划并自检，再开发、写状态/交付文件并接受 Issue 任务独立 Review 与同会话返工。用户要求用 Claude Code、让 Claude 编码或复用同一 Claude 会话返工时使用。
---

# Claude Code CLI 开发与独立验收

把 Claude Code 当作三层工作流最底层的唯一实现 worker。这里的主 Agent 必须是独立 Codex App Issue 负责/验收任务；它负责需求解释、范围、用户决策、完整 diff Review、风险复测和 Git 结论，但不得自己写或代修业务代码。Epic 监工只接收 Issue Evidence，不越级轮询 Claude worker。

## 读取规则并核对 CLI

1. 先读项目 `AGENTS.md`、原始需求、相关代码和 Git 现场；一个 worktree 同时只允许一个写入 worker。
2. 首次使用或版本变化时运行 `command -v claude`、`claude --version`、`claude --help`，再读 [references/cli-contract.md](references/cli-contract.md)。参数不匹配就停止更新合同。
3. 不把需求解释、产品取舍、业务调用链和成功标准外包给 Claude。
4. 权限、凭证、安全、不可逆操作或范围歧义先交给用户决定。

## 建立 prompt contract

写明中文要求、目标与逐条验收、已确认决策、非目标、唯一 worktree、允许/禁止路径、TDD/验证门禁、Git 权限、状态与交付文件路径。要求 Claude：先输出中文计划并自检，再在同一 TUI 原地实现；不派生写入者、不输出思考过程；阶段切换原子覆盖单行状态；最终写中文交付且末行为 `CLAUDE_DELIVERY_COMPLETE`。

状态仅允许 `CLAUDE_PLANNING`、`CLAUDE_IMPLEMENTING`、`CLAUDE_BLOCKED_USER_DECISION`、`CLAUDE_DELIVERY_COMPLETE`。交付包含文件、需求映射、Red/Green/Refactor 证据、测试、未验证项、风险和 Git 状态。

## 在可见 Terminal + tmux 启动

先说明将打开 Terminal，再调用 `scripts/launch-visible-cli.zsh <session> <runner> <worktree>`。runner 位于仓库外唯一临时路径且权限为 `700`，runner `cd` 与 tmux `new-session -c` 锁定同一物理 worktree。

在 runner 中使用当前 help 已验证的交互入口：

```bash
cd "$TASK_WORKTREE"
test "$(pwd -P)" = "$(cd "$TASK_WORKTREE" && pwd -P)"
claude --permission-mode bypassPermissions \
  --append-system-prompt "全程使用简体中文；先计划并自检，再原地实现。" \
  "$PLAN_AND_IMPLEMENT_PROMPT"
```

`bypassPermissions` 只免除工具确认，不扩大范围、Git 或用户决策权限。若当前环境策略要求显式允许危险跳过，先核对 help 与项目安全边界，不擅自附加参数。不得用 `-p/--print` 单轮模式冒充持续 TUI，也不得在隐藏 PTY 启动。

## 低噪声长轮询与同会话返工

启动成功后运行：

```bash
scripts/wait-for-delivery.zsh \
  "$STATUS_FILE" CLAUDE_DELIVERY_COMPLETE \
  "$HANDOFF_FILE" CLAUDE_DELIVERY_COMPLETE \
  240
```

让脚本在进程内固定每 5 秒检查一次。默认等待 240 秒；任务明确较长时可提高，但不要用更短等待恢复高频轮询。循环中零输出，双重完成时才输出一行并退出 0，整段超时只输出一次最后状态并退出 124。若宿主先返回运行 session，使用一次支持的最长等待续接，不要由主 Agent 每 5 秒轮询。

退出 0 后只读一次交付文件再 Review。退出 124 时，implementing/missing 重新等待 240 秒或更长，blocked 才请求用户决策，异常状态才做一次最小诊断。不要抓 pane、过程输出、思考、token、进程或中间 diff。正常返工直接在现有 TUI 提交一行读取仓库外返工合同的指令；不要使用 `--continue/--resume`，除非原 TUI 已意外退出且用户授权恢复。

## 独立验收

主 Agent 亲自审阅完整累计 diff、所有文件和真实调用链，按风险独立复跑受影响模块与直接依赖契约测试。问题分 P0-P3，P0-P2 必须在同一 TUI 关闭问题后重新完整验收。Claude 自述、测试摘要或完成标记不能替代 Review。

只有需求证据齐全、P0-P2 清零、独立验证通过、未验证项披露、Git/远端事实核实后才关闭精确 tmux session 并声称完成。

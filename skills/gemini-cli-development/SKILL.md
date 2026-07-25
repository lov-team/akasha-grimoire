---
name: gemini-cli-development
description: 使用可见 macOS Terminal + tmux 驱动 Gemini CLI 在同一交互会话中先给中文计划并自检，再开发、写状态/交付文件并接受主 Agent 独立 Review 与返工。用户要求用 Gemini CLI、让 Gemini 编码、计划后实现、持续监工或复用同一 Gemini 会话返工时使用。
---

# Gemini CLI 开发与独立验收

把 Gemini 当作实现 worker。主 Agent 负责需求解释、范围、用户决策、完整 diff Review、风险复测和 Git 结论。

## 读取规则并核对 CLI

1. 先读项目 `AGENTS.md`、原始需求、相关代码和 Git 现场；一个 worktree 同时只允许一个写入 worker。
2. 首次使用或版本变化时运行 `command -v gemini`、`gemini --version`、`gemini --help`，再读 [references/cli-contract.md](references/cli-contract.md)。参数不匹配就停止更新合同。
3. 不把需求解释、产品取舍、业务调用链和成功标准外包给 Gemini。
4. 权限、凭证、安全、不可逆操作或范围歧义先交给用户决定。

## 建立 prompt contract

写明中文要求、目标与逐条验收、已确认决策、非目标、唯一 worktree、允许/禁止路径、TDD/验证门禁、Git 权限、状态与交付文件路径。要求 Gemini：

- 先输出中文计划并自检需求、边界、Red → Green → Refactor、验证与风险，再在同一 TUI 原地实现；
- 不派生其他写入者，不采集或输出思考过程；
- 阶段切换时原子覆盖单行状态文件；
- 只有实现与自测结束后才写中文交付文件，末行写 `GEMINI_DELIVERY_COMPLETE`。

状态仅允许 `GEMINI_PLANNING`、`GEMINI_IMPLEMENTING`、`GEMINI_BLOCKED_USER_DECISION`、`GEMINI_DELIVERY_COMPLETE`。交付包含文件、需求映射、测试命令与结果、未验证项、风险和 Git 状态。

## 在可见 Terminal + tmux 启动

先说明将打开 Terminal，再调用 `scripts/launch-visible-cli.zsh <session> <runner> <worktree>`。runner 位于仓库外唯一临时路径且权限为 `700`，三处目录锁定一致：runner `cd`、tmux `new-session -c`、Gemini 在该目录启动。

在 runner 中使用当前 help 已验证的交互入口：

```bash
cd "$TASK_WORKTREE"
test "$(pwd -P)" = "$(cd "$TASK_WORKTREE" && pwd -P)"
gemini --skip-trust --approval-mode yolo --prompt-interactive "$PLAN_AND_IMPLEMENT_PROMPT"
```

完全批准只免除工具逐项确认，不扩大路径、Git 或需求权限。不得用 `-p/--prompt` 的 headless 单轮模式冒充持续 TUI；不得在隐藏 PTY 或 Codex 右侧终端启动。启动器拒绝复用同名 tmux session，并开启 mouse 与足够 scrollback。

## 低噪声长轮询

启动成功后立即运行轮询脚本，让脚本在进程内每 5 秒检查一次，不要由主 Agent 高频调用工具：

```bash
scripts/wait-for-delivery.zsh \
  "$STATUS_FILE" GEMINI_DELIVERY_COMPLETE \
  "$HANDOFF_FILE" GEMINI_DELIVERY_COMPLETE \
  240
```

默认等待 240 秒；任务明确较长时可提高，但不要用更短等待恢复高频轮询。脚本在循环中零输出；仅当状态和交付末行同时完成时输出一行并退出 0，整段超时则只输出一次最后状态并退出 124。若宿主先返回仍在运行的 session，使用一次支持的最长等待继续该进程，不要每 5 秒读取文件或轮询 session。

退出 0 后只读一次交付文件并进入 Review。退出 124 时按最后状态处理：implementing/missing 则重新执行一轮 240 秒或更长的等待；blocked 才请求用户决策；异常状态才做一次最小诊断。不要抓 pane、过程输出、思考、token、进程或中间 diff。同一 TUI 正常存活时不要使用 `--resume`。

## 独立 Review 与返工

完成后主 Agent 亲自检查 `git status`、完整累计 diff、所有变更文件和真实调用链，并按风险复跑受影响模块与直接依赖契约测试。worker 自述和其测试摘要不能替代验收。

问题按 P0-P3 分类；P0-P2 必须把含文件/行、违反合同、失败证据、期望与限定范围的返工合同写入仓库外文件，再向同一 TUI 发送一行读取指令。不得重启会话或另开第二个 worker。每轮重新检查完整累计 diff。

只有需求逐条有证据、P0-P2 清零、独立验证通过、未验证项披露、Git/远端事实核实后才关闭精确 tmux session 并声称完成。

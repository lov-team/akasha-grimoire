---
name: claude-code-cli-development
description: 在 Epic 监工 App → Issue 负责/验收 App → developer 三层工作流中，使用可见 macOS Terminal + tmux 驱动 Claude Code 作为最底层唯一写入 worker，先给中文计划并自检，再开发、写状态/交付文件并接受 Issue 任务独立 Review 与同会话返工。用户要求用 Claude Code、让 Claude 编码或复用同一 Claude 会话返工时使用。
---

# Claude Code CLI 开发与独立验收

把 Claude Code 当作三层工作流最底层的唯一实现 worker。这里的主 Agent 必须是独立 Codex App Issue 负责/验收任务；它负责需求解释、范围、用户决策、完整 diff Review、风险复测和 Git 结论，但不得自己写或代修业务代码。Epic 监工只接收 Issue Evidence，不越级轮询 Claude worker。

## 读取规则并核对 CLI

1. 先读项目 `AGENTS.md`、原始需求、相关代码和 Git 现场；默认一个 Issue、一个 Codex App 任务、一个 worktree、同一时刻一个 Claude Code TUI。正常流程复用原 TUI，异常退出时按下述恢复规则启动唯一替代 TUI。
2. 首次使用或版本变化时运行 `command -v claude`、`claude --version`、`claude --help`，再读 [references/cli-contract.md](references/cli-contract.md)。参数不匹配就停止更新合同。
3. 不把需求解释、产品取舍、业务调用链和成功标准外包给 Claude。
4. 权限、凭证、安全、不可逆操作或范围歧义先交给用户决定。

## 委托后自治与单向会话通信

- 任务带有父会话、Epic 监工或其他委托来源时，当前 Issue task 接受委托后独立负责需求对齐、用户决策、返工、验证、Git 交付与异常恢复；所有阶段与终态都写状态/交付文件，不向父会话发送消息。
- P0-P2、测试或日志不合格、diff 偏离都由当前 Issue task 直接驱动 Claude Code 修正并复验。需要产品选择时直接在当前 Issue task 向用户提问；不得让父会话代为转问、批准或恢复 worker。
- 会话消息只允许父会话向当前 Issue task 下发任务、决策或返工；当前 Issue task 不向父会话发送消息。它在阶段变化时原子更新父会话指定的单行状态文件，终态另写交付文件，由父会话的长轮询读取。
- 父会话的存在不降低当前 Issue task 的自主性，也不构成重启异常 worker、继续返工或执行已授权 Git 闭环所需的新权限。

## 建立 prompt contract

写明中文要求、目标与逐条验收、已确认决策、非目标、唯一 worktree、允许/禁止路径、TDD/验证门禁、Git 权限、状态与交付文件路径。要求 Claude：先输出中文计划并自检，再在同一 TUI 原地实现；不派生写入者、不输出思考过程；阶段切换原子覆盖单行状态；最终写中文交付且末行为 `CLAUDE_DELIVERY_COMPLETE`。

状态仅允许 `CLAUDE_PLANNING`、`CLAUDE_IMPLEMENTING`、`CLAUDE_BLOCKED_USER_DECISION`、`CLAUDE_SCOPE_DRIFT`、`CLAUDE_ERROR`、`CLAUDE_ABORTED`、`CLAUDE_DELIVERY_COMPLETE`。交付包含文件、需求映射、Red/Green/Refactor 证据、测试、未验证项、风险和 Git 状态。

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
  1200
```

让脚本在进程内固定每 20 秒检查一次，单轮最长 20 分钟。循环中零输出：双重完成退出 0；阻塞、偏航、错误或取消等可动作状态立即退出 3；整段无可动作终态才输出一次最后状态并退出 124。若宿主先返回运行 session，使用一次支持的最长等待续接，不要由主 Agent 轮询文件。

退出 0 后只读一次交付文件再 Review。退出 3 时按报告状态处理；退出 124 时，implementing/missing 再启动一轮 20 分钟监控，异常状态才做一次最小诊断。不要抓 pane、过程输出、思考、token、进程或中间 diff。正常返工直接在当前 TUI 提交一行读取仓库外返工合同的指令；session 正常存活时不得重启或使用 `--continue/--resume`。若精确 session 已异常退出，改走下述唯一替代 TUI 恢复，不通知父会话等待批准。

### Claude Code TUI 异常退出后的自主恢复

- 状态/交付长等待连续两轮仍缺失或不前进时，只读确认记录的精确 tmux session 是否存在；不得读取 pane。session 仍存在则继续按状态规则等待或处理，禁止重复投递。
- 若精确 session 已不存在，视为 worker 异常退出。当前 Issue task 不向父会话请求许可、不停在阶段性阻塞，也不自行写业务代码；先审计现有 Git 现场与最后有效交付，确认没有第二个写入者或未确认产品决策。
- 在同一 worktree、同一分支上启动一个新的唯一可见 Terminal+tmux 替代 TUI。使用新的精确 session 名、runner、状态和交付路径；prompt 必须完整携带原合同、已确认决策、累计 diff、独立 Review 问题、当前阶段和禁止项。不得使用 `--continue/--resume`，不得假装恢复原 Claude Code 内部会话。
- 替代 TUI 只接续尚未完成的阶段；Review 返工只处理已确认 P0-P2，不得重做已通过阶段或扩大需求。任一时刻仍只允许一个 Claude Code 写入者。
- 每次异常退出最多自动启动一个替代 TUI；若替代 TUI 再次异常退出，先做最小根因诊断并再选择安全恢复。只有确认环境持续不可用、用户取消或无法在既有授权内继续时，才写入最终失败/阻塞状态与交付证据。

## 独立验收

主 Agent 亲自审阅完整累计 diff、所有文件和真实调用链，按风险独立复跑受影响模块与直接依赖契约测试。问题分 P0-P3，P0-P2 必须在当前活动 TUI 关闭问题后重新完整验收；session 异常退出则按恢复规则使用唯一替代 TUI。Claude 自述、测试摘要或完成标记不能替代 Review。

只有需求证据齐全、P0-P2 清零、独立验证通过、未验证项披露、Git/远端事实核实后才主动关闭记录的每个精确 tmux session 并声称完成；已自然退出的 session 记录事实即可。默认由 Issue task 完成已授权的 Git 交付与收尾；若存在父会话，只在全部完成后写入最终 `ISSUE_COMPLETE` 状态与交付文件，中间失败由当前 Issue task 自行处理且不发送会话消息。

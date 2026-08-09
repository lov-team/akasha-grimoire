---
name: codex-cli-development
description: 使用可见 macOS Terminal + tmux 驱动 Codex CLI 在同一交互 TUI 中先给中文计划并交付 Red 测试证据，待 Issue 负责/验收任务审核后继续实现，最后接受完整 diff Review 与返工。仅在用户明确要求 Codex CLI、Terminal、tmux、交互 TUI 或复用现有 Codex CLI 会话时使用；一般“让另一个 Codex 编码”或“用 Codex App 子任务开发”改用 codex-app-development。
---

# Codex CLI 开发与独立验收

把 CLI 中的 Codex 当作实现 worker；当前主 Agent 仍负责需求解释、范围、用户决策、完整 diff Review、风险复测与 Git 结论。不要把 Codex App 任务管理和本 CLI 会话混为一谈。用户没有明确指定 CLI/TUI 时，优先使用 `codex-app-development` 的独立 App task/worktree 与单向下发、状态文件监控机制。

## 读取规则并核对 CLI

1. 先读项目 `AGENTS.md`、原始需求、相关代码与 Git 现场；默认一个 Issue、一个 Codex App 任务、一个 worktree、同一时刻一个 Codex CLI TUI。正常流程复用原 TUI，异常退出时按下述恢复规则启动唯一替代 TUI。
2. 首次使用或版本变化时运行 `command -v codex`、`codex --version`、`codex --help`，再读 [references/cli-contract.md](references/cli-contract.md)。参数不匹配就停止更新合同。
3. 主 Agent 自行确定逐条验收、非目标、真实调用链和验证门禁。
4. 权限、凭证、安全、不可逆操作或范围歧义先交给用户决定。

## 委托后自治与会话通信

- 任务带有父会话、Epic 监工或其他委托来源时，当前 Issue task 接受委托后独立负责需求对齐、用户决策、Red 审核、返工、验证、Git 交付与异常恢复；所有阶段与终态都写状态/交付文件，由父会话的长轮询读取。
- P0-P2、Red 不合格、测试或日志不合格、diff 偏离都由当前 Issue task 直接驱动 Codex CLI 修正并复验。需要产品选择时直接在当前 Issue task 向用户提问；不得让父会话代为转问、批准或恢复 worker。
- 会话消息以父到子为主：父会话向当前 Issue task 下发任务、决策或返工。当前 Issue task 在阶段变化时原子更新父会话指定的单行状态文件，终态另写交付文件。父子两端都是 Claude Desktop 或 Claude Code 会话时（两者已支持会话互发），当前 Issue task 在进入可动作终态（`ISSUE_COMPLETE`、`ISSUE_BLOCKED_USER_DECISION`、`ISSUE_ERROR`、`ISSUE_ABORTED`）时额外向父会话发送一条简短唤醒消息，每个状态最多一条，只含状态名与状态/交付文件路径；文件仍是唯一事实源。父会话不支持接收消息时保持纯单向，不发送任何回推，也不发送阶段性进展。
- 父会话的存在不降低当前 Issue task 的自主性，也不构成重启异常 worker、继续返工或执行已授权 Git 闭环所需的新权限。

## 建立 prompt contract

写明中文要求、唯一 worktree、目标、决策、非目标、允许/禁止路径、TDD/验证、Git 权限、状态与交付文件。把每个核心不变量绑定到真实生产入口、权威 owner、可观察结果、必须失败的负例和测试。要求 worker 先输出中文计划并自检，再只修改测试及专用 fixture/support 并交付真实 Red；收到主 Agent 的继续指令后才在同一 TUI 实现。不派生写入者、不输出思考过程；阶段切换原子覆盖单行状态；最终写中文交付且末行为 `CODEX_DELIVERY_COMPLETE`。

状态仅允许 `CODEX_PLANNING`、`CODEX_RED_READY`、`CODEX_IMPLEMENTING`、`CODEX_BLOCKED_USER_DECISION`、`CODEX_SCOPE_DRIFT`、`CODEX_ERROR`、`CODEX_ABORTED`、`CODEX_DELIVERY_COMPLETE`。为 Red 阶段和最终阶段分别指定唯一仓库外交付文件。Red 交付包含测试 diff、fixture/producer 来源、完整命令、退出码、精确失败断言和短日志路径，末行为 `CODEX_RED_READY`；最终交付包含文件、需求映射、Red/Green/Refactor 证据、测试、未验证项、风险和 Git 状态。

功能、缺陷、跨模块状态、协议、事务、恢复或复杂 UI 代码默认启用 Red 预审。纯文档、纯视觉、格式修改或已有精确失败用例的极小修复可以豁免，但必须在 prompt contract 写明理由；豁免任务不使用 `CODEX_RED_READY`。

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

启动成功后按当前阶段运行：

```bash
scripts/wait-for-delivery.zsh \
  "$STATUS_FILE" "$EXPECTED_STATUS" \
  "$HANDOFF_FILE" "$EXPECTED_MARKER" \
  1200
```

让脚本在进程内固定每 20 秒检查一次，单轮最长 20 分钟。循环中零输出：双重完成退出 0，可动作状态立即退出 3，整段无可动作终态才输出一次最后状态并退出 124。若宿主先返回运行 session，使用一次支持的最长等待续接，不要由主 Agent 轮询文件。

启用 Red 预审时，第一阶段把 expected status 和 marker 都设为 `CODEX_RED_READY`。主 Agent 在三层拓扑内即 Issue 负责/验收 task；它先用累计变更清单确认生产实现未修改，再审测试 diff、fixture/producer、失败日志相关片段和必要生产契约，确认测试从真实入口进入、Red 因目标行为缺失失败、断言精确且核心逻辑未被 mock 或私有 helper 绕过。不通过时只要求同一 Codex TUI 修正测试；通过后投递单行 `Red 证据已审核通过，请继续 Green → Refactor，并按最终交付合同完成。`，再把 expected status 和 marker 都设为 `CODEX_DELIVERY_COMPLETE` 等待最终交付。

每阶段退出 0 后只读一次对应交付文件并进入该阶段 Review。退出 3 时按报告状态处理；退出 124 时 planning/implementing/missing 再启动一轮 20 分钟监控，Red ready 立即进入 Red Review，异常状态才做一次最小诊断。不要抓 pane、过程输出、思考、token、进程或中间 diff。正常返工在当前 TUI 中只发送一行读取仓库外返工合同的指令；session 正常存活时不得重启或调用 `codex resume`。若精确 session 已异常退出，改走下述唯一替代 TUI 恢复，不通知父会话等待批准。

所有向现有 Codex TUI 的继续、决策或返工输入都必须先写入仓库外的唯一单行文件，再通过统一脚本提交：

```bash
scripts/submit-to-tmux.zsh \
  "=$EXACT_SESSION:$WINDOW_INDEX.$PANE_INDEX" \
  "$SINGLE_LINE_INPUT_FILE"
```

必须记录启动时的精确 session/window/pane，不能使用模糊 target。该脚本校验目标与单行输入后固定执行 `load-buffer → paste-buffer → 短暂等待 → send-keys Enter`，任一步失败都会返回非零；调用者不得自行拆开这些命令、只粘贴不提交、追加第二次 Enter，或为确认提交而读取 pane。脚本成功后立即恢复状态/交付文件轮询；短时间内状态未变化不代表未提交，不得重复投递。

### Codex CLI TUI 异常退出后的自主恢复

- 状态/交付长等待连续两轮仍缺失或不前进时，只读确认记录的精确 tmux session 是否存在；不得读取 pane。session 仍存在则继续按状态规则等待或处理，禁止重复投递。
- 若精确 session 已不存在，视为 worker 异常退出。当前 Issue task 不向父会话请求许可、不停在阶段性阻塞，也不自行写业务代码；先审计现有 Git 现场与最后有效交付，确认没有第二个写入者或未确认产品决策。
- 在同一 worktree、同一分支上启动一个新的唯一可见 Terminal+tmux 替代 TUI。使用新的精确 session 名、runner、状态和交付路径；prompt 必须完整携带原合同、已确认决策、累计 diff、独立 Review 问题、当前阶段和禁止项。不得调用 `codex resume`，不得假装恢复原 Codex CLI 内部会话。
- 替代 TUI 只接续尚未完成的阶段：Red 不合格就先修 Red 并重新交付；Green/Review 返工就只处理已确认 P0-P2；不得重做已通过阶段或扩大需求。任一时刻仍只允许一个 Codex CLI 写入者。
- 每次异常退出最多自动启动一个替代 TUI；若替代 TUI 再次异常退出，先做最小根因诊断并再选择安全恢复。只有确认环境持续不可用、用户取消或无法在既有授权内继续时，才写入最终失败/阻塞状态与交付证据。

## 独立验收

主 Agent 亲自检查完整累计 diff、所有变更文件、真实生产调用链和风险相关测试。问题分 P0-P3；P0-P2 必须在当前活动 TUI 返工并重新完整验收，session 异常退出则按恢复规则使用唯一替代 TUI。worker 自述、测试摘要或完成标记不能替代 Review。

只有需求证据齐全、P0-P2 清零、独立验证通过且未验证项披露后，Issue 负责/验收 task 才主动关闭记录的每个精确 tmux session；已自然退出的 session 记录事实即可。随后默认由 Issue task 提交并 push 当前 Issue 分支、核对远端 SHA，按 `codex-app-development` 合同安全回收精确 worktree并关闭 Issue。若存在父会话，只在此时写入最终 `ISSUE_COMPLETE` 状态与交付文件，并在父会话支持接收时补发一条唤醒消息；任一步失败都保留现场并由当前 Issue task 自行处理，不就阶段性进展向父会话发送消息。Codex CLI worker 不执行最终 Git 交付；默认授权不包含 PR、合并、强推、发布或生产写入。

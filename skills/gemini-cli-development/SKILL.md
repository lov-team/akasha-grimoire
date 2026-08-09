---
name: gemini-cli-development
description: 用户明确指定 Gemini CLI、让 Gemini 编码或要求复用原 Gemini 会话时，使用可见 macOS Terminal + tmux 驱动 Gemini CLI 作为 implementation worker，覆盖 React、Vue、Svelte、HTML、CSS、JavaScript、TypeScript、组件、交互、表单、前端路由、响应式、可访问性、动效和前端测试；在同一 TUI 完成中文计划、Red 门、实现、状态交付和返工，并由主 Agent 独立验收。未明确指定 worker 的代码开发默认使用 codex-app-development 的 GPT-5.6 Sol，并按任务难度选择 thinking。
---

# Gemini CLI 开发与独立验收

仅在用户明确指定 Gemini CLI 时把 Gemini 当作实现 worker；未指定 worker 的前端、后端和全栈代码统一交给 `codex-app-development` 的 GPT-5.6 Sol Codex worker，并按任务难度选择 thinking。纯图片、视频、声音等素材生成仍走对应媒体技能。主 Agent 负责需求解释、范围、用户决策、完整 diff Review、风险复测和 Git 结论。

## 读取规则并核对 CLI

1. 先读项目 `AGENTS.md`、原始需求、相关代码和 Git 现场；默认一个 Issue、一个 Codex App 任务、一个 worktree、同一时刻一个 Gemini TUI。正常流程复用原 TUI，异常退出时按下述恢复规则启动唯一替代 TUI。
2. 首次使用或版本变化时运行 `command -v gemini`、`gemini --version`、`gemini --help`，再读 [references/cli-contract.md](references/cli-contract.md)。参数不匹配就停止更新合同。
3. 不把需求解释、产品取舍、业务调用链和成功标准外包给 Gemini。
4. 权限、凭证、安全、不可逆操作或范围歧义先交给用户决定。

## 委托后自治与单向会话通信

- 任务带有父会话、Epic 监工或其他委托来源时，当前 Issue task 接受委托后独立负责需求对齐、用户决策、返工、验证、Git 交付与异常恢复；所有阶段与终态都写状态/交付文件，不向父会话发送消息。
- P0-P2、测试或日志不合格、diff 偏离都由当前 Issue task 直接驱动 Gemini 修正并复验。需要产品选择时直接在当前 Issue task 向用户提问；不得让父会话代为转问、批准或恢复 worker。
- 会话消息只允许父会话向当前 Issue task 下发任务、决策或返工；当前 Issue task 不向父会话发送消息。它在阶段变化时原子更新父会话指定的单行状态文件，终态另写交付文件，由父会话的长轮询读取。
- 父会话的存在不降低当前 Issue task 的自主性，也不构成重启异常 worker、继续返工或执行已授权 Git 闭环所需的新权限。

## 建立 prompt contract 与前端实现约束

写明中文要求、目标与逐条验收、已确认决策、非目标、唯一 worktree、允许/禁止路径、TDD/验证门禁、Git 权限、状态与交付文件路径。把每个行为不变量绑定到真实页面入口、状态 owner、可观察结果、必须失败的负例和测试。要求 Gemini：

- 先输出中文计划并自检需求、边界、Red → Green → Refactor、验证与风险；启用 Red 门时先只修改测试和专用 fixture/support，写出真实 Red 交付并暂停，收到继续指令后才在同一 TUI 实现；
- 不派生其他写入者，不采集或输出思考过程；
- 阶段切换时原子覆盖单行状态文件；
- 只有实现与自测结束后才写中文交付文件，末行写 `GEMINI_DELIVERY_COMPLETE`。

### 前端实现与验收约束（组件/网页/UI）

1. **设计系统复用**：优先复用现有设计 token、CSS 变量、基础组件和交互惯例；没有合同依据不得重写设计系统、全局样式、依赖体系或引入重复组件库。
2. **两道门与 Red 豁免**：组件行为、状态、表单、路由和数据流改动默认执行 `验收矩阵 → GEMINI_RED_READY → Red Review → Green → Refactor → Final Review`。纯文档、纯视觉样式或已有精确失败用例的极小修改可豁免 Red，但 prompt 必须记录理由，并提供截图或主路径视觉证据。
3. **风险裁剪的前端验证**：先确认目标 viewport 与浏览器；按风险检查响应式断点、键盘操作、焦点顺序、语义与可访问名称、loading/empty/error/disabled 状态、console/runtime error，并运行相关 lint、typecheck、单元、组件或 E2E。只执行与改动相关的检查，交付中披露未验证项及原因。
4. **视觉证据可复现**：截图必须注明页面/路由、viewport、状态和生成时间；动态交互至少覆盖用户主路径和一个失败或边界状态。主 Agent 必须独立查看产物，不能只接受 Gemini 的描述。

状态仅允许 `GEMINI_PLANNING`、`GEMINI_RED_READY`、`GEMINI_IMPLEMENTING`、`GEMINI_BLOCKED_USER_DECISION`、`GEMINI_SCOPE_DRIFT`、`GEMINI_ERROR`、`GEMINI_ABORTED`、`GEMINI_DELIVERY_COMPLETE`。启用 Red 门时为 Red 和最终阶段分别指定唯一仓库外交付文件：Red 交付末行写 `GEMINI_RED_READY`，并包含测试 diff、fixture/producer 来源、完整命令、退出码、精确失败断言和短日志路径；最终交付包含变更文件、需求映射、Red/Green/Refactor、视觉与测试证据、未验证项、风险和 Git 状态。

## 在可见 Terminal + tmux 启动

先说明将打开 Terminal，再调用 `scripts/launch-visible-cli.zsh <session> <runner> <worktree>`。runner 位于仓库外唯一临时路径且权限为 `700`，三处目录锁定一致：runner `cd`、tmux `new-session -c`、Gemini 在该目录启动。

在 runner 中使用当前 help 已验证的交互入口：

```bash
cd "$TASK_WORKTREE"
test "$(pwd -P)" = "$(cd "$TASK_WORKTREE" && pwd -P)"
gemini --skip-trust --approval-mode yolo --prompt-interactive "$PLAN_AND_IMPLEMENT_PROMPT"
```

完全批准只免除工具逐项确认，不扩大路径、Git 或需求权限。不得用 `-p/--prompt` 的 headless 单轮模式冒充持续 TUI；不得在隐藏 PTY 或 Codex 右侧终端启动。启动器拒绝复用同名 tmux session，并开启 mouse 与足够 scrollback。

## 低噪声长轮询与同会话返工

启动成功后立即运行轮询脚本，让脚本在进程内每 20 秒检查一次，不要由主 Agent 高频调用工具：

```bash
scripts/wait-for-delivery.zsh \
  "$STATUS_FILE" "$EXPECTED_STATUS" \
  "$HANDOFF_FILE" "$EXPECTED_MARKER" \
  1200
```

默认等待 1200 秒。脚本在循环中零输出；双重完成时退出 0，可动作状态立即退出 3，整段无可动作终态才输出一次最后状态并退出 124。若宿主先返回仍在运行的 session，使用一次支持的最长等待继续该进程，不要轮询文件或 session。

启用 Red 门时先以 `GEMINI_RED_READY` 为 expected status/marker。主 Agent 独立确认生产实现未改，再审测试入口、fixture 来源、失败断言和日志；不通过就只要求原 TUI 修正 Red，通过后投递单行继续指令，并以 `GEMINI_DELIVERY_COMPLETE` 等待最终交付。每阶段退出 0 后只读一次对应交付文件；退出 3 时处理报告状态；退出 124 时 planning/implementing/missing 再启动一轮 20 分钟监控。不要抓 pane、过程输出、思考、token、进程或中间 diff。

所有继续、决策或返工输入先写入仓库外唯一单行文件，再使用统一脚本提交到启动时记录的精确 pane：

```bash
scripts/submit-to-tmux.zsh \
  "=$EXACT_SESSION:$WINDOW_INDEX.$PANE_INDEX" \
  "$SINGLE_LINE_INPUT_FILE"
```

脚本校验精确 target 与单行输入，固定执行 `load-buffer → paste-buffer → send-keys Enter`。任一步失败都停止；不得自行拆开命令、补第二次 Enter、读取 pane 猜测是否提交，或因状态短时间未变化重复投递。session 正常存活时不得重启或使用 `--resume`；若精确 session 已异常退出，改走下述唯一替代 TUI 恢复。

### Gemini TUI 异常退出后的自主恢复

- 状态/交付长等待连续两轮仍缺失或不前进时，只读确认记录的精确 tmux session 是否存在；不得读取 pane。session 仍存在则继续按状态规则等待或处理，禁止重复投递。
- 若精确 session 已不存在，视为 worker 异常退出。当前 Issue task 不向父会话请求许可、不停在阶段性阻塞，也不自行写业务代码；先审计现有 Git 现场与最后有效交付，确认没有第二个写入者或未确认产品决策。
- 在同一 worktree、同一分支上启动一个新的唯一可见 Terminal+tmux 替代 TUI。使用新的精确 session 名、runner、状态和交付路径；prompt 必须完整携带原合同、已确认决策、累计 diff、独立 Review 问题、当前阶段和禁止项。不得使用 `--resume`，不得假装恢复原 Gemini 内部会话。
- 替代 TUI 只接续尚未完成的阶段：Red 不合格就先修 Red；Green 或 Review 返工只处理已确认 P0-P2。不得重做已通过阶段或扩大需求，任一时刻仍只允许一个 Gemini 写入者。
- 每次异常退出最多自动启动一个替代 TUI；若替代 TUI 再次异常退出，先做最小根因诊断并再选择安全恢复。只有确认环境持续不可用、用户取消或无法在既有授权内继续时，才写入最终失败/阻塞状态与交付证据。

## 独立 Review 与返工

完成后主 Agent 亲自检查 `git status`、完整累计 diff、所有变更文件和真实调用链，并按风险复跑受影响模块与直接依赖契约测试。worker 自述和其测试摘要不能替代验收。

问题按 P0-P3 分类；P0-P2 必须把含文件/行、违反合同、失败证据、期望与限定范围的返工合同写入仓库外文件，再向当前活动 TUI 发送一行读取指令。session 正常存活时不得重启或另开第二个 worker；异常退出时按恢复规则使用唯一替代 TUI。每轮重新检查完整累计 diff。

只有需求逐条有证据、P0-P2 清零、独立验证通过、未验证项披露、Git/远端事实核实后才主动关闭记录的每个精确 tmux session 并声称完成；已自然退出的 session 记录事实即可。默认由 Issue task 完成已授权的 Git 交付与收尾；若存在父会话，只在全部完成后写入最终 `ISSUE_COMPLETE` 状态与交付文件，中间失败由当前 Issue task 自行处理且不发送会话消息。

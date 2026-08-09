---
name: grok-cli-development
description: 使用可见 macOS Terminal + tmux 让 Grok CLI 实现边界明确的小需求和简单网页/UI 修改，或生成图像、UI 概念稿、游戏资产和视频；代码任务在同一 TUI 完成 Plan、Red-only 审核、Green/Refactor，再由 Issue task 独立验收。复杂需求改用 codex-app-development。用户要求用 Grok CLI、让 Grok 干活、生成视觉素材、审查或打回 Grok diff、复用同一 Grok 会话返工时使用。
---

# Grok CLI 开发与独立验收

把 Grok 当作实现 worker。主 Agent 始终负责需求解释、用户决策、范围控制、Red 测试预审、业务实现 Review、独立验证和最终交付结论。在三层拓扑中，此处主 Agent 就是只读的 Issue 负责/验收 task，不是 Epic 监工。

## 先确认边界

1. 读取项目 `AGENTS.md`、用户需求、相关代码和完整 Git 现场；用户即时指令与项目规则优先于本技能。
2. 默认一个 Issue、一个 Codex App 任务、一个 worktree、同一时刻一个 Grok TUI；不得让多个写入者同时修改同一 worktree。正常流程复用原 TUI，异常退出时按下述恢复规则启动唯一替代 TUI。
3. 产品取舍、UI/协议歧义、破坏性操作、权限凭证不明或未知业务文件出现时，先停止并请求用户决策。
4. 不把需求理解、真实调用链识别或成功标准制定外包给 Grok。

## 委托后自治与会话通信

- 任务带有父会话、Epic 监工或其他委托来源时，当前 Issue task 接受委托后独立负责需求对齐、用户决策、Red 审核、返工、验证、Git 交付与异常恢复；所有阶段与终态都写状态/交付文件，由父会话的长轮询读取。
- P0-P2、Red 不合格、截图不合格、日志过期或 diff 偏离都由当前 Issue task 直接驱动 Grok 修正并复验。需要产品选择时直接在当前 Issue task 向用户提问；不得让父会话代为转问、批准或恢复 worker。
- 会话消息以父到子为主：父会话向当前 Issue task 下发任务、决策或返工。当前 Issue task 在阶段变化时原子更新父会话指定的单行状态文件，终态另写交付文件。父子两端都是 Claude Desktop 或 Claude Code 会话时（两者已支持会话互发），当前 Issue task 在进入可动作终态（`ISSUE_COMPLETE`、`ISSUE_BLOCKED_USER_DECISION`、`ISSUE_ERROR`、`ISSUE_ABORTED`）时额外向父会话发送一条简短唤醒消息，每个状态最多一条，只含状态名与状态/交付文件路径；文件仍是唯一事实源。父会话不支持接收消息时保持纯单向，不发送任何回推，也不发送阶段性进展。
- 父会话的存在不降低当前 Issue task 的自主性，也不构成重启异常 worker、继续返工或执行已授权 Git 闭环所需的新权限。

## 先做开发 Agent 选型

- 范围明确、单模块或单一状态 owner、预计不超过 5 个文件和 300 行、核心不变量不超过 3 个，且不涉及协议/schema、迁移、事务、恢复、并发、安全边界或架构决策的小需求可用 Grok 开发。
- 简单网页/UI 修改也可用 Grok：只调整现有页面或组件的文案、颜色、间距、尺寸、局部布局、简单样式或轻量展示逻辑，不新增跨组件状态、路由、API 数据流、复杂表单、权限、拖拽、复杂动效或系统性响应式改造，并必须执行截图或主路径视觉验证。
- 超出任一条件就是复杂需求，直接交给新的 Codex App developer；尤其是新交互状态、跨组件协作、路由/API、设计系统或多页面重构，不要先让 Grok 实现一轮再迁移。

## 先做任务规模闸门

Grok 适合作为边界明确的实现 worker，不默认一次承接小 Epic。启动前先估算改动；命中任一项时，优先把任务拆成有依赖顺序的多个 Issue，再分别启动：

- 预计修改超过 12 个文件或新增超过 1200 行；
- 同时改变超过 2 个权威状态 owner；
- 一次横跨协议、服务端事务和客户端 UI 三层；
- 超过 8 个可独立验证的核心不变量；
- 同时要求状态机迁移、重连/恢复、UI 交互和端到端证据。

用户或项目明确要求原子交付且无法安全拆分时，记录不拆分理由，并把每个状态 owner 分成独立验证阶段；不得把范围风险只写进最终“已知风险”。拆分后的每个 Issue 都必须能独立 Red、实现和验收，不用并行写入同一 worktree 换取速度。

## 强制中文交互

- Grok 面向用户的计划、提问、选择项、进度摘要、测试说明、返工答复和最终交付一律使用**简体中文**。
- 命令、代码、文件名、API/类型/字段标识符和原始错误可保留英文，但必须紧跟中文解释。
- 每次 Plan、开发和返工启动都显式加入：

  ```bash
  --rules "全程使用简体中文与用户交互；计划、提问、进度摘要、测试说明和最终交付均用中文。命令、代码、标识符和原始错误可保留英文，但必须用中文解释。"
  ```

- prompt contract 第一行再次写明“全程使用简体中文”，仓库外交付文件也必须用中文撰写。
- Grok 若输出英文计划或要求用户用英文确认，立即在同一可见 TUI 要求其用中文完整重写；中文版本通过前不得进入下一阶段。

## 核对 CLI

首次使用或版本变化时，用普通非 PTY 命令运行：

```bash
command -v grok
grok --version
grok --help
```

本流程依赖：

- runner 的显式 `cd`、tmux `new-session -c` 与 Grok `--cwd`：三重锁定唯一 worktree；
- `--permission-mode bypassPermissions` + `--always-approve`：TUI 明确处于完全批准状态；计划阶段由 prompt 强制先输出并自检，通过后在原 TUI 直接开发；
- `--no-subagents`：禁止 Grok 再派生写入者；
- `--minimal --no-alt-screen`：在 Terminal + tmux 弹窗中使用可见、可滚动的 inline TUI；
- `--always-approve`：启动时固定启用，避免逐条工具审批；它不改变 worktree、路径、Git 权限与用户决策约束。

参数不匹配当前 `grok --help` 时停止并更新调用方式，不能凭印象拼接。

## 建立 prompt contract

调用 Grok 前明确：

- 原始目标和逐条验收标准；
- 已确认决策、真实歧义与非目标；
- worktree、基线、允许和禁止修改的路径；
- Red → Green → Refactor 顺序；
- focused、受影响模块、直接依赖契约测试、全量升级条件、import、UI、网络或真实设备验证；
- Git 权限边界；
- 仓库外交付文件路径与固定完成标记。

对代码任务，由 Issue 负责/验收 task 在启动 Grok 前把连续长合同压缩成“短主合同 + 验收矩阵”。主合同只保留目标、边界、真实入口、禁止路径与交付门禁；矩阵逐个绑定：

| 不变量 | 生产入口 | 权威 owner | 可观察结果 | 必须失败的负例 | 测试 |
|---|---|---|---|---|---|
| 一条核心行为 | 实际入口符号 | 唯一状态所有者 | 事件/状态/UI | 精确拒绝或回滚 | 真实测试名 |

协议 fixture 必须来自真实生产 producer、仓库内 canonical/golden wire fixture，或对真实 producer 输出的最小裁剪。不得根据 Issue 文案手写简化协议并让实现反向适配测试；确实只能手写时，先逐字段对照生产 encoder/decoder 并在 Red 交付中记录来源。

视觉生成任务还必须明确：用途、画幅/分辨率或视频时长、风格、角色与世界观、必须出现和禁止出现的元素、参考图仅允许借鉴的维度、精确文字、候选数量、仓库外 staging 路径，以及是否需要用户选稿后才能进入实现。

## 图像、UI 概念稿与视频生成

- 用户把任务交给 Grok CLI 时，所需的图像、UI mockup、游戏资产、动效概念和视频也由同一个 Grok TUI 使用其当前可用的内置生成能力完成；主 Agent 不另开生图 worker，也不代替 Grok 调用其他生成通道。
- 生成前先用最小 smoke 核对真实工具、模型、参考输入、输出格式和限制。不得凭记忆写死模型能力，不得绕过 Grok 内置能力直连供应商，也不得输出凭证、Cookie、临时授权 URL 或隐藏 provider 响应。
- 纯视觉任务不强套 Red → Green → Refactor；改用 `smoke → 首稿 → 目视 QA → 单点修正 → 最终交付`。若同时包含代码实现，视觉确认之后的业务代码仍严格执行 TDD。
- 预览和原始生成物放在仓库外唯一 `/tmp/<project>-<issue>-grok-visual-<round>/`；未经用户或 Issue 明确选定，不得复制进生产资产、修改 Godot 场景或围绕未确认稿编码。仓库的文件名、尺寸、版权/IP、import 和 staging 契约仍然有效。
- 竞品图只能作为明确标注的构图、层级、节奏或交互参考，不得复刻角色、Logo、专有纹样、文案、具体控件造型或像素布局。生成稿必须符合项目原创世界观。
- 每张图由 Grok 目视检查完整构图、主体、UI 层级、文字、禁用项和技术可实现区；视频还要检查关键帧、时长、运动连贯性、闪烁/形变、音画与循环边界。发现问题只做针对性重试，不用无差别重复生成掩盖失败。
- 需要用户选稿时，Grok 把候选绝对路径、实际尺寸/时长、最终 prompt、设计取舍、推荐项和已知缺陷写入仓库外决策文件，状态切为 `GROK_BLOCKED_USER_DECISION` 并停在同一 TUI。主 Agent 独立查看原图或视频证据后再向用户展示；用户选择后才向同一会话恢复指令。
- 最终交付文件必须列出所有采用/淘汰产物路径、实际模型或内置工具、生成次数、QA 结论、选稿结果、是否进入仓库及 Git 状态。主 Agent 必须独立查看图像原文件；视频至少核对元数据、代表性帧和可播放成片，不能只信 Grok 自述。

交付文件使用本轮唯一的新路径，例如：

```text
/tmp/<project>-issue-<number>-grok-delivery-round-<n>.md
```

启动前确认该路径不存在；若已存在，递增 round，不删除或复用旧文件。末行固定为：

```text
GROK_DELIVERY_COMPLETE
```

## 启动可见 Terminal + tmux

始终使用 **macOS Terminal + attached tmux**，不尝试 Codex App 右侧终端。使用 [`scripts/launch-visible-grok.zsh`](scripts/launch-visible-grok.zsh) 打开预先生成的 runner：

```bash
scripts/launch-visible-grok.zsh \
  <tmux-session-name> \
  </absolute/path/to/runner.zsh> \
  </absolute/path/to/task-worktree>
```

若系统没有可见 Terminal 能力，把命令交给用户执行并暂停；不得用 Codex 右侧终端、`-p`、后台 PTY 或隐藏 tmux 冒充可见 TUI。

使用弹窗前先说明将打开 Terminal。runner 必须位于仓库外的唯一临时路径、权限为 `700`，内容必须先 `cd "$TASK_WORKTREE"` 并校验成功，再显式传入同一路径的 Grok `--cwd`，同时固定 Grok 参数和 prompt 文件。启动器把同一路径传给 tmux `new-session -c`。session 名使用项目、Issue、阶段组合并只含字母、数字、点、下划线和短横线，例如 `mahjong-249-plan`。

启动器必须加载 [`scripts/tmux-visible.conf`](scripts/tmux-visible.conf)：开启 `mouse` 并将 `history-limit` 设为 50000。用户可直接用滚轮进入 copy-mode 回看；键盘方式为 `Ctrl-b` 后按 `[`，再用 `PageUp`/方向键滚动，按 `q` 返回 Grok 输入。不得为解决滚动问题切回 full-screen/alternate-screen。

初次启动禁止附着或复用同名 tmux session；同名已存在必须报错，避免 `new-session -A` 忽略本轮目录。启动脚本负责一次性核对 `pane_current_path` 的物理路径严格等于任务 worktree；不读取 pane 内容。目录不一致时不得进入计划或开发，应报告并只处理这个精确 session。路径通过后只允许用 `tmux list-sessions` 确认会话存在且 attached；禁止 `capture-pane`、后台 attach、截图读取 Grok 过程、持续 `pgrep` 或轮询 TUI 输出。没有现成 tmux client 时不要调用 `display-popup`；由启动脚本打开 Terminal 并在其中创建/附着会话。

## 在可见终端启动 Plan、Red 闸门与开发

主 Agent 完成前置决策闸门后，把计划与实现契约放入可见 Terminal + tmux 一次启动：

```bash
cd "$TASK_WORKTREE"
test "$(pwd -P)" = "$(cd "$TASK_WORKTREE" && pwd -P)"
grok --cwd "$TASK_WORKTREE" \
  --minimal \
  --no-alt-screen \
  --permission-mode bypassPermissions \
  --no-subagents \
  --always-approve \
  --rules "全程使用简体中文与用户交互；计划、提问、进度摘要、测试说明和最终交付均用中文。命令、代码、标识符和原始错误可保留英文，但必须用中文解释。" \
  "$PLAN_AND_IMPLEMENT_PROMPT"
```

硬约束：

- runner、tmux 与 `grok --cwd` 的三处路径必须是同一个经过物理路径解析的任务 worktree；任一不一致立即停止，不能靠 prompt 口头约束目录。
- 不使用 `exec_command` 的 `tty:true`、后台统一 PTY或隐藏终端启动 Grok TUI。tmux 只允许按上一节通过可见 Terminal attached 会话使用。
- 不使用 `-p/--single` 代替同一可见 TUI 内的 Plan 自检与直接开发。
- 启动固定同时使用 `--permission-mode bypassPermissions --always-approve`，确保 TUI 显示并实际处于完全批准状态；完全授权只免除工具逐条审批，不授权扩大范围、Git 交付或替用户决定前置歧义。
- prompt 必须要求 Grok 先输出中文计划并自检需求、TDD、边界、风险与验证；确认无遗漏后在同一 TUI 进入 Red。高风险代码任务先停在下述 Red 闸门；豁免任务才原地直接完成实现。全程不退出、不调用 `--continue`、不启动第二个 Grok。
- 必须由用户决定的事项在启动前解决；开发中新发现的决策阻塞写入状态文件并停止等待用户。

`PLAN_AND_IMPLEMENT_PROMPT` 必须要求：

1. 先读 worktree 内 `AGENTS.md`；
2. 先输出并自检计划；确认无遗漏后先执行 Red，不等待用户在窗口确认计划；
3. 只修改允许范围；
4. 遇到冲突、未知业务改动、测试设施故障或用户决策时停止；
5. 命中 Red 闸门时先写 Red 交付文件并暂停，收到主 Agent 的继续指令后才执行 Green → Refactor；
6. 完成实现和自测后，才写最终交付文件；
7. 最终交付文件用中文包含修改文件、需求映射、测试命令与结果、未验证项、风险和 Git 状态，末行写固定完成标记。

### Red-only 中间审核

进入 Grok 路径的功能或缺陷默认启用 Red 闸门。纯文档、纯视觉生成、只改格式、已有精确失败用例的极小修复可以豁免，但必须在 prompt contract 写明理由；跨模块状态、协议、事务、恢复和复杂 UI 应在选型阶段改用 Codex App。

启动前为 Red 阶段指定独立状态与交付路径。Grok 完成测试和真实失败后：

1. 原子写状态 `GROK_RED_READY`；
2. 写中文 Red 交付文件，末行独占 `GROK_RED_READY`；
3. 保持同一 TUI 打开并暂停，不写生产实现。

Red 交付只包含：累计变更清单、新增/修改测试、每个 fixture 的生产来源、完整命令、退出码、精确失败断言、短日志路径，以及“为何是目标行为缺失而不是测试自身错误”。主 Agent 使用 `wait-for-delivery.zsh` 等待双标记，先独立确认生产实现未修改，再审测试 diff、fixture/producer、Red 日志相关片段和必要生产契约；不读取 pane，不提前审未交付的实现。

三层拓扑内由 Issue task 完成这次 Red Review；它不写测试、不代修实现，也不把普通 Red 预审越级转发给 Epic。审核不通过时只要求同一 Grok TUI 修正测试；不得开始生产实现来掩盖错误的 Red。

只有同时满足以下条件才允许 Green：

- 测试从验收矩阵声明的真实入口进入；
- Red 因目标行为缺失失败，不是类型、语法、fixture、解析或环境错误；
- 事件/状态确实发生且有非零或精确断言；
- 集成验收未直接写私有字段、调用私有 helper 或用 mock 替代核心逻辑；
- 负例证明拒绝、清理、回滚或未应用结果，而不是提前返回。

审核通过后，把单行 `Red 证据已审核通过，请继续 Green → Refactor，并按最终交付合同完成。` 写入唯一仓库外文件，再用既有 `tmux load-buffer`、`tmux paste-buffer` 和一次 Enter 投递到同一 TUI。审核不通过时，按返工合同方式只要求修正 Red；不得让 Grok先实现再补证据。

## 低噪声长轮询状态与最终交付

启动前指定唯一的仓库外状态文件和交付文件。代码任务状态文件只允许单行 `GROK_PLANNING`、`GROK_RED_READY`、`GROK_IMPLEMENTING`、`GROK_BLOCKED_USER_DECISION`、`GROK_SCOPE_DRIFT`、`GROK_ERROR`、`GROK_ABORTED` 或 `GROK_DELIVERY_COMPLETE`；豁免 Red 的任务不使用 `GROK_RED_READY`。Grok 在阶段切换时原子覆盖，不写思考过程或长日志。

tmux 启动成功后立即运行一次长轮询，让脚本在进程内每 20 秒检查，不要由主 Agent 高频调用工具：

```bash
scripts/wait-for-delivery.zsh \
  "$GROK_STATUS" GROK_DELIVERY_COMPLETE \
  "$GROK_HANDOFF" GROK_DELIVERY_COMPLETE \
  1200
```

默认等待 1200 秒。脚本循环中零输出；双重完成时退出 0，可动作状态立即退出 3，整段无可动作终态才输出一次最后状态并退出 124。若宿主先返回仍在运行的 session，使用一次支持的最长等待续接该进程，不要轮询文件、session 或发送状态更新。

等待 Red 时把 expected status 和 marker 都设为 `GROK_RED_READY`；退出 0 后执行 Red-only 审核并向同一 TUI 继续或返工。等待最终交付时仍使用 `GROK_DELIVERY_COMPLETE`。最终等待退出 0 后保留 Grok TUI，只读一次中文交付文件并从完整累计 diff 开始独立验收。退出 3 时按报告状态处理；退出 124 时，`GROK_PLANNING`、`GROK_IMPLEMENTING` 或缺失都不自动输入，确认仍稳定后再启动一轮 20 分钟监控；`GROK_RED_READY` 立即进入 Red 审核；异常状态才做一次最小诊断。

等待期间不检查中间 Git 状态、文件列表、tmux pane、进程、测试进度、思考过程、token 或中间 diff，不发送 `Ctrl-C`。开发中的文件变化留到最终 Review。若发现 P0-P2，向当前 Grok TUI 提交返工合同后再次使用同一轮询脚本；session 正常存活时不得重启、不得使用 `--continue`、不得新建 tmux session，也不管理 Grok session ID。若精确 session 已异常退出，改走下述唯一替代 TUI 恢复，不通知父会话等待批准。

## 从完整 diff 开始 Review

主 Agent 亲自执行并阅读：

```bash
git status --short --branch
git diff --stat
git diff --check
git diff
# worker 已提交时：
git diff "$BASE_REF"...HEAD
git ls-files --others --exclude-standard
```

逐个读取所有 tracked/untracked 变更，并至少核对：

1. 每条验收标准是否在真实生产入口生效；
2. 状态是否由真实构造路径建立，规则是否进入真实命令消费、事件发布/回放和用户可见结果；
3. 是否只新增了 helper、DTO、占位对象或自证测试，却没有接入业务路径；
4. 是否遗漏关键副作用、错误分支、清理、幂等、回滚或跨模块契约；
5. 是否提前实现后续 Issue 或引入未确认决策；
6. 测试是否覆盖真实核心逻辑，mock 是否绕过被测对象；
7. Red 证据是否能证明测试在实现前有效失败。

正式 Review 前先运行 [`scripts/audit-test-strength.zsh`](scripts/audit-test-strength.zsh) 扫描本轮变更测试。恒真放行（如 `or true`、`|| true`）是阻断项；提前 `return`、条件断言、私有访问和允许零次事件属于人工审计项，必须逐条证明不会让核心行为“没发生也通过”。脚本只是下限检查，不能替代调用链 Review。

测试全绿不能替代业务语义 Review。默认按真实生产调用链执行 focused → 受影响模块 → 直接依赖契约测试，不再为每个 Issue 或每轮返工固定跑全量。不得只跑新增测试自证，必须覆盖被改实现的直接调用方、被调用方和共享数据契约。涉及 class/资产跑 import，涉及 UI 做截图/主路径手测，涉及网络或设备而无法真实验证时明确披露。

只有满足以下任一条件才升级全量测试：修改跨模块共享协议/schema、事件序列化/恢复、权威基础状态机或通用规则基础设施；修改 Autoload、项目级配置、插件/依赖、全局 class 解析链或大范围资源导入；focused 出现跨模块 Parse Error/系统性失败或无法可靠界定影响；用户、Issue、发布或里程碑明确要求。未命中时，Grok 在最后一次代码修改后只需跑受影响验证包，并在交付中写清范围推导、命令、totals 和未覆盖风险。主 Agent 审计该日志后用相邻 focused/契约测试独立交叉验证，不机械重复同一测试包。

## P0-P2 打回同一会话

统一严重度：

- P0：阻断、数据损坏或严重安全问题；
- P1：主要功能、架构或用户流程错误；
- P2：正确性、契约、恢复语义或关键覆盖缺口；
- P3：非阻断改进。

P0-P2 必须关闭。返工要求必须用中文包含文件/行、违反的要求、实际行为、期望行为、失败命令和限定范围。使用新的 round 交付文件路径，直接向当前可见 tmux session 中仍打开的 Grok TUI 提交返工 prompt；每轮重新审查完整累计 diff，而不是只看最后补丁。session 正常存活时不得退出/重启 Grok、调用 `--continue` 或另建第二个 tmux session。

标记出现前禁止补充 prompt 或干预。标记出现且 Review 确认需要返工后，先把完整中文返工合同写入唯一的仓库外 `/tmp/*.md` 文件；**不得把长篇、多行返工合同本身直接 paste 进 TUI**，避免 bracketed paste / 多行解析造成明显卡顿或提交状态不清。

tmux 只投递一行短指令，内容必须包含该返工文件的绝对路径，例如：

```text
请读取 /tmp/<project>-issue-<number>-grok-rework-round-<n>.md，并严格执行其中全部返工指令；读取后立即按文件要求更新状态文件。
```

将这行短指令写入另一个唯一的仓库外文本文件，再用 `tmux load-buffer` + `tmux paste-buffer` 送入启动时记录的精确 session/pane，最后仅用一次 `tmux send-keys ... Enter` 提交。不得读取或捕获 pane 输出，不得退出/重启 Grok。随后只轮询该轮状态/交付文件；短时间内状态尚未出现属于正常接收延迟，不得重复粘贴。用户正在 TUI 内操作时先避免并发输入。

### Grok TUI 异常退出后的自主恢复

- 状态/交付长等待连续两轮仍缺失或不前进时，只读确认记录的精确 tmux session 是否存在；不得读取 pane。session 仍存在则继续按状态规则等待或处理，禁止重复投递。
- 若精确 session 已不存在，视为 worker 异常退出。当前 Issue task 不向父会话请求许可、不停在阶段性阻塞，也不自行写业务代码；先审计现有 Git 现场与最后有效交付，确认没有第二个写入者或未确认产品决策。
- 在同一 worktree、同一分支上启动一个新的唯一可见 Terminal+tmux 替代 TUI。使用新的精确 session 名、runner、状态和交付路径；prompt 必须完整携带原合同、已确认决策、累计 diff、独立 Review 问题、当前阶段和禁止项。不得使用 `--continue`，不得假装恢复原 Grok 内部会话。
- 替代 TUI 只接续尚未完成的阶段：Red 不合格就先修 Red 并重新交付；Green/Review 返工就只处理已确认 P0-P2；不得重做已通过阶段或扩大需求。任一时刻仍只允许一个 Grok 写入者。
- 每次异常退出最多自动启动一个替代 TUI；若替代 TUI 再次异常退出，先做最小根因诊断并再选择安全恢复。只有确认环境持续不可用、用户取消或无法在既有授权内继续时，才写入最终失败/阻塞状态与交付证据。

## 验收通过后关闭 tmux 与专用 Terminal 窗口

启动当前 Issue 的可见 tmux 弹窗时记录唯一精确 session 名，并在 session 存活期间始终复用其 Grok TUI。每轮交付文件末行完成标记有效后不得主动关闭；若需返工，直接在现有 TUI 输入框输入并提交 prompt。session 异常退出则按上一节记录新的唯一替代 session；全程不管理 Grok session ID。

关闭前先用 `tmux list-sessions` 只读确认精确名称仍存在，再对记录的每个 session 单独执行：

```bash
tmux kill-session -t "$EXACT_SESSION"
```

只有完整 diff Review 完成、P0-P2 清零且主 Agent 独立验证全部通过后，才主动执行关闭。关闭后再次只读确认该精确 session 已不存在。禁止使用 `tmux kill-server`、glob、前缀匹配、模糊匹配或未经记录的 session 名，不得影响用户的其他 tmux 会话。若 session 已自然退出，记录事实；仍有未完成工作时按异常恢复规则启动替代 TUI，不为单纯清理而新建会话。

`launch-visible-grok.zsh` 必须为本次启动显式创建新的 Terminal 窗口并记录其唯一 window id。精确 tmux session 退出后，wrapper 只在该 window id 仍存在且仍为单标签页时关闭它；若窗口已不存在或用户后来加入了其他标签页，则保留窗口，不得用 `front window`、窗口标题、进程名或模糊匹配强关。关闭结果不影响 tmux 与验收结论。

## Git 与完成条件

默认由主 Agent（在三层拓扑中即 Issue 负责/验收 task）在验收后提交并 push 当前 Issue 分支；Grok 不负责最终 Git 交付。默认授权不包含 PR、合并、强推、发布或生产写入，除非用户或项目规则明确扩大权限。

发生 Git 操作时，独立核对本地 HEAD、远端 SHA、PR 基线与完整 diff、可合并状态和目标分支。提交与 push 成功后按 `codex-app-development` 合同确认 worktree 干净、无未跟踪文件且远端 SHA 一致，再非强制回收精确 worktree、关闭 Issue。若存在父会话，只在此时写入最终 `ISSUE_COMPLETE` 状态与交付文件，并在父会话支持接收时补发一条唤醒消息；任一步失败都保留现场和 Issue并由当前 Issue task 自行处理，不就阶段性进展向父会话发送消息。CI 是否为门禁、是否直接合并，以当前项目 `AGENTS.md` 和用户指令为准，不在技能中硬编码。

只有同时满足以下条件才声称完成：

- 用户需求和决策逐条有真实业务证据；
- 交付文件完成标记有效；
- 主 Agent 已读完整 diff 和所有变更文件；
- P0-P2 清零；
- 主 Agent 独立验证通过；
- 未验证项和风险已披露；
- Git、PR 或合并状态已按实际远端核实。

---
name: agent-task-supervisor
description: 在 Codex App 中以 Spec、Epic、Issue 和证据关系图轻量监工多个任务；由独立 Issue task 制定实现计划与验收矩阵，再创建 GPT-5.6 Luna、thinking=max 的 Codex worker 开发，Issue 独立审核 Red 与完整实现并默认完成 Git 交付、worktree 回收和 Issue 关闭。用户要求用 Graph Engineering 拆解、监工、协调、等待或验收多个任务，或持续推进 worker 但不代替其实现时使用。
---

# Agent 任务监工

把自己当作合同、节奏和验收负责人，不当作另一个实现 worker。

## 建立轻量任务板

只记录推进与恢复所需字段：

| 字段 | 内容 |
|---|---|
| task | 任务名与 task/thread id |
| location | host id、worktree、分支 |
| graph | Spec、Epic、Issue id 与当前节点 |
| scope | Issue 交付合同、验收条件、禁止项 |
| state | 当前阶段、最近一条简短进展、是否需关注 |
| monitor | 状态/交付文件、最近已处理状态与 mtime、监控进程和失联阈值 |
| edges | `depends_on`、`blocks`、`produces`、`validates` |

用户已明确要求开发采用三层分工。Epic 监工发现 ready Issue 后先调用 `create_thread` 建立独立 Issue 负责/验收 task；Issue task 制定实现计划与验收矩阵后，再按 `codex-app-development` 创建使用 GPT-5.6 Luna、thinking=max 的独立 Codex worker。禁止 Epic 监工直接把 developer 当 Issue task，也禁止 Issue task 自己实现再自审。

Epic 创建 Issue task、Issue task 创建或继续 developer 后，直接父任务都立即启动一个最长 20 分钟、每 20 秒扫描一次的本地监控程序。两级监控分别只读直属 child 的单行状态文件与终态交付文件，不能合并、越级或重复；child 不向父会话主动发送消息。

代码任务默认使用两道验收门：Issue task 先定义验收矩阵，developer 只写测试并交付真实 Red，Issue task 审核通过后才允许同一 developer 进入 Green → Refactor；最终交付后再审完整累计 diff。Issue task 不得亲自写测试或生产实现。纯文档、纯视觉、格式修改或已有精确失败用例的极小修复可以豁免 Red 预审，但必须在 Issue 合同中写明理由。

默认授权 Issue task 在最终验收通过后完成当前 Issue 的 Git 交付：提交、推送当前 Issue 分支并核对远端 SHA。该默认授权不包含新建或合并 PR、改写历史、强推、发布或生产写入；项目规则或用户另有要求时优先。Git 交付成功后由 Issue task 安全回收精确 developer worktree、关闭对应 Issue，再原子写入 `ISSUE_COMPLETE` 状态与交付 Evidence，供 Epic 的监控程序读取。

## 选择开发 Agent

按以下规则选择最底层 worker：

1. 所有代码开发默认使用 Codex App worker (`codex-app-development`)，创建时显式传 `model=gpt-5.6-luna`、`thinking=max`；前端、后端、全栈和任务规模不再触发自动换 worker。
2. Issue task 负责计划：先给出分步实现计划、范围/非目标、文件或模块边界、验收矩阵、Red 门禁与风险复测，再把开发交给 Codex worker。
3. 纯图片、视频、声音等素材生成仍走相应媒体技能。
4. 用户在当前任务明确指定 Claude Code、Grok、Gemini 或 Codex CLI 时遵从指定，只替换最底层 worker；计划、实现与验收职责仍保持分离。

当同一执行框架支持多个底座模型，需要按知识工作、工程、企业自动化、吞吐、成本或私有部署进行模型路由时，读取 [生产模型路由参考](references/production-model-routing.md)。它只用于模型候选、升级和验收，不覆盖用户明确指定、已有长会话粘性、项目固定模型或本 Skill 已规定的状态/Review 档位。

## 用 Graph Engineering 驱动交付

把需要执行和验收的工作组织为 `Spec → Epic → Issue → Agent Task → Evidence`：

- **Spec**：定义目标、边界、非目标、关键决策和最终验收，是根合同。
- **Epic**：把 Spec 切成可交付的里程碑子图，维护跨 Issue 依赖与汇总验收。
- **Issue**：作为最小可执行节点，明确 owner、范围、依赖、输出和验证；每个活跃任务必须映射一个 Issue。
- **Agent Task**：分为只读协调/验收的 Issue task 与唯一写入的 developer task，分别保存 task id、host、worktree 和 cursor，不充当新的事实源。
- **Evidence**：用累计 diff、测试、产物、Review 和远端 SHA 关闭 Issue，再自底向上关闭 Epic 与 Spec。

开始实现前先建立或更新节点与依赖边；没有 Issue 映射的任务不得进入执行。只并行没有未满足依赖的 Issue。范围或方向变化时先更新 Spec/Epic/Issue，再推动原任务；阻塞、决策和验收结论写回对应节点，不另建流水账。Epic 监控到已关闭 Issue 的 `ISSUE_COMPLETE` 后立即重新计算 ready 集合，按依赖、写入冲突、资源和优先级启动下一个 Issue，或并行启动多个互不冲突的 ready Issue。

## 默认保持轻量

1. 调用 `wait_threads` 时默认显式传 `timeoutMs: 1200000`（20 分钟）并使用紧凑快照；单任务传最近 cursor，多任务在一次有界等待中聚合。目标提前完成、需要关注或收到新用户输入时允许提前返回。
2. 正常推进时只关注阶段、最新短进展、完成或需用户注意，不重复播报不变状态。
3. 不常规读取完整历史、pane、过程输出、日志、diff、测试明细或思考过程。
4. 先推动原任务解决问题；不要因为进展慢就接管代码或另开 worker。
5. 问题关闭后立即恢复状态级监工。

## 单向下发与状态文件

- 会话消息方向固定为 `Epic → Issue → developer`，只用于初始合同、决策、继续和返工；child 不调用 `send_message_to_thread` 向父层回推状态。
- child 必须与直接父任务共享同一组绝对路径；创建时传入 Issue、验收合同、唯一绝对 `status_file`、当前阶段唯一 `handoff_file`、完成 marker 和失联阈值。不能共享文件系统时不得伪装成本地 monitor，也不把父 `thread_id` 当作回报地址。
- child 在阶段切换时原子覆盖单行状态文件，不写轮询流水账。developer 使用 `*_PLANNING`、`*_RED_READY`、`*_IMPLEMENTING`、`*_BLOCKED_USER_DECISION`、`*_SCOPE_DRIFT`、`*_DELIVERY_COMPLETE`、`*_ERROR`、`*_ABORTED`；Issue task 使用 `ISSUE_ACCEPTING`、`ISSUE_REVIEWING`、`ISSUE_BLOCKED_USER_DECISION`、`ISSUE_COMPLETE`、`ISSUE_ERROR`、`ISSUE_ABORTED`。
- `RED_READY`、`DELIVERY_COMPLETE` 与 `ISSUE_COMPLETE` 必须同时具备末行 marker 正确的交付文件；完成标记只表示待父层处理，不替代独立 Review。
- 父任务保存最近已处理的状态、mtime 和交付 marker。相同快照只静默等待，不重复投递；只有父层向 child 的输入需要会话消息。

## 每次下发后启动有界监控

1. 初始委托、`CONTINUE_GREEN`、用户决策或返工输入成功投递后，直接父任务立即启动且只启动一个 20 分钟监控程序；同一 child 同时不得有第二个 monitor。
2. 程序每 20 秒只读一次状态与交付末行，循环中零输出。目标交付双标记成立时退出 0；`*_BLOCKED_USER_DECISION`、`*_SCOPE_DRIFT`、`*_ERROR`、`*_ABORTED` 时立即退出 3；20 分钟内没有可动作终态则退出 124。
3. 退出 0 后父任务只读一次交付文件并立即进入对应 Review 或图谱推进；退出 3 后只恢复解决该状态所需的最小上下文；退出 124 且 child 仍稳定执行时可启动下一轮 20 分钟监控，不发送“仍在运行”。
4. 宿主若先返回运行 session，只用支持的最长等待续接同一进程；不由模型每 20 秒查询 session、状态文件、pane 或完整 task 历史。
5. 输入投递失败时不启动 monitor；先解决投递失败。监控退出后才允许对同一 child 投递下一条输入并启动新 monitor，避免重复指令与双重消费者。

## 成本与并发边界

- 不对用户可同时运行的任务数量设置硬上限；并发由依赖、写入冲突、资源和用户优先级决定。
- 无论并发多少，每条父子边只能有一个监控所有者：Issue task 监控 developer，Epic 监工只监控 Issue task；Epic、Issue task 和 CLI wrapper 不得同时轮询同一 developer 或状态文件。
- 监控程序必须由被监控目标的直接父任务启动：Issue task 监控 developer，Epic 监工只监控 Issue task。
- monitor 不得与同一目标上的 active `/goal` 自动续跑或 automation heartbeat 并存；三者只能保留一个监控所有者。本工作流默认选择上述 20 分钟本地 monitor，不再创建周期 automation。
- Codex developer 从创建起固定使用 `gpt-5.6-luna`、`thinking=max`，返工继续同一 worker，不为阶段变化切模型。Issue task 保持 `gpt-5.6-sol`：纯状态与 monitor 结果处理使用 `thinking=low`，实现计划、正式合同判断、累计 diff Review、失败诊断与 P0–P2 闭环使用 `thinking=high`；不为切 reasoning 重建 task 或丢失原会话。
- worker 交付标记只代表待 Review，不等于目标完成。Issue task 独立 Review 并确认 P0–P2 清零后，先确认 worker 停止与 monitor 退出，再完成 commit、push、远端 SHA 核验、精确 worktree 回收和 Issue 关闭，最后写入 `ISSUE_COMPLETE` 与 Evidence。Epic 的 monitor 读到后推进新的 ready Issue。

## 按路径低噪声等待

监工 Codex App task 与 CLI worker 都统一要求 child 写单行状态文件和最终交付文件。父任务下发成功后运行：

```bash
scripts/wait-for-task-delivery.zsh \
  "$STATUS_FILE" "$DELIVERY_COMPLETE_STATUS" \
  "$HANDOFF_FILE" "$DELIVERY_COMPLETE_MARKER" \
  1200
```

脚本在自身进程内每 20 秒检查一次，默认 1200 秒；循环中零输出，状态与交付末行双重完成时退出 0，可动作状态退出 3，整段超时只输出一次最后状态并退出 124。若宿主先返回运行 session，使用一次支持的最长等待续接，不要由主 Agent 查询文件。

退出 0 后只读一次交付文件并进入验收；退出 3 时处理唯一可动作状态；退出 124 且 child 仍稳定推进时可再启动一轮 20 分钟监控。每个任务使用自己的状态、交付路径和监控所有者，避免串读证据。

## 上下文与输出闸门

以下信号任一出现时，先写一份紧凑 handoff，再决定继续原 task、显式压缩或新建后继 task；不要靠反复状态消息继续堆积：

- 单次输入上下文达到约 120,000 tokens；
- 同一监工 task 已产生约 200 次模型请求；
- 本地 session JSONL 超过约 10 MB；
- 已发生两次上下文压缩且等待型内容仍持续增长。

handoff 只保留任务图、当前 owner、worktree/分支、稳定状态、最近 cursor、完成条件、阻塞、必须 Review 的证据路径和未关闭风险。完整日志、长 diff、测试输出和历史快照写到仓库外证据文件；模型上下文只接收路径、退出码、计数、摘要和支持结论的最小片段。工具输出默认先限制在 4,000–8,000 tokens，只有正式 Review 确实需要时才按文件或区段扩读。

## 只按证据逐层下钻

出现以下任一信号时才读取支持结论的最小额外证据：

- 真实阻塞或需要用户决策；
- 方向、范围、worktree 或权限边界偏离；
- 交付标记缺失、验收失败或测试证据过期；
- worker 自述与 Git、日志、产物或远端状态矛盾；
- 进入正式 Review；
- 发现 P0、P1 或 P2 风险。

下钻顺序为：紧凑状态 → 对应交付摘要 → 相关文件/日志片段 → 完整累计 diff 与调用链。不要越级拉取无关材料。

## 处理阻塞与决策

收到新的 `BLOCKED_USER_DECISION` 后才进入决策模式；正常 monitor 不读取上文。父 task 使用 high reasoning，并按顺序处理：

1. 从 Issue 合同、已确认决策、依赖边、最近相关 3–5 个 turn 和支持判断的最小代码/证据恢复上下文；先读摘要与精确片段，只有冲突时才扩读，不拉取完整历史或思考过程。
2. 把新问题规范化并生成 `decision_fingerprint`，去掉重复、已回答、被上游选择蕴含或已被新问题取代的项；按依赖顺序只保留真正阻塞推进的上游决策。
3. 可逆、在既有范围内、无安全/凭证/生产/不可逆后果，且从现有约束能得到明确推荐的事项，由 Issue task 直接采用推荐项，写回 Issue 决策记录并成功投递给原 worker，不打扰用户。
4. 产品方向、范围扩张、架构所有权、真实安全风险、凭证、生产写入、不可逆操作、显著成本或外部承诺必须交还用户。多个事项合并成一个决策包：每项只含稳定 id、推荐选项、核心理由、其他选项的关键代价、影响的 Issue/依赖和是否阻塞；先问上游关键项，从答案可推导的下游项不再单独提问。
5. memory 分开保存 `decision_fingerprint`、`prompted_decision_id` 与 `resolved_decision_id`。决策包成功呈现后进入 `AWAITING_USER_DECISION` 并静默等待，相同问题不重复发送；用户答复成功写回合同并投递给 worker 后才标记 resolved。
6. 用户答案含糊时先用既有约束推导；只有不同解释会显著改变结果时才追问一次。不要把 worker 的探索性问题、可由代码查明的事实或实现细节升级给用户。
7. 不代替 worker 写代码；监工和 Issue task 可以整理上下文、作低风险决定、核查证据、评论、要求返工和独立复测。

## 固化重要结论

只把重要方向决策、真实阻塞、里程碑和验收结论写入对应 Spec、Epic、Issue 或项目笔记。写结论、关系边、证据与下一步，不写轮询流水账，不刷屏。

## 独立验收

代码任务先由独立 Issue task 执行 Red-only 预审：

1. 启动 developer 前把每个核心不变量绑定到真实生产入口、权威 owner、可观察结果、必须失败的负例和测试。
2. 要求 developer 只修改测试及专用 fixture/support 并跑出目标性失败；生产实现保持未修改，然后发送 `RED_READY` Evidence。
3. 先用累计变更清单确认生产实现未修改，再审测试 diff、fixture/producer 来源、失败命令与退出码、精确失败断言和必要生产契约。
4. 确认测试从真实入口进入，Red 因目标行为缺失而失败；拒绝语法、类型、fixture、环境错误，恒真或条件断言，允许零次事件，以及用私有 helper 或 mock 绕过核心逻辑。
5. 不通过时只要求原 developer 修正 Red；通过后向同一 developer 发送一次明确的 `CONTINUE_GREEN`，再进入正常低噪声监控。

developer 最终交付后，仍由同一独立 Issue task 验收；Issue task 不得写或代修业务代码：

1. 对照原始合同、决策和非目标逐条核对。
2. 读取完整累计 diff 和全部变更文件，沿真实调用链检查是否生效。
3. 按风险独立复跑必要验证，核对日志时间、退出码、测试 totals、产物和远端 SHA。
4. 将问题标为 P0-P3；P0-P2 必须回到原任务关闭并重新验收。
5. 只有证据一致、P0-P2 清零、未验证项已披露时才给出通过结论。

developer 自述、其测试摘要或“命令成功”不能替代 Review。Issue task 验收通过后完成 Git 交付、worktree 回收和 Issue 关闭，再写入 `ISSUE_COMPLETE` 与 Evidence；Epic 只核实闭环、更新上层图谱并推进已解锁工作。

## Issue 交付、关闭与续跑

最终 Review 通过后由 Issue task 按顺序完成：

1. 确认 developer 已完成且不再写入，并确认 developer monitor 已退出；关闭对应 CLI/tmux 会话时遵守其精确目标清理合同。
2. 检查完整 Git 状态，只提交当前 Issue 已验收的 tracked/untracked 文件；发现来源不明或越界文件就停止关闭。
3. 默认创建当前 Issue 的提交并推送当前分支，核对本地 HEAD 与目标远端 SHA 完全一致；push 失败时保留 Issue 打开并处理失败。
4. 仅对记录的精确 developer worktree 执行非强制回收；先确认 Git 状态干净、无未提交或未跟踪文件且提交已在远端，禁止 `--force`、模糊路径或批量删除。任一条件不满足就保留 worktree 和 Issue。
5. 关闭图谱中的对应 Issue；若该节点绑定远端 Issue，也由 Issue task 按项目工具和权限关闭。
6. 原子写入唯一 `ISSUE_COMPLETE` 状态与交付文件，Evidence 至少包含 commit、remote SHA、验证摘要、worktree 回收结果和 Issue closed 状态。

Epic monitor 读到并核实 `ISSUE_COMPLETE` 后退出，更新依赖边并立即启动一个或多个已解锁且互不冲突的 ready Issue。Epic 不重复执行 commit、push、worktree 回收或 Issue 关闭。

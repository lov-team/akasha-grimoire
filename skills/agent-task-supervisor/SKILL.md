---
name: agent-task-supervisor
description: 在 Codex App 中以 Spec、Epic、Issue 和证据关系图轻量监工多个任务或外部 Agent，维护紧凑任务板；优先由子任务向父任务推送状态变化，父任务保留单一所有者的低频失联 watchdog，仅在阻塞、偏航、验收失败、证据冲突、正式 Review 或 P0-P2 风险时唤醒和逐层下钻。用户要求用 Graph Engineering 拆解、监工、协调、等待或验收多个任务，或持续推进 worker 但不代替其实现时使用。
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
| cursor | 最近已消费 cursor |
| event | 最近已消费 `event_id`、最后更新时间与失联阈值 |
| edges | `depends_on`、`blocks`、`produces`、`validates` |

用户已明确要求开发采用三层分工。Epic 监工发现 ready Issue 后先调用 `create_thread` 建立独立 Issue 负责/验收 task；Issue task 再按 `codex-app-development` 创建独立 developer。默认 developer 是新的 Codex App task/worktree；用户指定 Grok、Claude Code、Gemini 或 Codex CLI 时只替换最底层 worker。禁止 Epic 监工直接把 developer 当 Issue task，也禁止 Issue task 自己实现再自审。

Issue task 创建 developer 并确认启动稳定后，必须为自己的 thread 创建唯一 15 分钟 heartbeat 来监控 developer；Epic 监工另有自己的 heartbeat，只监控 Issue task。两个 automation 分别附着到对应父 thread，不能合并、越级或重复。

## 用 Graph Engineering 驱动交付

把需要执行和验收的工作组织为 `Spec → Epic → Issue → Agent Task → Evidence`：

- **Spec**：定义目标、边界、非目标、关键决策和最终验收，是根合同。
- **Epic**：把 Spec 切成可交付的里程碑子图，维护跨 Issue 依赖与汇总验收。
- **Issue**：作为最小可执行节点，明确 owner、范围、依赖、输出和验证；每个活跃任务必须映射一个 Issue。
- **Agent Task**：分为只读协调/验收的 Issue task 与唯一写入的 developer task，分别保存 task id、host、worktree 和 cursor，不充当新的事实源。
- **Evidence**：用累计 diff、测试、产物、Review 和远端 SHA 关闭 Issue，再自底向上关闭 Epic 与 Spec。

开始实现前先建立或更新节点与依赖边；没有 Issue 映射的任务不得进入执行。只并行没有未满足依赖的 Issue。范围或方向变化时先更新 Spec/Epic/Issue，再推动原任务；阻塞、决策和验收结论写回对应节点，不另建流水账。

## 默认保持轻量

1. 优先用宿主允许的最长等待和紧凑快照；单任务传最近 cursor，多任务在一次有界等待中聚合。
2. 正常推进时只关注阶段、最新短进展、完成或需用户注意，不重复播报不变状态。
3. 不常规读取完整历史、pane、过程输出、日志、diff、测试明细或思考过程。
4. 先推动原任务解决问题；不要因为进展慢就接管代码或另开 worker。
5. 问题关闭后立即恢复状态级监工。

## 子任务主动通知

- 通知链固定为 `developer → Issue 负责/验收 task → Epic 监工 task`；每层只汇总会解锁上层动作的状态。
- 创建或委派 child task 时传入直接父 `thread_id`、`host_id`、Issue、验收合同和通知合同。
- child 只在 `MILESTONE_READY`、`BLOCKED_USER_DECISION`、`SCOPE_DRIFT`、`DELIVERY_READY`、`COMPLETE`、`ERROR` 或 `ABORTED` 等会解锁父任务动作的状态变化时调用 `send_message_to_thread`；不发送普通 `IMPLEMENTING` 或无变化状态。
- 事件使用稳定的 `event_id=<issue>:<round>:<state>`；父任务保存 `last_event_id` 并丢弃重复消息。正文只含 child id、state、最小 evidence 和期望动作。
- 推送是主路径但不是唯一活性证据。父任务必须保留低频 watchdog，防止 child 异常死亡、漏报或通知链路中断。

## 成本与并发边界

- 不对用户可同时运行的任务数量设置硬上限；并发由依赖、写入冲突、资源和用户优先级决定。
- 无论并发多少，每条父子边只能有一个监控所有者：Issue task 监控 developer，Epic 监工只监控 Issue task；Epic、Issue task 和 CLI wrapper 不得同时轮询同一 developer 或状态文件。
- 每条边的 heartbeat 必须附着到该边直接父任务：developer watchdog 的 `targetThreadId` 是 Issue task，Issue watchdog 的 `targetThreadId` 是 Epic 监工 task。
- 启动、输入投递或异常恢复后的前两个等待窗用于确认链路稳定；进入明确的 `IMPLEMENTING` 或等价稳定状态后，结束当前持续等待 turn，改用默认 15 分钟 watchdog heartbeat。
- heartbeat 只做一次即时状态读取或 `wait_threads timeoutMs: 0` 紧凑快照，核对状态、最后更新时间、cursor 和失联阈值。状态不变时不发 commentary、不读取历史、不重新执行完整推理链；只有漏报、失联、完成、阻塞或异常才唤醒负责验收的 task。
- heartbeat 不得与同一目标上的 active `/goal` 自动续跑并存。若同一外部状态等待已重复至少三轮、没有其他可安全推进的就绪节点，且必须等待 worker 或其他外部状态变化，按 goal 合同把 goal 标为 `blocked`，确认 task 已 idle 后再启用 heartbeat；这是真实外部阻塞，不是因任务困难或耗时而暂停。未达到 blocked 条件时 Agent 无权暂停 goal，应只保留 goal 这一名监控所有者，并让新建 heartbeat 保持 `PAUSED`，避免双重唤醒。
- 已有长会话不得仅为降低监控成本临时切换模型：跨模型会失去原有 prompt cache，首轮可能比继续原模型更贵。默认保持同一个 `gpt-5.6-sol`：纯状态监工 follow-up 使用 `thinking=low`，正式合同判断、累计 diff Review、失败诊断与 P0–P2 闭环使用 `thinking=high`。向既有 task 发送监工或 Review 唤醒消息时显式携带对应 thinking override；自动续跑或 heartbeat 不能设置该参数时，保持原模型并在任务/UI 配置中优先固定监工为 low，不为切 reasoning 重建 worker 或丢失原会话。
- worker 交付标记只代表待 Review，不等于目标完成；Issue task 验收 developer 后停止 developer watchdog，Epic 监工关闭 Issue 后停止 Issue watchdog；目标取消或不再需要监控时也立即停用，避免孤儿自动化。

## 按路径低噪声等待

监工 Codex App 任务时，启动确认阶段优先一次调用 `wait_threads`，使用宿主允许的最长等待；当前 `timeoutMs` 单次最大为 `120000`。传入最近 `afterCursor`，多任务尽量在同一有界等待中聚合。连续两个 120 秒窗口状态不变且任务仍稳定执行时，不再继续同一 turn 的无限等待链，也不发送“仍在运行”类消息；先依赖 child 状态事件，并由唯一监控所有者建立默认每 15 分钟一次的 thread watchdog。watchdog 每次只取一份即时紧凑快照，状态无变化就静默结束本次检查。

用户明确要求持续监工、稍后检查、保持关注或完成后继续时，使用 Codex App heartbeat automation，而不是让主模型常驻循环。创建前检查现有 automation，优先更新同一目标的既有 heartbeat，避免重复；目标 task、检查对象、完成条件和停止条件必须写清楚。不要把 heartbeat 建成新的用户侧 task，也不要为同一 worker 创建多个 heartbeat。

监工提供单行状态文件和最终交付文件的外部 Agent 时，运行：

```bash
scripts/wait-for-task-delivery.zsh \
  "$STATUS_FILE" "$DELIVERY_COMPLETE_STATUS" \
  "$HANDOFF_FILE" "$DELIVERY_COMPLETE_MARKER" \
  240
```

脚本在自身进程内每 5 秒检查一次，默认 240 秒；循环中零输出，状态与交付末行双重完成时才输出一行并退出 0，整段超时只输出一次最后状态并退出 124。若宿主先返回运行 session，使用一次支持的最长等待续接，不要由主 Agent 高频查询 session 或文件。

退出 0 后只读一次交付文件并进入验收。退出 124 时：若尚处于启动确认阶段，可再执行一次 240 秒等待；若已经连续两个窗口保持稳定推进，则停止当前 turn 的机械等待，交给唯一 heartbeat 做低频即时检查。阻塞状态才请求决策；异常状态才做一次最小诊断。每个外部任务使用自己的状态、交付路径和监控所有者，避免串读证据。

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

- 先向原任务发送具体、可执行、范围明确的推动信息。
- 仅当选择可逆、在已批准范围内、有明确推荐，且不涉及凭证、安全边界或不可逆后果时，才可替用户采用推荐项。
- 产品方向、范围扩张、真实安全风险、凭证、生产写入和不可逆操作必须交还用户决定。
- 不代替 worker 写代码；监工可以核查、评论、要求返工和独立复测。

## 固化重要结论

只把重要方向决策、真实阻塞、里程碑和验收结论写入对应 Spec、Epic、Issue 或项目笔记。写结论、关系边、证据与下一步，不写轮询流水账，不刷屏。

## 独立验收

developer 宣称完成后，由独立 Issue task 验收；Issue task 不得写或代修业务代码：

1. 对照原始合同、决策和非目标逐条核对。
2. 读取完整累计 diff 和全部变更文件，沿真实调用链检查是否生效。
3. 按风险独立复跑必要验证，核对日志时间、退出码、测试 totals、产物和远端 SHA。
4. 将问题标为 P0-P3；P0-P2 必须回到原任务关闭并重新验收。
5. 只有证据一致、P0-P2 清零、未验证项已披露时才给出通过结论。

developer 自述、其测试摘要或“命令成功”不能替代 Review。Issue task 验收通过后把 Evidence 推给 Epic 监工，由 Epic 层关闭图谱并汇报任务状态、未验证项、Git/远端事实和已解锁后续工作。

---
name: codex-app-development
description: 由独立的 Codex App Issue 负责/验收任务创建隔离开发任务与 worktree，审核 Red 与最终实现，默认由 Issue task 完成 commit、push、worktree 回收和 Issue 关闭，再通知 Epic 推进后续 ready Issue。用户要求用 Codex App 子会话开发、让另一个 Codex 实现、为 Issue 单独开开发会话、隔离实现与 Review 上下文或让父子任务互相通信时使用；用户指定 Grok、Claude Code、Gemini 或 Codex CLI 时保留相同三层职责，只替换最底层 worker。
---

# Codex App 独立开发任务

把调用本 Skill 的父任务限定为 **Issue 负责/验收任务**，把新建 child 限定为 **实现 worker**。父任务不得写业务代码或替 child 修复；child 不得给自己的交付做最终验收。创建前完整读取 [references/app-task-contract.md](references/app-task-contract.md)。

## 保持三层职责

默认拓扑固定为：

```text
Epic 监工 App → Issue 负责/验收 App → Codex App 开发任务
```

- Epic 监工发现 ready Issue 后先创建独立 Issue 任务，不直接创建开发 worker。
- Issue 任务解释需求、确认范围和用户决策，再创建新的开发 task/worktree；Issue 任务对测试和业务文件保持只读验收视角。
- 开发任务是该 Issue 的唯一写入者，负责先交付 Red 测试、获批后实现、测试和返工。
- Issue 任务不写业务代码，但默认负责验收后的 Git 提交与推送、精确 worktree 回收和 Issue 关闭。
- 复杂需求使用新的 Codex App developer/worktree。跨模块、跨状态 owner、状态机、协议、事务、恢复、并发、复杂数据流、架构歧义，以及涉及新交互状态、跨组件协作、路由/API、设计系统或多页面重构的 UI 都归入复杂需求。
- 小需求默认可改用 `grok-cli-development`：范围明确、单模块或单一状态 owner、不超过 5 个文件和 300 行、核心不变量不超过 3 个，且不涉及协议/schema、迁移、事务、恢复、并发、安全边界或架构决策。
- 简单网页/UI 修改也可用 Grok：只调整现有页面或组件的文案、颜色、间距、尺寸、局部布局、简单样式或轻量展示逻辑，不新增跨组件状态、路由、API 数据流、复杂表单、权限、拖拽、复杂动效或系统性响应式改造，并能执行截图或主路径视觉验证。
- 超出任一小需求边界即使用 Codex App developer。用户明确指定 Claude Code、Gemini 或 Codex CLI/TUI 时分别使用对应技能，只替换最底层 worker，不合并 Issue 与开发职责。

## 创建隔离开发任务

Codex App 路径先用 `list_projects` 取得 project id 和 `isGitRepository`，再用 `create_thread` 创建干净 task；Git 项目必须使用独立 worktree。不要用 `fork_thread` 复制 Issue 任务历史，只传最小实现合同。仅当实现确实依赖已批准的未提交基线时才使用 `startingState: working-tree`。

创建前由 Issue 任务确定目标、验收条件、非目标、允许/禁止路径、依赖、验证门禁、Git 交付策略及自己的 `thread_id`/`host_id`。默认授权 Issue task 在验收后 commit 并 push 当前 Issue 分支；PR、合并、强推、发布或生产写入仍需项目规则或用户明确授权。创建后保存 developer `thread_id`、`host_id`、精确 worktree 和 cursor；返回 `clientThreadId` 时等待 setup 完成并解析真实 task，不能把它传给要求 `thread_id` 的工具。开发 prompt 必须要求：

1. 先读项目 `AGENTS.md`、相关代码和 Git 现场，再计划并按 Red → Green → Refactor 推进；不得派生新的写入 worker。
2. 核对并在交付中报告唯一绝对 worktree、base SHA 和 Git 状态，不在 Issue task checkout 或其他 worktree 写入。
3. 只在会解锁 Issue 任务动作的状态变化时调用 `send_message_to_thread`，不推送普通 `IMPLEMENTING`、思考过程或无变化状态。
4. 默认先只修改测试及专用 fixture/support 并跑出真实 Red，向 Issue task 发送 `RED_READY` 后暂停；未收到 `CONTINUE_GREEN` 前不得修改生产实现。
5. Red Evidence 包含测试 diff、fixture/producer 来源、完整命令、退出码、精确失败断言和短日志路径；最终交付再包含 base SHA、累计 diff、全部变更文件、需求映射、验证证据、未验证项和风险。
6. developer 不执行最终 commit、push、PR 或合并，由 Issue task 在验收通过后统一完成 Git 交付。

创建 Codex App developer 时，用户没有明确指定模型或 thinking 就省略覆盖，沿用其 App 默认配置。Issue 任务的纯状态处理和 watchdog 使用 `gpt-5.6-sol low`，正式 Review、失败诊断和 P0–P2 闭环使用同一模型的 `high`。不要为切 reasoning 更换模型或重建会话。

## 由 Issue 会话创建定时任务

developer 启动并在前两个有界等待窗确认链路稳定后，Issue 负责/验收任务必须调用 `automation_update` 为自己创建或更新唯一 heartbeat，不能要求 Epic 监工代建 developer watchdog：

- 名称包含 Issue id 和 developer 标识；`targetThreadId` 指向 Issue 负责/验收任务自身，周期为每 15 分钟。
- App developer 每次只调用一次 `wait_threads(timeoutMs: 0)` 紧凑快照；CLI developer 每次只读一次状态/交付文件。
- prompt 固定 developer id/host 或状态文件、最近 cursor、`last_event_id`、失联阈值、完成条件和停止条件。
- 状态不变时静默；阻塞、偏航、交付、异常或失联才唤醒 Issue 任务。普通状态用 sol low，Review、诊断和 P0–P2 用 sol high。
- 创建前检查现有 automation，优先更新同一 Issue/developer 的 heartbeat；禁止重复 heartbeat 或与 Issue task 的 active goal 持续等待并存。

## Red-only 预审

Issue task 在创建 developer 前先建立验收矩阵，把每个核心不变量绑定到真实生产入口、权威 owner、可观察结果、必须失败的负例和测试。功能、缺陷、跨模块状态、协议、事务、恢复或复杂 UI 代码默认启用 Red 预审；纯文档、纯视觉、格式修改或已有精确失败用例的极小修复可以豁免，但必须在合同中写明理由。

收到 `RED_READY` 后，Issue task 使用 high reasoning，先用累计变更清单确认生产实现未修改，再读取测试 diff、fixture/producer 来源、Red 日志相关片段和必要生产契约，确认：

- 测试从矩阵声明的真实入口进入，核心行为没有被 mock 或私有 helper 绕过；
- Red 因目标行为缺失失败，不是类型、语法、fixture、解析或环境错误；
- 事件或状态确实发生且有非零或精确断言；
- 负例验证拒绝、清理、回滚或未应用结果，不靠提前返回自证。

不通过时只把测试问题发回同一 developer 修正，不允许提前实现。通过后向同一 developer 发送一次 `CONTINUE_GREEN`，要求继续 Green → Refactor；Red 预审不是最终验收，交付后仍必须审完整累计 diff。

## 推送优先，watchdog 兜底

developer 主动把 `RED_READY`、`MILESTONE_READY`、`BLOCKED_USER_DECISION`、`SCOPE_DRIFT`、`DELIVERY_READY`、`ERROR` 或 `ABORTED` 推送给 Issue 任务。worker 的最高交付状态是 `DELIVERY_READY`；只有 Issue task 完成 Git 交付、worktree 回收和 Issue 关闭后才向 Epic 发送 `COMPLETE`。Issue 任务按 `event_id` 去重；普通执行进度和 Red 预审不越级转发。

Issue 任务通过上述 heartbeat 为 developer 保留唯一的 15 分钟 watchdog，只检查状态、最后更新时间和 cursor。Epic 监工另有自己的 15 分钟 watchdog，只监控 Issue 任务，不越级轮询 developer。正常活跃时静默；`failed`、`notLoaded`、异常退出或超过失联阈值时才做最小诊断。

`DELIVERY_READY` 或 worker 完成标记只代表待 Review。Issue 任务必须独立 Review 完整 diff；确认 P0–P2 清零后先确认 worker 停止并调用 `automation_update(mode="delete")` 删除 developer watchdog，再完成 Git 交付、安全回收精确 worktree并关闭 Issue。Epic 收到 `COMPLETE` 后删除对应 Issue watchdog并启动新的 ready Issue；任务取消或确定不再受监控时也直接删除，不保留暂停的孤儿 automation。

## 独立验收和原任务返工

收到 `DELIVERY_READY` 后，Issue 任务用 `gpt-5.6-sol high` 亲自读取 developer worktree 的完整累计 diff、全部变更文件和真实调用链，并按风险复跑必要验证。不得只依据 developer 的摘要、测试或完成消息，也不得直接修改业务文件。

问题分为 P0–P3。P0–P2 必须发回同一个 developer task 或同一 CLI 会话返工，附具体证据、验收条件和禁止范围；返工后重新完整 Review。

需求证据齐全、P0–P2 清零、独立验证通过且未验证项披露后，Issue task 默认按顺序完成：确认 worker 停止、删除 developer watchdog、只提交已验收范围、push 当前 Issue 分支、核对本地 HEAD 与远端 SHA、非强制回收记录的精确 developer worktree、关闭对应 Issue，再向 Epic 发送 `COMPLETE`。回收前必须确认 worktree 干净、无未跟踪文件且提交已在远端；任何一步失败都保留 worktree 和 Issue，不得上报完成。默认授权不包含 PR、合并、强推、发布或生产写入。

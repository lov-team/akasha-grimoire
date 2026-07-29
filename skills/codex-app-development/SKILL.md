---
name: codex-app-development
description: 在 Codex App 中把开发工作委派给独立子任务与隔离 worktree，通过父子 task 双向事件通知、低频失联 watchdog、同一子任务返工和父任务独立 diff Review 完成交付。用户要求用 Codex App 子会话/子任务开发、让另一个 Codex 实现、把 Codex CLI worker 改为 App task、隔离上下文或让父子任务互相通信时使用；明确要求 Codex CLI、Terminal 或 tmux 时改用 codex-cli-development。
---

# Codex App 子任务开发

把 Codex App 子任务当作实现 worker；父任务负责需求合同、用户决策、完整 diff Review、风险复测和最终集成。创建前完整读取 [references/app-task-contract.md](references/app-task-contract.md)。

## 选择 App 任务

- 只有用户明确要求新任务、子会话、另一个 Codex 或委派开发时才创建 App task。
- 默认用 `create_thread` 创建干净的独立 task；项目是 Git 仓库时使用隔离 worktree。先调用 `list_projects` 取得 project id 和 `isGitRepository`。
- 不用 `fork_thread` 复制父任务长历史；只把最小实现合同传给子任务。仅当任务确实依赖当前未提交改动且用户已要求从该状态开始时，才选择 `startingState: working-tree`。
- 用户明确要求 Codex CLI、可见 Terminal 或 tmux 时使用 `codex-cli-development`，不要悄悄改成 App task。

## 建立父子合同

创建前由父任务确定目标、验收条件、非目标、允许/禁止路径、依赖、验证门禁、Git 权限、父 `thread_id`/`host_id` 和 Issue 节点。创建后由父任务保存返回的 child `thread_id`、`host_id` 和 cursor；返回 `clientThreadId` 时等待 setup 完成并解析真实 task，不能把它传给要求 `thread_id` 的工具。prompt 必须要求子任务：

1. 先读项目 `AGENTS.md`、相关代码和 Git 现场，再计划并实现；不得派生新的写入 worker。
2. 核对并在交付中报告自己的唯一绝对 worktree、base SHA 和 Git 状态，不在父任务 checkout 或其他 worktree 写入。
3. 只在状态变化时按参考合同调用 `send_message_to_thread` 通知父任务，不推送普通 `IMPLEMENTING`、思考过程或无变化状态。
4. 交付时提供 base SHA、精确 worktree、累计 diff、变更文件、需求映射、验证证据、未验证项、风险和 Git 状态；不得自行扩大提交、推送、生产写入或不可逆操作权限。

默认保持 `gpt-5.6-sol`。实现与复杂判断使用 `high`；纯状态更新和 watchdog 使用 `low`。不要为了切 reasoning 新建任务或更换模型。

## 推送优先，watchdog 兜底

子任务用事件消息主动唤醒父任务，父任务按 `event_id` 去重并更新任务板。`MILESTONE_READY`、`BLOCKED_USER_DECISION`、`SCOPE_DRIFT`、`DELIVERY_READY`、`COMPLETE`、`ERROR` 或 `ABORTED` 等会解锁父任务动作的状态变化必须推送；普通执行进度不推送。

父任务仍为每个 child 保留唯一的低频 watchdog，因为 child 可能异常死亡或漏报。稳定执行后默认每 15 分钟用一次 `wait_threads(timeoutMs: 0)` 或等价紧凑快照，只检查状态、最后更新时间和 cursor：

- 正常活跃且无新事件时静默结束；不读完整历史、终端、diff 或测试输出。
- `failed`、`notLoaded`、异常退出或超过合同中的失联阈值时，才用 `gpt-5.6-sol high` 做一次最小诊断。
- 同一 child 不得同时存在多个 heartbeat，也不得让 heartbeat 与另一个持续轮询 owner 并存。
- `DELIVERY_READY` 或 worker 完成标记只代表待 Review；父任务独立验收通过、任务取消或不再受监控时才立即停用 watchdog。

## 独立验收和原任务返工

收到 `DELIVERY_READY` 后，父任务切换为 `gpt-5.6-sol high`，亲自读取 child worktree 的完整累计 diff 和全部变更文件，沿真实调用链检查，并按风险复跑必要验证。不得只依据 child 的摘要、测试结果或完成消息。

问题分为 P0–P3。P0–P2 必须通过 `send_message_to_thread` 发回同一个 child task 返工，附具体文件、证据、验收条件和禁止范围；返工后重新完整 Review。仅在需求证据齐全、P0–P2 清零、独立验证通过且未验证项披露后，由父任务记录 `COMPLETE` 并执行用户已授权的集成、提交或推送。

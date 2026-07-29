---
name: codex-app-development
description: 由独立的 Codex App Issue 负责/验收任务再创建隔离的 Codex App 开发任务与 worktree，强制分离实现和验收视角，并通过双向事件、同一开发任务返工和 15 分钟失联 watchdog 完成交付。用户要求用 Codex App 子会话开发、让另一个 Codex 实现、为 Issue 单独开开发会话、隔离实现与 Review 上下文或让父子任务互相通信时使用；用户指定 Grok、Claude Code、Gemini 或 Codex CLI 时保留相同三层职责，只替换最底层 worker。
---

# Codex App 独立开发任务

把调用本 Skill 的父任务限定为 **Issue 负责/验收任务**，把新建 child 限定为 **实现 worker**。父任务不得写业务代码或替 child 修复；child 不得给自己的交付做最终验收。创建前完整读取 [references/app-task-contract.md](references/app-task-contract.md)。

## 保持三层职责

默认拓扑固定为：

```text
Epic 监工 App → Issue 负责/验收 App → Codex App 开发任务
```

- Epic 监工发现 ready Issue 后先创建独立 Issue 任务，不直接创建开发 worker。
- Issue 任务解释需求、确认范围和用户决策，再创建新的开发 task/worktree；Issue 任务自身保持只读验收视角。
- 开发任务是该 Issue 的唯一写入者，负责计划、实现、测试和返工。
- 用户指定 Grok、Claude Code、Gemini 或 Codex CLI/TUI 时，Issue 任务分别使用 `grok-cli-development`、`claude-code-cli-development`、`gemini-cli-development` 或 `codex-cli-development`；只替换最底层 worker，不合并 Issue 与开发职责。

## 创建隔离开发任务

Codex App 路径先用 `list_projects` 取得 project id 和 `isGitRepository`，再用 `create_thread` 创建干净 task；Git 项目必须使用独立 worktree。不要用 `fork_thread` 复制 Issue 任务历史，只传最小实现合同。仅当实现确实依赖已批准的未提交基线时才使用 `startingState: working-tree`。

创建前由 Issue 任务确定目标、验收条件、非目标、允许/禁止路径、依赖、验证门禁、Git 权限及自己的 `thread_id`/`host_id`。创建后保存 developer `thread_id`、`host_id` 和 cursor；返回 `clientThreadId` 时等待 setup 完成并解析真实 task，不能把它传给要求 `thread_id` 的工具。开发 prompt 必须要求：

1. 先读项目 `AGENTS.md`、相关代码和 Git 现场，再计划并实现；不得派生新的写入 worker。
2. 核对并在交付中报告唯一绝对 worktree、base SHA 和 Git 状态，不在 Issue task checkout 或其他 worktree 写入。
3. 只在会解锁 Issue 任务动作的状态变化时调用 `send_message_to_thread`，不推送普通 `IMPLEMENTING`、思考过程或无变化状态。
4. 交付 base SHA、累计 diff、全部变更文件、需求映射、验证证据、未验证项和风险；不得自行扩大 commit、push、生产写入或不可逆操作权限。

创建 Codex App developer 时，用户没有明确指定模型或 thinking 就省略覆盖，沿用其 App 默认配置。Issue 任务的纯状态处理和 watchdog 使用 `gpt-5.6-sol low`，正式 Review、失败诊断和 P0–P2 闭环使用同一模型的 `high`。不要为切 reasoning 更换模型或重建会话。

## 由 Issue 会话创建定时任务

developer 启动并在前两个有界等待窗确认链路稳定后，Issue 负责/验收任务必须调用 `automation_update` 为自己创建或更新唯一 heartbeat，不能要求 Epic 监工代建 developer watchdog：

- 名称包含 Issue id 和 developer 标识；`targetThreadId` 指向 Issue 负责/验收任务自身，周期为每 15 分钟。
- App developer 每次只调用一次 `wait_threads(timeoutMs: 0)` 紧凑快照；CLI developer 每次只读一次状态/交付文件。
- prompt 固定 developer id/host 或状态文件、最近 cursor、`last_event_id`、失联阈值、完成条件和停止条件。
- 状态不变时静默；阻塞、偏航、交付、异常或失联才唤醒 Issue 任务。普通状态用 sol low，Review、诊断和 P0–P2 用 sol high。
- 创建前检查现有 automation，优先更新同一 Issue/developer 的 heartbeat；禁止重复 heartbeat 或与 Issue task 的 active goal 持续等待并存。

## 推送优先，watchdog 兜底

developer 主动把 `MILESTONE_READY`、`BLOCKED_USER_DECISION`、`SCOPE_DRIFT`、`DELIVERY_READY`、`COMPLETE`、`ERROR` 或 `ABORTED` 推送给 Issue 任务。Issue 任务按 `event_id` 去重，并把需要 Epic 层动作的状态再汇总推送给 Epic 监工；普通执行进度不逐层转发。

Issue 任务通过上述 heartbeat 为 developer 保留唯一的 15 分钟 watchdog，只检查状态、最后更新时间和 cursor。Epic 监工另有自己的 15 分钟 watchdog，只监控 Issue 任务，不越级轮询 developer。正常活跃时静默；`failed`、`notLoaded`、异常退出或超过失联阈值时才做最小诊断。

`DELIVERY_READY` 或 worker 完成标记只代表待 Review。Issue 任务必须独立 Review 完整 diff；确认 P0–P2 清零后调用 `automation_update(mode="delete")` 删除 developer watchdog。Epic 确认 Issue 已合并并关闭后，再删除对应 Issue watchdog；任务取消或确定不再受监控时也直接删除，不保留暂停的孤儿 automation。

## 独立验收和原任务返工

收到 `DELIVERY_READY` 后，Issue 任务用 `gpt-5.6-sol high` 亲自读取 developer worktree 的完整累计 diff、全部变更文件和真实调用链，并按风险复跑必要验证。不得只依据 developer 的摘要、测试或完成消息，也不得直接修改业务文件。

问题分为 P0–P3。P0–P2 必须发回同一个 developer task 或同一 CLI 会话返工，附具体证据、验收条件和禁止范围；返工后重新完整 Review。仅在需求证据齐全、P0–P2 清零、独立验证通过且未验证项披露后，Issue 任务才向 Epic 监工发送 `COMPLETE` Evidence，并执行用户已授权的集成、提交或推送。

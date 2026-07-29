# 三层开发与验收合同

## 角色与写入边界

| 角色 | 职责 | 写入权限 |
| --- | --- | --- |
| Epic 监工 App | 找 ready Issue、维护依赖、接收 Issue Evidence | 不写 Issue 业务代码 |
| Issue 负责/验收 App | 解释合同、创建 worker、独立 Review、P0–P2 闭环 | 不写或代修业务代码 |
| Developer worker | 在唯一隔离现场中实现、测试、返工 | 唯一业务代码写入者 |

默认 Developer worker 是新的 Codex App task/worktree。用户指定 Grok、Claude Code、Gemini 或 Codex CLI 时，分别替换为对应 CLI worker；Issue 任务仍独立验收，禁止同时实现和自审。

## Developer 创建合同

Issue 任务传给 developer 的最小字段：

| 字段 | 要求 |
| --- | --- |
| `issue_parent_thread_id` / `issue_parent_host_id` | developer 主动通知的 Issue 任务 |
| `epic_supervisor_thread_id` | 仅供追踪；developer 不常规越级通知 |
| `issue` | Spec/Epic/Issue 图中的唯一执行节点 |
| `scope` / `non_goals` | 允许结果、禁止路径和不得扩大的权限 |
| `acceptance` / `validation` | 可核验条件、必跑测试和证据格式 |
| `git_policy` | 是否允许 commit、push、改分支或集成；未授权即禁止 |
| `lost_contact_threshold` | 默认 60 分钟；长任务按合同调高 |

## Developer → Issue 事件

只在状态变化时通知直接父任务：

```text
AKASHA_TASK_EVENT
event_id=<issue>:<delivery-round>:<state>
issue=<issue-id>
developer_id=<app-thread-or-cli-session>
state=<MILESTONE_READY|BLOCKED_USER_DECISION|SCOPE_DRIFT|DELIVERY_READY|COMPLETE|ERROR|ABORTED>
evidence=<absolute-path-or-compact-summary>
action=<expected-issue-parent-action>
```

- 同一轮同一状态的 `event_id` 保持稳定；Issue 任务保存 `last_event_id` 并丢弃重复消息。
- `MILESTONE_READY` 只用于依赖已解锁或 Issue 任务可立即推进的里程碑；禁止普通 `IMPLEMENTING`、“仍在运行”、思考过程、长日志或完整 diff。
- `DELIVERY_READY` 指向精确 developer worktree/会话和证据；Issue 任务独立读取事实。
- App developer 用 `send_message_to_thread` 主动通知；CLI worker 按对应 Skill 的状态/交付合同，由 Issue 任务的唯一 watchdog 接收。

## Issue → Epic 事件

Issue 任务只向 Epic 监工汇总需要跨 Issue 协调、用户决策或图谱关闭的事件，包含 Issue task id、developer id、Review 结论和 Evidence。普通 developer 状态不越级转发。

Issue 任务每 15 分钟对 developer 做一次紧凑 watchdog；Epic 监工每 15 分钟只对 Issue 任务做 watchdog。每条父子边只有一个监控 owner，不允许 Epic 监工和 Issue 任务同时轮询 developer。

Issue 任务创建的 heartbeat 必须附着到自己的 `thread_id`，而不是 Epic 监工 thread；它只监控当前 developer。Epic 监工的 heartbeat 另行附着到 Epic thread，只监控 Issue task。两者名称、target、cursor、event id 和停止条件分别记录，不能共用一个 automation 冒充两条边。

P0–P2 必须由 Issue 任务发回原 developer task 或同一 CLI 会话，返工后由 Issue 任务重新完整验收。Issue 验收通过后停止 developer watchdog 并向 Epic 发送 `COMPLETE`；Epic 关闭 Issue 后停止 Issue watchdog。

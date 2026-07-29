# Codex App 父子任务合同

## 创建合同

父任务传给 child 的最小字段：

| 字段 | 要求 |
| --- | --- |
| `parent_thread_id` / `parent_host_id` | 子任务主动通知的目标 |
| `issue` | Spec/Epic/Issue 图中的唯一执行节点 |
| `scope` / `non_goals` | 允许结果、禁止路径和不得扩大的权限 |
| `acceptance` | 可逐条核验的功能与质量条件 |
| `validation` | 必跑测试、风险验证和证据格式 |
| `git_policy` | 是否允许 commit、push、改分支或集成；未授权即禁止 |
| `lost_contact_threshold` | 默认 60 分钟；长任务按合同调高 |

## 通知事件

只在状态变化时调用 `send_message_to_thread`，目标为父 `thread_id` 和 `host_id`：

```text
AKASHA_TASK_EVENT
event_id=<issue>:<delivery-round>:<state>
issue=<issue-id>
child_thread_id=<thread-id>
state=<MILESTONE_READY|BLOCKED_USER_DECISION|SCOPE_DRIFT|DELIVERY_READY|COMPLETE|ERROR|ABORTED>
evidence=<absolute-path-or-compact-summary>
action=<expected-parent-action>
```

- `event_id` 在同一轮同一状态下稳定不变；父任务保存 `last_event_id` 并丢弃重复消息。
- `MILESTONE_READY` 只用于依赖已解锁或父任务可立即推进的里程碑，不发送普通 `IMPLEMENTING`、周期性“仍在运行”、思考过程、长日志或完整 diff。
- `DELIVERY_READY` 的 `evidence` 指向精确 worktree 和交付证据；父任务收到后独立读取事实。
- 阻塞、偏航、待 Review 和异常通知用 `model=gpt-5.6-sol, thinking=high` 唤醒父任务；纯状态恢复或任务板同步才用 `thinking=low`。

## 父任务响应

父任务用同一事件格式或紧凑返工合同回复 child；P0–P2 返工必须用 `send_message_to_thread` 发送到原 `child_thread_id`，并使用 `gpt-5.6-sol high`。子任务不得为返工另建 task。

父任务每 30 分钟执行一次紧凑 watchdog；只有 child 超过 `lost_contact_threshold`、状态失败或 cursor/状态事实冲突时才下钻。父任务验收通过后停止 watchdog，并在 Issue Evidence 中记录 diff、独立测试和集成结果。

# 三层开发与验收合同

## 角色与写入边界

| 角色 | 职责 | 写入权限 |
| --- | --- | --- |
| Epic 监工 App | 找 ready Issue、维护依赖、接收关闭 Evidence、启动后续 ready Issue | 不写 Issue 业务代码 |
| Issue 负责/验收 App | 解释合同、审核 Red 与最终实现、Git 交付、回收 worktree、关闭 Issue | 不写或代修测试与业务代码；可写 Git 元数据 |
| Developer worker | 在唯一隔离现场中先交付 Red，获批后实现、测试、返工 | 唯一代码写入者 |

复杂需求默认使用新的 Codex App task/worktree。单模块或单一状态 owner、不超过 5 个文件和 300 行、核心不变量不超过 3 个，且不涉及协议/schema、迁移、事务、恢复、并发、安全边界或架构决策的小需求可使用 Grok CLI。简单网页/UI 修改也可用 Grok，但只能局部调整现有页面或组件，不能新增跨组件状态、路由、API 数据流、复杂表单、权限、拖拽、复杂动效或系统性响应式改造，并必须做视觉验证。超出任一条件就使用 Codex App developer。Issue 任务始终独立验收，禁止同时实现和自审。

## Developer 创建合同

Issue 任务传给 developer 的最小字段：

| 字段 | 要求 |
| --- | --- |
| `issue_parent_thread_id` / `issue_parent_host_id` | developer 主动通知的 Issue 任务 |
| `epic_supervisor_thread_id` | 仅供追踪；developer 不常规越级通知 |
| `issue` | Spec/Epic/Issue 图中的唯一执行节点 |
| `scope` / `non_goals` | 允许结果、禁止路径和不得扩大的权限 |
| `acceptance_matrix` | 每个不变量对应的真实入口、权威 owner、可观察结果、负例和测试 |
| `validation` | 必跑测试、Red-only 预审规则、全量升级条件和证据格式 |
| `git_policy` | 默认由 Issue task commit 并 push 当前 Issue 分支；PR、合并、强推、发布和生产写入需另行授权 |
| `lost_contact_threshold` | 默认 60 分钟；长任务按合同调高 |

## Developer → Issue 事件

只在状态变化时通知直接父任务：

```text
AKASHA_TASK_EVENT
event_id=<issue>:<delivery-round>:<state>
issue=<issue-id>
developer_id=<app-thread-or-cli-session>
state=<RED_READY|MILESTONE_READY|BLOCKED_USER_DECISION|SCOPE_DRIFT|DELIVERY_READY|ERROR|ABORTED>
evidence=<absolute-path-or-compact-summary>
action=<expected-issue-parent-action>
```

- 同一轮同一状态的 `event_id` 保持稳定；Issue 任务保存 `last_event_id` 并丢弃重复消息。
- `RED_READY` 只在生产实现未修改、测试已从真实入口跑出目标性失败后发送；Evidence 指向累计变更清单、测试 diff、fixture 来源、命令、退出码和精确失败断言。Issue 任务先独立确认生产实现未修改，审核通过后向同一 developer 发送 `CONTINUE_GREEN`，不向 Epic 转发普通 Red 预审。
- `MILESTONE_READY` 只用于依赖已解锁或 Issue 任务可立即推进的里程碑；禁止普通 `IMPLEMENTING`、“仍在运行”、思考过程、长日志或完整 diff。
- `DELIVERY_READY` 指向精确 developer worktree/会话和证据；Issue 任务独立读取事实。
- developer 不发送 `COMPLETE`；该状态专属于 Issue → Epic，并且只能在 Git 交付、worktree 回收和 Issue 关闭全部完成后发送。
- App developer 用 `send_message_to_thread` 主动通知；CLI worker 按对应 Skill 的状态/交付合同，由 Issue 任务的唯一 watchdog 接收。

## Issue → Epic 事件

Issue 任务只向 Epic 监工汇总需要跨 Issue 协调、用户决策或已经完成关闭闭环的事件，包含 Issue task id、developer id、Review 结论和 Evidence。普通 developer 状态不越级转发。

Issue 任务每 15 分钟对 developer 做一次紧凑 watchdog；Epic 监工每 15 分钟只对 Issue 任务做 watchdog。每条父子边只有一个监控 owner，不允许 Epic 监工和 Issue 任务同时轮询 developer。

Issue 任务创建的 heartbeat 必须附着到自己的 `thread_id`，而不是 Epic 监工 thread；它只监控当前 developer。Epic 监工的 heartbeat 另行附着到 Epic thread，只监控 Issue task。两者名称、target、cursor、event id 和停止条件分别记录，不能共用一个 automation 冒充两条边。

P0–P2 必须由 Issue 任务发回原 developer task 或同一 CLI 会话，返工后由 Issue 任务重新完整验收。确认 P0–P2 清零后，Issue task 先确认 worker 停止并删除 developer watchdog，再完成 commit、push、远端 SHA 核验、精确 worktree 安全回收和 Issue 关闭，才向 Epic 发送 `COMPLETE`。Epic 核实 Evidence 后删除对应 Issue watchdog并启动新的 ready Issue。不得用长期 `PAUSED` 代替生命周期结束时的删除。

## 两道验收门

代码任务默认按 `验收矩阵 → RED_READY → Issue Red Review → CONTINUE_GREEN → DELIVERY_READY → Issue Final Review` 推进。Red Review 只审测试有效性和目标性失败；Final Review 审完整累计 diff、真实调用链和风险验证。纯文档、纯视觉、格式修改或已有精确失败用例的极小修复可以豁免第一道门，但 Issue 合同必须记录理由。

## 默认交付与续跑

Final Review 通过后按 `停止 worker → 删除 developer watchdog → commit → push → 核对 remote SHA → 非强制回收精确 worktree → 关闭 Issue → COMPLETE` 推进。worktree 必须干净、无未跟踪文件且提交已在远端；否则停止关闭并保留现场。`COMPLETE` Evidence 至少包含 commit、remote SHA、验证摘要、worktree 回收结果和 Issue closed 状态。Epic 收到后重新计算依赖图，并按写入冲突、资源和优先级启动一个或多个互不冲突的 ready Issue。

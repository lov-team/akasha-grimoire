# 两层开发与验收合同

## 角色与写入边界

| 角色 | 职责 | 写入权限 |
| --- | --- | --- |
| 监工任务 | 找 ready Issue、维护依赖、解释需求并下发合同与验收条件、独立 Review 最终实现、Git 交付、回收 worktree、关闭 Issue、启动后续 ready Issue | 不写或代修测试与业务代码，不代写实现计划；可写 Git 元数据 |
| 开发 worker（Codex App / Claude Desktop） | 在唯一隔离现场自主制定实现计划并完成开发与测试：测试先行的 Red → Green → Refactor、回归自测与返工 | 唯一代码写入者 |

所有代码开发默认统一交给 Codex App worker，并在创建时显式使用 `model=gpt-5.6-sol`。监工只下发需求合同与验收条件，按 `简单=low / 常规=medium / 复杂=high / 高风险=xhigh / 极高难=max` 选择 thinking，再把计划、开发与测试交给 worker；选择依据必须写进需求合同，信息不足默认 `medium`，不得一律使用 `max`。Claude Desktop worker 使用相同两层结构与难度档位（effort）。监工始终独立验收，禁止同时实现和自审。纯媒体生成仍走对应媒体技能；用户明确指定 CLI TUI worker 时改走对应 CLI 技能的三层分工。

## Developer 创建合同

监工传给 developer 的最小字段：

| 字段 | 要求 |
| --- | --- |
| `developer_status_file` | 仓库外唯一绝对路径；developer 阶段切换时原子覆盖单行状态 |
| `developer_handoff_file` / `completion_marker` | 终态交付路径和末行完成标记 |
| `monitor_host` | parent 与 child 必须能读写同一组绝对路径；不能共享文件系统时不得使用本地 monitor |
| `issue` | Spec/Epic/Issue 图中的唯一执行节点 |
| `acceptance_criteria` | 逐条可验证的验收条件与核心不变量；实现计划由 developer 自主制定并随交付提交 |
| `model` / `difficulty` / `thinking` | 默认 `gpt-5.6-sol`；记录难度、判定证据及对应 thinking，worker 创建后和返工期间保持不变 |
| `scope` / `non_goals` | 允许结果、禁止路径和不得扩大的权限 |
| `validation` | 必跑测试、Red 证据要求、全量升级条件和证据格式 |
| `git_policy` | 默认由监工 commit 并 push 当前 Issue 分支；PR、合并、强推、发布和生产写入需另行授权 |
| `lost_contact_threshold` | 默认 60 分钟；长任务按合同调高 |

## 会话消息与状态文件

会话消息默认只从监工到 developer，用于初始合同、决策和返工。Codex App developer 必须由 `create_thread` 创建隔离 task，不使用 `fork_thread` 或 shell/PTY session 复制父上下文；初始消息和 follow-up 只传绝对合同路径与最小指令。Codex App developer 不调用 `send_message_to_thread` 向父层报告；它只原子更新父层指定的状态文件，终态另写交付文件。父子两端都为 Claude Desktop / Claude Code 会话时，developer 可在可动作终态额外发送一条简短唤醒消息（每状态最多一条，只含状态名与文件路径），但文件仍是唯一事实源。

- developer 状态使用 `DEVELOPER_PLANNING`、`DEVELOPER_IMPLEMENTING`、`DEVELOPER_BLOCKED_USER_DECISION`、`DEVELOPER_SCOPE_DRIFT`、`DEVELOPER_DELIVERY_COMPLETE`、`DEVELOPER_ERROR`、`DEVELOPER_ABORTED`；合同显式保留 Red 门时另有 `DEVELOPER_RED_READY`。CLI worker 可保留供应商前缀，但语义必须一致。
- 默认不设 `RED_READY` 暂停门：developer 每个核心行为先写测试跑出目标性失败，再实现到 Green，Red 失败证据（命令、退出码、精确失败断言）必须保留进最终交付。监工在合同中显式保留 Red 门的高风险 Issue 除外：worker 交付 Red 后暂停，监工预审通过下发 `CONTINUE_GREEN`。
- `DELIVERY_COMPLETE` 只表示待 Final Review；监工必须独立读取完整累计 diff、调用链与验证事实。

## 20 分钟 monitor

监工每次成功下发 developer 输入后启动一个 monitor。每条父子边只有一个监控 owner。

monitor 使用 `wait-for-task-delivery.zsh`，默认 1200 秒、每 20 秒读取一次状态与交付末行。目标双标记成立时退出 0；阻塞、偏航、错误或取消时退出 3；20 分钟无可动作终态时退出 124。循环中不输出状态，不读取会话历史、pane、过程日志或中间 diff。退出 124 且 child 仍稳定执行时可启动下一轮 20 分钟 monitor，不创建周期 automation，也不发送“仍在运行”。收到 child 有效终态唤醒消息时可提前结束本轮 monitor，先核对状态/交付文件再行动。

monitor 与同目标的 active goal、automation heartbeat 互斥。宿主若返回运行 session，监工只用支持的最长等待续接同一进程。状态和 mtime 未变化时不重复投递；只有父向子的下一条指令使用会话消息。

需要使用 `wait_threads` 获取 setup 或 task 状态时，默认显式传 `timeoutMs: 1200000`（20 分钟），并为每个目标传其自己的最近 cursor。多目标调用只充当首个可动作终态的事件选择器：任一目标完成或需关注就立即处理并移出等待集合，其他目标继续运行；禁止把它实现成等待全部 worker/monitor/PID 的 barrier。常规推进不调用 `read_thread(includeOutputs=true)`，终态只读一次状态/交付文件。

新 `BLOCKED_USER_DECISION` 使用独立决策生命周期：监工只读取合同、既有决策、依赖、最近相关 3–5 个 turn 和最小证据，生成稳定 `decision_fingerprint`。范围内、可逆、无安全或不可逆影响且有明确推荐的事项直接决定并恢复 worker；必须由用户决定的事项去重、消除可推导下游项后合并成一个决策包，每项给出推荐、理由、关键代价和依赖影响。memory 保存 `prompted_decision_id` 与 `resolved_decision_id`；成功呈现后静默等待，不重复提问，直到用户答案写回合同并成功投递给 worker 才 resolved。

P0–P2 必须由监工下发给原 developer task 返工；投递前保留旧交付文件，切换到唯一返工 handoff 路径并原子重置状态，再只发送读取返工合同路径的短指令。返工后重新完整验收。确认 P0–P2 清零后，监工先确认 worker 与 monitor 停止，再完成 commit、push、远端 SHA 核验、精确 worktree 安全回收和 Issue 关闭。

## 验收门

代码任务默认按 `需求合同 → developer 自主计划 → Red → Green → Refactor → DELIVERY_COMPLETE → 监工 Final Review` 推进。Final Review 先核对实现计划与合同、diff 一致，再审完整累计 diff、真实调用链、Red 证据链和风险验证。监工在合同中显式保留 Red 门的高风险 Issue 按 `RED_READY → Red 预审 → CONTINUE_GREEN` 增加一道预审。

## 默认交付与续跑

Final Review 通过后按 `停止 worker 与 monitor → commit → push → 核对 remote SHA → 非强制回收精确 worktree → 关闭 Issue` 推进。worktree 必须干净、无未跟踪文件且提交已在远端；否则停止关闭并保留现场。关闭后监工重新计算依赖图，并按写入冲突、资源和优先级启动一个或多个互不冲突的 ready Issue。

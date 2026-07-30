# 三层开发与验收合同

## 角色与写入边界

| 角色 | 职责 | 写入权限 |
| --- | --- | --- |
| Epic 监工 App | 找 ready Issue、维护依赖、接收关闭 Evidence、启动后续 ready Issue | 不写 Issue 业务代码 |
| Issue 负责/验收 App | 解释合同、审核 Red 与最终实现、Git 交付、回收 worktree、关闭 Issue | 不写或代修测试与业务代码；可写 Git 元数据 |
| Developer worker | 在唯一隔离现场中先交付 Red，获批后实现、测试、返工 | 唯一代码写入者 |

前端开发（React/Vue/Svelte、HTML/CSS/JS/TS、组件、交互状态、表单、前端路由、响应式、可访问性、动效和前端测试）默认优先使用 Gemini CLI。边界明确的小型非前端代码（不超过 5 个文件和 300 行、核心不变量不超过 3 个，且无协议/schema、迁移、事务、恢复、并发或安全边界）可使用 Grok CLI；用户点名 Grok 或需要其内置媒体能力时也可使用。复杂后端、协议/schema、迁移、事务、恢复、并发、安全边界或架构决策默认使用 Codex App developer。全栈任务在可安全分拆时拆成前端 Issue（Gemini CLI）与后端 Issue（Codex App）；不可安全分拆时按高风险路径选择并写明理由。Issue 任务始终独立验收，禁止同时实现和自审。

## Developer 创建合同

Issue 任务传给 developer 的最小字段：

| 字段 | 要求 |
| --- | --- |
| `developer_status_file` | 仓库外唯一绝对路径；developer 阶段切换时原子覆盖单行状态 |
| `developer_handoff_file` / `completion_marker` | 当前阶段唯一交付路径和末行完成标记 |
| `monitor_host` | parent 与 child 必须能读写同一组绝对路径；不能共享文件系统时不得使用本地 monitor |
| `issue` | Spec/Epic/Issue 图中的唯一执行节点 |
| `scope` / `non_goals` | 允许结果、禁止路径和不得扩大的权限 |
| `acceptance_matrix` | 每个不变量对应的真实入口、权威 owner、可观察结果、负例和测试 |
| `validation` | 必跑测试、Red-only 预审规则、全量升级条件和证据格式 |
| `git_policy` | 默认由 Issue task commit 并 push 当前 Issue 分支；PR、合并、强推、发布和生产写入需另行授权 |
| `lost_contact_threshold` | 默认 60 分钟；长任务按合同调高 |

## 单向会话与状态文件

会话消息只允许 `Epic → Issue → developer`，用于初始合同、决策、继续和返工。Issue 与 developer 不调用 `send_message_to_thread` 向父层报告；它们只原子更新父层指定的状态文件，终态另写交付文件。

- developer 状态使用 `DEVELOPER_PLANNING`、`DEVELOPER_RED_READY`、`DEVELOPER_IMPLEMENTING`、`DEVELOPER_BLOCKED_USER_DECISION`、`DEVELOPER_SCOPE_DRIFT`、`DEVELOPER_DELIVERY_COMPLETE`、`DEVELOPER_ERROR`、`DEVELOPER_ABORTED`。CLI worker 可保留供应商前缀，但语义必须一致。
- `RED_READY` 只在生产实现未修改、测试已从真实入口跑出目标性失败且 Red 交付末行 marker 有效后写入。Issue 独立审核通过后向同一 developer 下发 `CONTINUE_GREEN`。
- `DELIVERY_COMPLETE` 只表示待 Final Review；Issue task 必须独立读取完整累计 diff、调用链与验证事实。
- Issue task 状态使用 `ISSUE_ACCEPTING`、`ISSUE_REVIEWING`、`ISSUE_BLOCKED_USER_DECISION`、`ISSUE_COMPLETE`、`ISSUE_ERROR`、`ISSUE_ABORTED`。只有 Git 交付、远端 SHA、worktree 回收和 Issue 关闭全部完成后才能写 `ISSUE_COMPLETE`，并同步写入末行 marker 有效的 Evidence。

## 两级 20 分钟 monitor

Issue task 每次成功下发 developer 输入后启动一个 monitor；Epic 每次成功下发 Issue 输入后也启动一个 monitor。每条父子边只有一个监控 owner，不允许 Epic 越级读取 developer 文件。

monitor 使用 `wait-for-task-delivery.zsh`，默认 1200 秒、每 20 秒读取一次状态与交付末行。目标双标记成立时退出 0；阻塞、偏航、错误或取消时退出 3；20 分钟无可动作终态时退出 124。循环中不输出状态，不读取会话历史、pane、过程日志或中间 diff。退出 124 且 child 仍稳定执行时可启动下一轮 20 分钟 monitor，不创建周期 automation，也不发送“仍在运行”。

monitor 与同目标的 active goal、automation heartbeat 互斥。宿主若返回运行 session，父任务只用支持的最长等待续接同一进程。状态和 mtime 未变化时不重复投递；只有父向子的下一条指令使用会话消息。

需要使用 `wait_threads` 获取 setup 或 task 状态时，默认显式传 `timeoutMs: 1200000`（20 分钟）；单目标同时传最近 cursor，多目标放在同一次有界等待中。目标完成、需要关注或收到新用户输入时允许提前返回。

新 `BLOCKED_USER_DECISION` 使用独立决策生命周期：父 task 只读取 Issue 合同、既有决策、依赖、最近相关 3–5 个 turn 和最小证据，生成稳定 `decision_fingerprint`。范围内、可逆、无安全或不可逆影响且有明确推荐的事项直接决定并恢复 worker；必须由用户决定的事项去重、消除可推导下游项后合并成一个决策包，每项给出推荐、理由、关键代价和依赖影响。memory 保存 `prompted_decision_id` 与 `resolved_decision_id`；成功呈现后静默等待，不重复提问，直到用户答案写回合同并成功投递给 worker才 resolved。

P0–P2 必须由 Issue 任务下发给原 developer task 或同一 CLI 会话，返工后由 Issue 任务重新完整验收。确认 P0–P2 清零后，Issue task 先确认 worker 与 monitor 停止，再完成 commit、push、远端 SHA 核验、精确 worktree 安全回收和 Issue 关闭，最后写入 `ISSUE_COMPLETE` 与 Evidence。Epic monitor 读到并核实后启动新的 ready Issue。

## 两道验收门

代码任务默认按 `验收矩阵 → RED_READY → Issue Red Review → CONTINUE_GREEN → DELIVERY_COMPLETE → Issue Final Review` 推进。Red Review 只审测试有效性和目标性失败；Final Review 审完整累计 diff、真实调用链和风险验证。纯文档、纯视觉、格式修改或已有精确失败用例的极小修复可以豁免第一道门，但 Issue 合同必须记录理由。

## 默认交付与续跑

Final Review 通过后按 `停止 worker 与 monitor → commit → push → 核对 remote SHA → 非强制回收精确 worktree → 关闭 Issue → ISSUE_COMPLETE` 推进。worktree 必须干净、无未跟踪文件且提交已在远端；否则停止关闭并保留现场。`ISSUE_COMPLETE` Evidence 至少包含 commit、remote SHA、验证摘要、worktree 回收结果和 Issue closed 状态。Epic monitor 读到后重新计算依赖图，并按写入冲突、资源和优先级启动一个或多个互不冲突的 ready Issue。

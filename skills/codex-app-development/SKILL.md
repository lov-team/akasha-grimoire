---
name: codex-app-development
description: 由监工任务下发需求合同与验收条件，再创建使用 GPT-5.6 Sol、按任务难度选择 thinking 的隔离 Codex App worker，在两层结构中由 worker 自主完成实现计划、开发与测试（测试先行的 Red → Green → Refactor 与自测），监工独立 Review 最终交付并默认完成 commit、push、worktree 回收和 Issue 关闭；并行 worker 使用最小上下文、逐任务 cursor 和先完成先验收的事件驱动流水线。用户要求用 Codex App 子会话开发、让另一个 Codex 实现、为 Issue 单独开开发会话或隔离实现与 Review 上下文时使用；用户明确指定 CLI TUI worker 时改走对应 CLI 技能的三层分工。
---

# Codex App 独立开发任务

把调用本 Skill 的父任务限定为 **监工（合同/验收）任务**，把新建 child 限定为 **计划/开发/测试 worker**。监工不得写业务代码或替 child 修复；child 不得给自己的交付做最终验收。创建前完整读取 [references/app-task-contract.md](references/app-task-contract.md)。

## 保持两层职责

默认拓扑固定为：

```text
监工任务 → Codex App 开发任务
```

- 监工发现 ready Issue 后只解释需求、确认范围和用户决策，形成需求合同（目标、范围/非目标、允许/禁止路径、验收条件、Git 策略与状态/交付文件路径），再创建新的开发 task/worktree；不制定实现计划，也不拆出独立的 Issue 负责/验收中间层。
- 开发任务默认是使用 `model=gpt-5.6-sol`、按任务难度选择 `thinking` 的 Codex worker，也是该 Issue 的唯一写入者；它先自主制定分步实现计划并自检，再独立完成开发与测试——测试先行的 Red → Green → Refactor、回归自测与返工——不需要中途暂停等待预审，实现计划随交付一并提交。
- 监工对测试和业务文件保持只读验收视角，不写业务代码，但默认负责验收后的 Git 提交与推送、精确 worktree 回收和 Issue 关闭。
- 所有代码开发默认统一使用 Codex App developer；前端、后端和全栈不再按技术栈自动切换 worker。
- 纯图片、视频、声音等素材生成仍使用对应媒体技能，不纳入代码 worker 默认路由。
- 用户明确指定 Claude Code、Grok、Gemini 或 Codex CLI/TUI 时改走对应 CLI 技能的三层分工（Epic → Issue 负责/验收 → CLI developer）；Claude Desktop worker 同样使用本两层结构，仅替换执行框架。

## 创建隔离开发任务

Codex App 路径先用 `list_projects` 取得 project id 和 `isGitRepository`，再用 `create_thread` 在与监工共享状态文件的同一 host 创建干净 task；Git 项目必须使用独立 worktree。不要用 shell/PTY session 伪装 Codex App task，也不要用 `fork_thread` 复制监工历史。初始 prompt 只传 Issue、绝对合同/状态/交付路径和必要启动指令，不嵌入父会话历史、完整 Issue 正文、长日志或 diff；worker 自行读取合同和仓库事实。仅当实现确实依赖已批准的未提交基线时才使用 `startingState: working-tree`。

创建前由监工确定目标、非目标、允许/禁止路径、依赖、逐条验收条件、验证门禁和 Git 交付策略；同时指定唯一绝对状态/交付文件与完成 marker。实现计划由 worker 制定，监工不代写。默认授权监工在验收后 commit 并 push 当前 Issue 分支；PR、合并、强推、发布或生产写入仍需项目规则或用户明确授权。创建后为每个 developer 独立保存 `thread_id`、`host_id`、最近 cursor 和精确 worktree；返回 `clientThreadId` 时等待 setup 完成并解析真实 task，不能把它传给要求 `thread_id` 的工具。开发 prompt 必须要求：

1. 先读项目 `AGENTS.md`、需求合同、相关代码和 Git 现场；自主输出分步实现计划（文件/模块边界、顺序、风险点、每个验收条件对应的测试入口）并自检，再按测试先行的 Red → Green → Refactor 推进，不重新定义范围，也不得派生新的写入 worker。
2. 核对并在交付中报告唯一绝对 worktree、base SHA 和 Git 状态，不在监工 checkout 或其他 worktree 写入。
3. 不向父会话发送消息；阶段切换时原子覆盖单行状态文件，最终交付另写交付文件和末行 marker。
4. 每个核心行为先写测试并确认目标性失败（Red），再实现到通过（Green），最后重构并跑回归；Red 失败证据（命令、退出码、精确失败断言）必须保留进交付。
5. 最终交付包含实现计划、base SHA、累计 diff、全部变更文件、需求映射、Red → Green 证据链、完整验证证据、未验证项和风险。
6. developer 不执行最终 commit、push、PR 或合并，由监工在验收通过后统一完成 Git 交付。

安全、并发、迁移、数据一致性等高风险 Issue，监工可在合同中显式保留 `DEVELOPER_RED_READY` 暂停门：worker 先只改测试并交付 Red，监工预审通过并下发 `CONTINUE_GREEN` 后才实现。默认不启用该门。

创建 Codex App developer 时固定显式传 `model: "gpt-5.6-sol"`，并在创建前依据合同选择 `thinking`：

| 难度 | `thinking` | 判定信号 |
| --- | --- | --- |
| 简单 | `low` | 纯文档/格式、机械配置、局部且确定性的单文件修改，验证路径直接 |
| 常规 | `medium` | 边界清楚的功能或缺陷，涉及少量文件与普通测试，无复杂状态或迁移 |
| 复杂 | `high` | 跨模块调用链、状态机、协议/数据模型、复杂 UI、并发或多类失败恢复 |
| 高风险 | `xhigh` | 安全边界、数据一致性、迁移/回滚、架构级改动，或复杂失败已重复出现 |
| 极高难 | `max` | 多个高风险信号叠加，且必须进行长链诊断、跨系统权衡或大范围一致性证明 |

监工必须在需求合同中记录所选难度、证据和 `thinking`，不因追求能力而一律选 `max`，也不只按文件数降档。信息不足时先按 `medium`，发现更高风险信号则在创建 worker 前升档；worker 创建后保持同一 `gpt-5.6-sol` 与 thinking，返工继续原会话。只有用户在当前任务明确指定其他 worker、模型或 thinking 时才替换默认路由。监工的纯状态与 monitor 结果处理使用低档 reasoning；正式 Review、失败诊断和 P0–P2 闭环使用 `high`，安全、并发、迁移或数据一致性 Review 使用 `xhigh`。不要为切 reasoning 更换监工模型或重建会话。

## 多 worker 事件驱动流水线

- 多个 developer 可以同时运行，但每个 Issue 必须拥有独立 task、worktree、状态/交付文件和 cursor；不得共享 shell session、状态文件或 handoff。
- 使用 `wait_threads` 时为每个目标传自己的最近 cursor，显式设置 `timeoutMs: 1200000`。多目标调用只选择首个完成或需关注的目标；任一目标返回可动作终态后，立即把它移出等待集合并进入该 Issue 的 Review、返工或 Git 交付，其他 worker 继续运行。
- 禁止把多个 monitor、session 或 PID 放入一个“等待全部结束”包装器；最终批次汇总可以等待全部，但单 Issue 交付不得被兄弟任务阻塞。
- 正常监控不调用 `read_thread(includeOutputs=true)`，也不把 worker 输出复制进监工上下文。状态文件、handoff、累计 diff 和验证日志是回收证据；只有 setup/投递故障或证据矛盾时才以 `includeOutputs=false`、最小 turn 数定点诊断。
- 决策或返工只向原 task 发送读取绝对合同路径的短指令。返工投递前保留旧交付文件，切换到唯一返工 handoff 路径，并把该 worker 状态原子重置为 implementing/reworking，避免旧终态造成误唤醒。

## 由监工启动本地监控

developer 初始合同、决策或返工成功投递后，监工立即运行 `agent-task-supervisor/scripts/wait-for-task-delivery.zsh`，默认 1200 秒、每 20 秒扫描。App developer 与 CLI developer 使用同一状态/交付文件合同，不再为这条 edge 创建 automation heartbeat：

- 同一 developer 同时只允许一个 monitor；监工是唯一监控 owner。
- 目标双标记成立时脚本退出 0，监工只读一次交付并进入完整 diff Review；阻塞、偏航、错误或取消时退出 3；20 分钟无可动作终态时退出 124。
- 退出 124 且 developer 仍稳定执行时，可再启动一轮 20 分钟 monitor，不发送“仍在运行”；失联才做一次最小进程/task 诊断。
- 宿主先返回运行 session 时，只用支持的最长等待续接该进程，不由模型每 20 秒查询文件、thread、pane 或历史。
- monitor 不与同目标的 active goal 或 heartbeat 并存；输入失败时先修复投递，不启动监控。
- `BLOCKED_USER_DECISION` 只恢复合同、既有决策、依赖和最小证据；可逆且范围内的明确推荐直接决定并下发，需要用户决定的事项去重并合并成一个决策包。
- 多 developer 的 monitor 保持逐 edge 独立；任一 monitor 返回 0/3 就立即处理该 Issue，不等待其他 monitor。不得启动 wait-all shell 聚合器。

## 单向下发，状态文件回收结果

会话消息只从监工到 developer。developer 通过状态/交付文件暴露 `BLOCKED_USER_DECISION`、`SCOPE_DRIFT`、`DELIVERY_COMPLETE`、`ERROR` 或 `ABORTED`（启用 Red 门时另有 `RED_READY`），不主动回推。

worker 完成标记只代表待 Review。监工必须独立 Review 完整 diff；确认 P0–P2 清零后先确认 worker 停止且 monitor 已退出，再完成 Git 交付、安全回收精确 worktree 并关闭 Issue。

## 独立验收和原任务返工

收到 `DELIVERY_COMPLETE` 双标记后，监工用 `gpt-5.6-sol` 及上表对应的 Review 档位（通常为 `high`，高风险为 `xhigh`）亲自读取 developer worktree 的完整累计 diff、全部变更文件和真实调用链，并按风险复跑必要验证。不得只依据 developer 的摘要、测试或完成消息，也不得直接修改业务文件。

终审必须先核对 worker 提交的实现计划与需求合同、实际 diff 一致，再核验 Red 证据链：测试从计划声明的真实入口进入，Red 因目标行为缺失失败而非语法、类型、fixture 或环境错误，事件或状态有非零或精确断言，负例验证拒绝、清理、回滚或未应用结果，核心逻辑没有被 mock 或私有 helper 绕过。

问题分为 P0–P3。P0–P2 必须发回同一个 developer task 返工，附具体证据、验收条件和禁止范围；返工后重新完整 Review。

需求证据齐全、P0–P2 清零、独立验证通过且未验证项披露后，监工默认按顺序完成：确认 worker 与 monitor 停止、只提交已验收范围、push 当前 Issue 分支、核对本地 HEAD 与远端 SHA、非强制回收记录的精确 developer worktree、关闭对应 Issue。回收前必须确认 worktree 干净、无未跟踪文件且提交已在远端；任何一步失败都保留 worktree 和 Issue。默认授权不包含 PR、合并、强推、发布或生产写入。

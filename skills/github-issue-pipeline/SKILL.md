---
name: github-issue-pipeline
description: 以 GitHub 为唯一协调媒介的异步三角色流水线：Epic Issue Creator 与用户对话生成 Epic 和 Issue 并提交 GitHub；Issue Monitor 定时扫描 ready Issue 并派发多个自主 Issue worker，worker 终点是提交 PR；PR Monitor 定时扫描 PR，对照 Issue 预期与开发质量验收，P0–P2 问题派 worker 继续开发，通过则合并并关闭 Issue。三角色互不直连、不共享会话，全部状态走 GitHub label、comment 和 PR。用户要求用 GitHub Issue/PR 流水线、定时调度、异步无人值守推进多任务开发时使用。
---

# GitHub Issue 流水线

把开发流水线拆成三个互不通讯的角色，GitHub 是唯一事实源和协调媒介：

```text
Epic Issue Creator（交互）──写──▶ GitHub Epic/Issue
Issue Monitor（定时）──读 Issue──▶ 派发 Issue worker ──▶ worker 提交 PR
PR Monitor（定时）──读 PR──▶ 验收 ──▶ 合并关闭 / 派 worker 返工
```

- 三个角色不互发会话消息、不共享状态文件、不假设对方在线；一切协调通过 Issue/PR 的 label、assignee、comment 与关联关系完成。
- 两个 monitor 走定时调度（宿主的 scheduled task / cron / automation），每次运行都是无状态的有界批处理：读 GitHub → 决策 → 动作 → 退出，不留常驻监控进程。
- 本模式与 `agent-task-supervisor` 的会话监工模式互斥使用：同一个 Issue 只能属于一种模式，不得同时被会话 monitor 和流水线 monitor 消费。
- 标签状态机、防重复调度锁、PR 合同等硬性约定见 [references/github-state-contract.md](references/github-state-contract.md)，三个角色都必须先读取。

## Epic Issue Creator（唯一交互角色）

与用户对话，把需求整理成可执行的 GitHub 图谱；不写业务代码、不派 worker、不合并 PR。

1. 用对话澄清目标、边界、非目标和关键决策，按 `Spec → Epic → Issue` 拆解；Epic 用带 `epic` label 的 Issue 承载，正文维护子 Issue 任务清单（`- [ ] #N`）。
2. 每个 Issue 必须自包含，worker 无法回来提问：目标、验收条件（逐条可验证）、范围/非目标、允许/禁止路径、依赖（`Depends on #N`）、验证门禁、难度档位（`简单/常规/复杂/高风险/极高难`，对应 worker 的 `low/medium/high/xhigh/max`）。信息不足以写出可验证验收条件时，先向用户追问，不提交半成品 Issue。
3. 用 `gh issue create` 提交；无未满足依赖的 Issue 打 `agent:ready`，有依赖的打 `agent:waiting`。高风险 Issue（安全、并发、迁移、数据一致性）额外打 `risk:high`，供 PR Monitor 提升 Review 档位。
4. 处理用户决策回流：worker 或 monitor 把问题以 `agent:blocked` + comment 抛回 Issue 后，由本角色在下次对话中呈现给用户，把答案写回 Issue comment 并恢复 `agent:ready`。
5. 范围或方向变化时先改 GitHub 上的 Epic/Issue 正文，再等 monitor 自然消费；不直接指挥 worker。

## Issue Monitor（定时派发）

每轮调度做一次有界扫描，只负责"发现可开发的 Issue 并派 worker"，不 Review、不合并。

1. 扫描 `agent:ready` 且无 `agent:working`/`agent:pr-open` 的 open Issue；核对 `Depends on #N` 引用的 Issue 均已 closed，未满足则改回 `agent:waiting` 跳过。
2. 对每个可派发 Issue 先执行认领锁：加 `agent:working` label 并 comment 记录 worker id 与派发时间；加完后重读 label 确认没有并发认领冲突（发现重复 comment 时，只保留最早认领，后到者撤销自己的派发）。
3. 按写入冲突和资源并行派发多个 worker：不同 Issue 各自独立分支与 worktree，天然无冲突；同一 Issue 永远只有一个活跃 worker。
4. worker 默认按 `codex-app-development` 的路由创建：Codex App worker、`model=gpt-5.6-sol`、按 Issue 标注的难度档位选 `thinking`；用户指定 Claude Desktop / CLI worker 时按对应技能替换执行框架。worker 合同要求见状态合同文档，核心差异：worker 自主完成实现计划、开发与测试（测试先行 Red → Green → Refactor），并且**自己 commit、push 分支、开 PR**（`Fixes #N` 关联），PR 就是交付终点；worker 不合并、不打 release。
5. worker 阻塞时不等待：worker 在 Issue 上写 `agent:blocked` + 决策 comment 后即可停止；本 monitor 下轮扫描跳过 `agent:blocked`，等 Epic Issue Creator 把用户答案写回并恢复 `agent:ready`。
6. 失联清理：`agent:working` 超过失联阈值（默认 120 分钟，Issue 可标注调高）仍无分支推送、无 PR、无新 comment 的，视为 worker 死亡；comment 记录判定证据后撤掉 `agent:working` 恢复 `agent:ready`，下轮重派。
7. 每轮扫描结束即退出；不留监控进程，不轮询单个 worker。

## PR Monitor（定时验收与合并）

每轮调度扫描 worker 提交的 open PR，是唯一有合并权的角色；不写业务代码。

1. 扫描带 `Fixes #N` 关联且 Issue 处于 `agent:pr-open` 的 open PR，跳过本轮已在处理中（`agent:rework` 刚派发未完成）的 PR。
2. 独立验收，使用高档 reasoning（`risk:high` Issue 用最高常规档）：
   - 对照 Issue 的验收条件与非目标逐条核对 PR 描述、实现计划与完整 diff；
   - 沿真实调用链确认改动生效，核验 Red → Green 证据链（测试从真实入口进入、Red 因目标行为缺失失败、断言非恒真、核心逻辑未被 mock 绕过）；
   - 核对 CI 状态、与 base 分支的冲突、越界文件和禁止路径。
   worker 的 PR 描述、测试摘要或 CI 绿灯单独都不构成通过。
3. 问题分 P0–P3。存在 P0–P2 时不合并：把逐条问题（证据、期望、禁止范围）comment 到 PR，Issue 打 `agent:rework`，派发一个 worker 在**同一分支**继续开发（合同要求先读 PR 上的 Review comment，修复后 push 更新同一 PR）；P3 记录到 PR comment 不阻塞。
4. 验收通过且 CI 绿、无冲突时合并：默认 squash merge，合并信息引用 Issue；`Fixes #N` 使 Issue 自动关闭，随后删除远端分支、勾选 Epic 清单中对应项。Epic 所有子项完成后 comment 汇总并关闭 Epic。默认授权只覆盖"合并 worker 流水线 PR 到默认分支"；改写历史、强推、release、生产写入、合并非流水线 PR 都不在授权内。
5. PR 与 Issue 预期根本性偏离（做错了方向而非质量问题）时不派返工：关闭 PR、comment 说明偏离证据、Issue 打 `agent:blocked` 交还用户。
6. 每轮扫描结束即退出。合并冲突但验收通过的 PR，派 worker 在同一分支 rebase/解冲突后下轮再验。

## 定时调度与成本

- 两个 monitor 各建一个独立的定时任务（如每 10–30 分钟一轮，按项目节奏调整；避开整点整半），prompt 必须自包含：仓库、角色（Issue Monitor 或 PR Monitor）、本技能与状态合同路径、每轮扫描上限。
- 每轮设扫描与派发上限（默认单轮最多派发 3 个 worker、验收 2 个 PR），超出的留给下轮，防止单轮爆量。
- monitor 每轮只读列表级信息（label、状态、标题）做决策，进入验收才拉取完整 diff；不读 worker 会话历史。
- 无 ready Issue / 无待验收 PR 时静默退出，不产生输出，不通知用户。
- 需要模型路由时读取 [生产模型路由参考](../agent-task-supervisor/references/production-model-routing.md)，规则与监工模式一致。

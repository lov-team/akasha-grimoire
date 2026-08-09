# GitHub 状态合同

三个角色（Epic Issue Creator、Issue Monitor、PR Monitor）与所有 Issue worker 共同遵守的硬性约定。GitHub 是唯一事实源；任何角色不得凭会话记忆或本地文件替代它。

## Label 状态机

Issue 生命周期由以下互斥的 `agent:*` label 驱动（同一时刻最多一个）：

| Label | 含义 | 谁设置 | 谁消费 |
| --- | --- | --- | --- |
| `agent:waiting` | 依赖未满足，暂不可开发 | Creator / Issue Monitor | Issue Monitor（依赖满足后改 `agent:ready`） |
| `agent:ready` | 可派发开发 | Creator / Issue Monitor / Creator（决策回写后恢复） | Issue Monitor |
| `agent:working` | 已派发 worker，开发中 | Issue Monitor | Issue Monitor（失联清理）、worker（完成后改 `agent:pr-open`） |
| `agent:pr-open` | PR 已提交，待验收 | worker | PR Monitor |
| `agent:rework` | PR 验收发现 P0–P2，返工中 | PR Monitor | PR Monitor（返工 push 后重验）、Issue Monitor（失联清理同样适用） |
| `agent:blocked` | 需要用户决策 | worker / 任一 monitor | Epic Issue Creator（呈现给用户并恢复 `agent:ready`） |

辅助 label（可叠加）：`epic`（Epic 承载 Issue）、`risk:high`（PR Monitor 用最高常规档 Review，可要求保留 Red 门证据）。

状态迁移只能由表中"谁设置"的角色执行；换状态时先撤旧 `agent:*` 再加新的，并 comment 一行迁移原因。closed Issue 不携带任何 `agent:*` label。

## 认领锁与幂等

monitor 是定时批处理，可能并发或重复运行，所有动作必须幂等：

- **认领**：Issue Monitor 派发前先加 `agent:working` 并 comment `claim: <worker-id> <ISO时间>`；随后重读 comment，若存在更早的 claim 则本次撤销（撤 label 由先到者保留）。
- **验收**：PR Monitor 处理 PR 前检查是否已有本轮未关闭的 `rework: <ISO时间>` comment；有则跳过，避免双重派发返工 worker。
- **重复扫描**：任何角色发现目标状态已是期望值时静默跳过，不重复 comment。

## Issue 正文合同（Creator 产出，worker 消费）

worker 无法向任何人提问，Issue 必须自包含：

```markdown
## 目标
<一段话说明要达成什么>

## 验收条件
- [ ] <逐条可验证，绑定真实入口与可观察结果>

## 范围与非目标
- 允许路径：<glob 或目录>
- 禁止路径：<glob 或目录>
- 非目标：<明确不做的事>

## 依赖
Depends on #N（无依赖则写"无"）

## 元数据
- 难度：简单|常规|复杂|高风险|极高难（对应 low/medium/high/xhigh/max）
- 失联阈值：默认 120 分钟
- 分支名：agent/issue-<N>
```

## Worker 合同（Issue Monitor 派发时下达）

worker 是该 Issue 的唯一写入者，在独立 worktree + `agent/issue-<N>` 分支内工作：

1. 只读 GitHub Issue 正文和其 comment 作为需求来源；先自主输出分步实现计划并自检，再按测试先行的 Red → Green → Refactor 开发与自测。
2. 交付终点是 PR：自己 commit（信息引用 `#N`）、push 分支、用 `gh pr create` 开 PR。PR 描述必须包含：`Fixes #N`、实现计划、需求映射（每条验收条件 → 实现与测试位置）、Red → Green 证据（命令、退出码、精确失败断言）、未验证项和风险。
3. 开 PR 后把 Issue label 从 `agent:working` 改为 `agent:pr-open`，然后停止；不合并、不打 tag、不写生产。
4. 遇到必须用户决策的问题：在 Issue comment 写清问题、推荐选项与代价，label 改 `agent:blocked`，然后停止；不空等。
5. 返工 worker（`agent:rework`）额外要求：先读 PR 上 PR Monitor 的逐条 Review comment，在**同一分支**修复并 push 更新同一 PR，逐条回复处理结果；不开新 PR、不重做已通过部分。
6. 不改其他 Issue 的文件、不动禁止路径、不派生新的写入 worker。

## PR Monitor 验收清单

1. PR 关联的 Issue 存在、状态为 `agent:pr-open` 或返工后待重验。
2. diff 只落在允许路径内；禁止路径零改动；无来源不明文件。
3. 每条验收条件都有对应实现与测试，需求映射与实际 diff 一致。
4. Red 证据链成立：测试从真实入口进入，Red 因目标行为缺失失败（非语法/类型/fixture/环境错误），断言非恒真且不允许零次事件，核心逻辑未被 mock 或私有 helper 绕过。
5. CI 全绿、无合并冲突、base 为默认分支。
6. `risk:high`：额外核对安全边界、迁移可回滚、数据一致性，用最高常规档 reasoning。

P0（错误/破坏）、P1（验收条件未满足）、P2（重要质量缺陷）任一存在即返工；P3（风格/建议）comment 记录不阻塞。

## 授权边界

- Issue Monitor：创建 worker、改 `agent:*` label、comment；不合并、不关 Issue、不删分支。
- PR Monitor：squash 合并流水线 PR 到默认分支、删除已合并的 `agent/issue-*` 远端分支、comment、改 label；`Fixes #N` 自动关闭 Issue。不改写历史、不强推、不 release、不合并人类或其他来源的 PR。
- worker：只在自己分支 commit/push/开 PR；不合并、不动默认分支。
- Epic Issue Creator：创建/编辑 Issue 与 Epic、写决策 comment、恢复 `agent:ready`；不派 worker、不合并。

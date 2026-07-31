# 生产模型路由参考

更新时间：2026-07-31。

本参考用于在同一 Agent 或 API 执行框架中，根据任务价值、风险、质量、延迟、成本和部署边界选择底座模型。它不是永久排行榜，也不替代项目自己的回归集。

## 目录

- [优先级与边界](#优先级与边界)
- [先定义任务合同](#先定义任务合同)
- [当前场景候选](#当前场景候选)
- [三层路由](#三层路由)
- [升级与回退](#升级与回退)
- [结果验证](#结果验证)
- [成本口径](#成本口径)
- [路由记录模板](#路由记录模板)
- [刷新规则](#刷新规则)
- [参考事实源](#参考事实源)

## 优先级与边界

按以下优先级路由，前项覆盖后项：

1. 用户在当前任务明确指定的模型、供应商或部署方式；
2. 项目合同、数据边界、地区可用性、许可证和工具兼容性；
3. 已有长会话和 prompt cache 的粘性，不只为降低单轮成本临时跨模型；
4. 不可逆动作、敏感数据、外部承诺和高损失错误的风险等级；
5. 任务所需的文件、图像、长上下文、Shell、网页、API 和结构化输出能力；
6. 质量、成功率、P95 延迟和每个成功任务总成本。

显式模型合同优先。本参考不能覆盖 `agent-task-supervisor` 已固定的状态处理、正式 Review 或失败诊断档位，也不能把“更便宜”当作中途重建稳定长会话的理由。

## 先定义任务合同

路由前至少记录：

| 字段 | 内容 |
|---|---|
| `task_class` | 知识交付、工程、SaaS 自动化、知识库客服、批处理、私有部署等 |
| `value_tier` | 失败或优质交付对应的业务价值 |
| `risk_tier` | 可逆低风险、需复核、高风险或不可逆 |
| `required_tools` | Web、Shell、文件、浏览器、数据库、第三方 API |
| `required_modalities` | 文本、图像、音频、视频、结构化文件 |
| `context_need` | 输入规模、跨文件关系和状态持续时间 |
| `quality_gate` | 可程序验证指标、rubric、人工 Review 或最终数据库状态 |
| `budget` | 最大 token、费用、墙钟时间、调用次数和重试次数 |
| `fallback` | 同档替换、升档、人工接管和回滚路径 |

没有成功判定和预算时，不通过堆叠模型调用掩盖合同缺失。

## 当前场景候选

以下候选来自截至更新时间已经覆盖新一代模型的生产型评测，包括 GDPval-AA v2、AA-Briefcase、Terminal-Bench v2.1、AutomationBench-AA 和 τ³-Banking。模型更新或目标环境不可用时，使用同角色的当前等价模型重新跑内部测试，不机械保留版本号。

| 场景 | 首选候选 | 次选或国产候选 | 路由理由 |
|---|---|---|---|
| 高价值研究、咨询、战略报告、PPT、表格 | Claude Opus 5 | Kimi K3、GPT-5.6 Sol | 优先完整交付物质量、多文件分析和呈现稳定性 |
| 高难代码、终端、运维和复杂工具任务 | GPT-5.6 Sol、Claude Opus 5 | GPT-5.6 Terra；国产优先 Kimi K3，再评估 GLM-5.2 | 优先真实环境成功率、测试和恢复能力 |
| 跨 Gmail、Sheets、CRM、工单等 SaaS 自动化 | Kimi K3 | GPT-5.6 Sol、Grok 4.5 | 优先跨应用协调、规则遵循和最终状态正确率 |
| 制度密集型知识库客服 | Kimi K3、GPT-5.6 Sol | Claude Opus 5、GLM-5.2 | 所有候选仍需外部状态验证和人工升级 |
| 高并发分类、提取、初稿和批处理 | GPT-5.6 Luna、Gemini Flash | GLM-5.2、Grok 4.5 | 优先低延迟、吞吐和每成功任务成本 |
| 国产开放权重或私有部署 | GLM-5.2 | Kimi、DeepSeek、Qwen 的当前可部署版本 | 先核对许可证、显存、量化损失和本地吞吐 |
| 独立正式 Review、复杂诊断 | 遵从上层 Skill 的固定 Review 模型和高推理档 | 无自动降档 | Review 的职责隔离和证据完整性高于调用成本 |

公共榜单只决定候选集。模型、推理档位、Agent harness、工具权限和重试预算不同，分数不可直接混算。

## 三层路由

### 快速层

用于可逆、低风险、可程序验证的批处理：分类、抽取、格式转换、初步摘要、候选生成和简单工具调用。

- 优先低延迟/低成本模型；
- 输出必须经过 schema、规则或确定性程序验证；
- 验证失败时不要反复使用同一 prompt 无限重试。

### 均衡层

用于需要跨文件推理、代码修改、数步工具调用或较高成品质量，但仍有明确验证器的任务。

- 优先 Terra、Kimi K3、GLM-5.2 等质量/成本平衡候选；
- 至少保留一条程序验证、测试、rubric 或人工抽检路径；
- 同类失败一次后先修正上下文、工具或任务拆分，再决定升档。

### 高能力层

用于高价值成品、复杂工程、长链 Agent、正式 Review 和失败代价高的诊断。

- 优先 Opus 5、GPT-5.6 Sol 或经内部测试达到同等级的当前模型；
- 推理档位由任务难度和预算决定，不默认所有请求都使用 Max；
- 高能力模型仍需独立验收，不把自信语气当作证据。

## 升级与回退

使用以下顺序处理失败：

1. **验证失败类型**：区分输入缺失、工具错误、权限错误、格式错误、能力不足和外部系统失败；
2. **先修执行合同**：能通过补充文件、缩小任务、增加确定性工具或修正 schema 解决时，不先升模型；
3. **同层至多一次有信息增量的重试**：必须改变上下文、计划、工具或失败反馈，禁止原样重放；
4. **升到高一层**：能力不足、跨文件推理失败或修复后仍未通过质量门时升档；
5. **切换专长候选**：工程、视觉、长文档或 SaaS 工作流与当前模型专长不匹配时，换角色而非只加推理；
6. **人工接管**：达到预算、出现高风险歧义、连续两层失败或无法可靠验证时停止自动执行；
7. **回滚副作用**：外部写入失败先核对最终状态和幂等键，再决定补偿或重试。

低风险任务可以自动升档；高风险、不可逆或外部承诺任务在第一次真实写入前就应进入审批，不以失败后升级代替事前控制。

## 结果验证

按生产结果验收，不按对话观感验收：

| 任务 | 权威证据 |
|---|---|
| 文档、PPT、表格 | 文件可重新打开；内容 rubric；公式、图表、引用和版式检查 |
| 代码与终端 | 真实入口、测试、退出码、日志、产物和回归验证 |
| SaaS 与企业系统 | 最终数据库/应用状态、权限、幂等、违规检查和审计日志 |
| 知识库客服 | 制度版本、引用命中、必需工具调用、最终业务状态和重复运行稳定性 |
| 高风险 Review | 独立 Reviewer、完整累计 diff、风险复测和未验证项披露 |

Agent 自述、自然语言总结、置信度或“命令成功”不构成完成证据。

## 成本口径

只比较 token 单价会鼓励错误路由。统一记录：

> 每个成功任务总成本 = 模型与推理成本 + 搜索/沙箱/工具成本 + 失败重试成本 + 人工复核与返工成本。

至少同时跟踪：

- 首次成功率与重复运行成功率；
- 每个成功任务的平均/P95 成本；
- 端到端平均/P95 耗时；
- 输出 token、工具调用次数和平均 turns；
- 需人工返工比例与返工分钟数；
- 严重错误、越权、不可回滚副作用和引用错误数。

便宜模型若造成更多重试和人工返工，可能比高价模型更贵；高价模型若把所有低风险批处理都做成深度推理，也不具备生产经济性。

## 路由记录模板

```yaml
routing_decision:
  task_class: <knowledge-work|engineering|saas|support|batch|private>
  value_tier: <low|medium|high>
  risk_tier: <reversible|review-required|high|irreversible>
  required_tools: [<tool>]
  quality_gate: <programmatic check or reviewer>
  budget:
    max_cost_usd: <number>
    max_wall_seconds: <number>
    max_attempts: <number>
  selected_tier: <fast|balanced|frontier>
  selected_model: <current model id>
  reason: <one sentence>
  fallback: <repair|same-tier-once|escalate|human>
  rollback: <command or state restoration>
```

路由记录只保留决策、边界和证据路径，不写模型思考过程。

## 刷新规则

出现以下任一变化时重新跑内部候选集：

- 主力模型或推理档位发布新版本；
- API 价格、上下文、工具支持、许可证或地区可用性变化；
- Agent harness、系统提示、沙箱或重试策略变化；
- 业务任务分布、质量门或风险等级变化；
- 线上首次成功率、P95 成本或严重错误越过阈值。

每次刷新保留固定回归集和至少一组近期失败样本。公共榜单用于发现候选，内部真实任务决定生产路由。

## 参考事实源

- [Artificial Analysis LLM Leaderboard](https://artificialanalysis.ai/leaderboards/models)
- [GDPval-AA v2](https://artificialanalysis.ai/evaluations/gdpval-aa)
- [AA-Briefcase](https://artificialanalysis.ai/evaluations/aa-briefcase)
- [Terminal-Bench v2.1](https://artificialanalysis.ai/evaluations/terminalbench-v2-1)
- [AutomationBench-AA](https://artificialanalysis.ai/evaluations/automationbench-aa)
- [τ³-Banking](https://artificialanalysis.ai/evaluations/tau3-banking)

事实源访问日期均为 2026-07-31。路由时以目标环境当前可用模型、实际价格和内部评测结果为准。

---
name: content-pipeline
description: Use when 用户想讨论、澄清或诊断中文内容想法，把文章、资料、链接或已开始的内容项目制作成小红书式图文内容包，或继续、批量生产包含研究、文案、卡片、图片与 QA 的本地交付物。
---

# 中文图文内容流水线

把一个想法推进为一个可追溯、可恢复、经过视觉检查的本地内容包。当前 Agent 负责访谈、研究、写作、编排和验收；外部生成能力只在内容合同要求时启用。

## 按阶段读取参考

- 讨论想法、冻结交付结构或判断内容类型时，读 [references/content-contract.md](references/content-contract.md)。
- 研究、保留原意、制作内容地图和终稿时，读 [references/source-and-copy.md](references/source-and-copy.md)。
- 创建、继续或验收内容包前，读 [references/package-contract.md](references/package-contract.md)。
- 选择排版路线、调研模板、生成图片或视觉 QA 时，读 [references/visual-production.md](references/visual-production.md)。
- 需要复用版式骨架时，读 [references/visual-library.md](references/visual-library.md)。
- 需要借鉴外部方法时，按需读 [references/upstream-methods.md](references/upstream-methods.md)。

## 工作流

1. 先读当前项目的 `AGENTS.md`、用户素材和已有 `manifest.md`；项目规则和用户最新明确要求优先。
2. 输入仍是模糊想法时，先整理已知信息、指出缺口并给出推荐方向。只有账号定位、内容边界、首次视觉路线、代表性样稿、付费调用或平台操作等关键决定才请求确认。
3. 正式生产前冻结内容合同：受众、核心观点、内容承诺、来源边界、内容类型、图片数量与职责、配文区块、标签、CTA、视觉方向和平台操作边界。
4. 按 [references/package-contract.md](references/package-contract.md) 从 `assets/post-package/` 创建或继续一个独立内容包；批量任务仍是一篇一目录，成功阶段不静默覆盖。
5. 先研究并建立来源到核心判断、论据、例子、结论和卡片的内容地图，再决定页数。事实、引用、观点和推断分开记录。
6. 完成标题候选、正文、可选标签与 CTA；去除空话和机械表达，但保留作者的第一人称、判断强度和论证结构。
7. 新视觉路线先调研 3—5 个同平台、同主题、同内容形式的真实样本；确认版式后重点制作封面和一张文字最密集的正文样卡，两者通过再批量生成其余页面。
8. 文字型观点、科普和商业分析卡片默认使用可复现 HTML/CSS 排版。照片、插画或其他生成素材确有必要时，**REQUIRED SUB-SKILL:** 使用 `$gpt-image-generation`；缺少凭证时使用 `$akasha-key-setup`。不在本 Skill 复制 API 或凭证实现。
9. 检查每张成品的原始尺寸和手机缩略图，完成 `qa.md`，并将 `manifest.md` 如实标记为 `ready`、`partial` 或 `blocked`。
10. 交付本地内容包的绝对路径、成品清单、QA 结论和遗留风险。停止在平台上传、保存草稿、定时发布或付费扩量之前。

## 硬规则

- 一个内容包只对应一篇帖子；不同主题、研究材料和中间产物不得混用。
- 用户最新修正替代旧合同；先同步 `brief.md`、`copy.md` 和卡片计划，再继续生产。
- 图片和配文各自承担冻结的职责；不把完整提示词、教程、许可证或风险说明自动叠进图片。
- 不编造来源、数据、体验、客户案例、截图、生成结果或平台建议。
- 默认规格为 `1080 × 1440` PNG；用户或实测参考明确给出其他规格时，以冻结合同为准。
- `ready` 只表示本地内容包完整且逐图验收通过，不表示已经发布到平台。
- 批量完成后跨内容包检查同质标题、重复 Hook 和机械复用模板，并把结果写入批次根目录的 `batch-qa.md`。

---
name: video-production
description: 把创意、文章、脚本、已有素材或参考视频组织成可追溯、可复现、可验收的完整视频生产项目，覆盖编导、镜头设计、素材搜索下载、AI 视频生成、时间线剪辑、字幕声音、多平台导出和成片 QA。用户要求制作完整视频、广告、短片、纪录片、剧情片、产品片、从脚本到成片、混合真实素材与生成素材或提升视频完成度时使用。
---

# 视频生产总编排

把视频制作视为同一个有阶段门的工程，不把“生成出若干片段”当成完成。

## 绑定当前项目

1. 读取当前目录中的 brief、脚本、镜头表、素材清单、EDL、字幕、渲染记录和 QA 报告。
2. 以最新已确认产物为事实源，只执行第一个未完成阶段；不要重做已经验收的阶段。
3. 新项目按 [references/production-contract.md](references/production-contract.md) 建立目录和交付合同。
4. 大体积媒体放在仓库外 staging；仓库保存文本工程、脚本、清单、哈希和验收记录。

## 执行生产闭环

### 1. 锁定制作合同

明确受众、平台、时长、画幅、核心信息、情绪曲线、视觉风格、声音策略、素材边界、截止条件和交付格式。未知项写入合同并给出合理默认值，不让其隐式漂移。

### 2. 完成编导包

**REQUIRED SUB-SKILL:** 使用 `$video-director` 生成或修订：

- `brief.md`
- `script.md`
- `continuity.yaml`
- `shot-list.csv`
- `storyboard.md`
- `generation-plan.json`

镜头表通过叙事、覆盖、连续性和可生成性审查后，才进入素材阶段。

### 3. 为每个镜头决定来源

按优先级选择：复用已确认素材、拍摄/录屏、检索现有素材、生成图片并运镜、直接生成视频。需要外部素材时，**REQUIRED SUB-SKILL:** 使用 `$video-source-research`；需要生成时使用当前项目已安装的专用 Skill。

- MiniMax H3、Kling 3.0 / 2.5：`$newapi-video-generation`。
- Grok：`$grok-media-generation`。
- Seedance：`$seedance-video-generation`；尾帧续拍使用 `$seedance-video-continuation`。
- Gemini Omni：`$gemini-omni-video-generation`。
- 静态视觉：`$gpt-image-generation`。
- 旁白：`$fish-audio-speech`；音乐：`$suno-music-generation`。

用户没有指定模型或供应商时，直接生成视频的默认路由严格按以下顺序选择第一个满足镜头能力的入口：

1. MiniMax H3（`$newapi-video-generation`）
2. Grok（`$grok-media-generation`）
3. Seedance 2.0（`$seedance-video-generation`）

只有当前入口不支持所需参考素材、时长、画幅或声音，入口不可用，或代表镜头经过针对性重试仍未通过验收，才降到下一顺位，并在 `generation-plan.json` 记录原因。用户明确指定模型或供应商时直接遵从，不再套用默认顺序。Kling、Gemini Omni、Seedance 尾帧续拍等专用能力仅在用户明确指定，或更高顺位入口无法满足镜头硬约束时选用。

先做一个代表镜头 smoke。确认人物、商品、场景、运动和风格可达后再批量消耗生成额度。

### 4. 组装时间线

**REQUIRED SUB-SKILL:** 使用 `$video-editing`：

1. 探测所有采用素材并生成代理。
2. 以真实旁白或 A-roll 时间戳建立粗剪。
3. 输出并审核 `edl.json`，再执行确定性渲染。
4. 完成 B-roll、字幕、音乐、音效、响度、颜色和多平台版本。

声音合同不得降级：brief/脚本要求旁白时使用项目指定 TTS Skill 生成真实旁白 stem；要求配乐时使用项目指定音乐 Skill 生成或取得真实音乐 stem。环境噪声和程序化噪声只能计入 SFX/ambience，不能冒充配乐。默认采用固定电平混音，不随旁白自动压低音乐；仅当 brief 明确指定时才做轻微 ducking。最终混音必须通过旁白转写回验、音乐非静音检查和分轨/总混响度检查。

### 5. 验收成片

**REQUIRED SUB-SKILL:** 使用 `$video-qc` 同时完成：

- 技术检查：解码、时长、分辨率、帧率、黑帧、冻结、静音、响度、字幕。
- 视觉检查：开头、中间、结尾和镜头交界代表帧。
- 创作检查：开场、信息密度、节奏、连续性、可读性、声音和结尾兑现。
- 追溯检查：采用镜头能够回溯到来源或生成记录。

任何一项失败都回到明确责任阶段，只重跑受影响镜头或导出。

## 交付

至少交付最终视频、可复现 EDL/渲染命令、脚本与字幕、素材来源清单、生成任务映射和 QA 报告。只有最终文件被重新打开、完整解码且视觉审阅通过，才能宣称完成。

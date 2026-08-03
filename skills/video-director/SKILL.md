---
name: video-director
description: 把视频创意、文章、产品需求、故事梗概或现有脚本发展为可拍摄、可检索素材、可生成并可剪辑的编导包，覆盖受众与核心命题、三幕或信息结构、节拍、镜头表、分镜、摄影与运动设计、人物场景连续性和生成计划。用户要求编剧、导演、分镜、shot list、广告脚本、短片策划、镜头语言、运镜、角色一致性或生成前规划时使用。
---

# 视频编导

产出可以直接交给素材检索、视频生成和剪辑的工程文件，而不是只写气氛化文案。

## 建立导演合同

读取当前项目已有内容，明确受众、发布场景、目标时长、画幅、核心命题、必须出现的信息、期望动作、情绪曲线、参考风格和制作限制。使用 [assets/director-brief.md](assets/director-brief.md) 建立或补全 brief。

## 从内容到节拍

1. 用一句话写清观众看完应理解或感受到什么。
2. 选择适合内容的结构：剧情使用起因—升级—转折—兑现；广告使用问题—证据—解决—行动；知识内容使用钩子—问题—解释—例证—结论。
3. 将结构拆成可见、可听、可剪的 beat。每个 beat 只承担一个主要叙事任务。
4. 把抽象心理和营销词改写成动作、表情、物件、环境变化、对白或可验证画面。

使用 [assets/script.md](assets/script.md) 建立脚本；分镜使用 [assets/storyboard.md](assets/storyboard.md)，不要把所有镜头压进一张只有气氛、没有动作阶段的拼图。

详细检查见 [references/story-and-continuity.md](references/story-and-continuity.md)。

## 设计镜头覆盖

为每个 beat 至少设计主镜头；关键动作补充建立镜头、中景、近景、反应、插入和环境声。遵循 [references/shot-design.md](references/shot-design.md)，使用 [assets/shot-list.csv](assets/shot-list.csv) 输出镜头表。

每个镜头必须包含：

- `shot_id`、所属 beat、预计时长和叙事功能。
- 主体、可见动作、场景、时间、构图、景别、机位、镜头运动和声音。
- 与前后镜头相连的视线、轴线、动作方向、光线和状态。
- 来源策略：`existing`、`capture`、`search`、`image_generate` 或 `video_generate`。
- 验收标准，以及不能出现的漂移或伪影。

## 锁定连续性

复制 [assets/continuity.yaml](assets/continuity.yaml) 并记录人物/商品、服装、道具、场景、时间、光线、色彩、屏幕方向、声音和不可逆剧情状态。镜头间只改变故事明确要求变化的字段。

## 转换为生成计划

1. 对生成镜头只描述一个主要动作，给出起始状态、结束状态、方向、速度和时长。
2. 优先用首帧、尾帧、人物图、商品图或参考片段锁定身份；不要只靠形容词要求一致。
3. 相邻镜头需要连续动作时，设计 overlap、match cut 或尾帧续拍。
4. 将模型选择留给对应生成 Skill，导演包只记录能力需求和参考素材。
5. 复制 [assets/generation-plan.json](assets/generation-plan.json) 写入计划，保持 `shot_id` 与输出文件一一对应。

## 导演审查

进入生产前逐项检查：前 3 秒是否建立观看理由；每个镜头是否推进信息或情绪；景别是否有变化；轴线和视线是否连贯；动作是否能在给定时长内完成；是否存在无法取得素材的镜头；片尾是否兑现开场承诺。失败项直接修改脚本或镜头表，不把问题推迟到剪辑阶段。

交付 `brief.md`、`script.md`、`continuity.yaml`、`shot-list.csv`、`storyboard.md` 和 `generation-plan.json`。

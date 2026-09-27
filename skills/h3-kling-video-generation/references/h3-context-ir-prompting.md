# MiniMax H3 Context-IR 写作规范

依据 MiniMax 官方 H3 Prompt 写作指南（base 与 ref 两份）整理。H3 训练时看到的是 **Context-IR**：英文、分字段、按 `[Shot N]` 编号的目标视频描述。发给模型的 Prompt 必须就是 Context-IR 本身；中文制作单、时长理由、后期清单只留在本地。

## 目录

1. 制作单与模型 Prompt 的分工
2. 选择模式
3. 通用写法
4. 镜头、摄影机与切镜
5. 声音、对白与画面文字
6. I2VA 与 FL2VA 的对齐行
7. Ref2VA 六段结构
8. 时长预算
9. 提示词扩写
10. 示例
11. 提交前检查

## 1. 制作单与模型 Prompt 的分工

每个镜头两份文件：

- **制作单**（中文，复制 [`../assets/h3-shot-plan-template.md`](../assets/h3-shot-plan-template.md)）：镜头定位、请求参数、后期与剪辑、验收。
- **模型 Prompt**（英文 Context-IR，复制 `../assets/h3-prompt-{t2va,i2va,fl2va,ref2va}.txt`，用 `--prompt-file` 提交）：只写目标视频里看得见、听得见的内容。

模板占位符按名称填写，`lint` 会拒绝任何未替换的 `{{…}}`。其中 `{{CAMERA_SENTENCE}}` 写一句运镜（第 4 节）；`{{OPTIONAL_DIALOGUE}}` 写 `The hoarse old man (S1) says: <d>[English] Line.</d>`，无台词时删除；`{{OPTIONAL_LATER_SHOTS}}` 写 `[Shot 2] At 00:04.000, the camera cuts to ...`，单镜头时删除。

以下内容只写进制作单，不进 Prompt：模式与素材说明、推荐时长与理由、剪辑采用区间、字幕／标题／UI／精确 MG、转场母题与交棒、A/B 实验说明，以及“严格保持”“不要……”一类指令。H3 把 Prompt 当作对成片的描述而不是命令：元指令会被当成画面内容或被忽略，中文长文档还会被扩写器整段改写。

## 2. 选择模式

| 模式 | 请求 | Prompt 开头 | 适用 |
| --- | --- | --- | --- |
| T2VA | `h3-max`（无图）或 `h3-max-t2v`；画幅默认 `16:9`，不支持 `adaptive` | 直接 `integrated_multimodal_description:` | 概念 smoke、不要求角色连续性的空镜 |
| I2VA | `h3-max-i2v` + 1 张 `--image` | I2VA 对齐行 | 已验收首帧；正式镜头默认 |
| FL2VA | `h3-max-i2v` + 2 张 `--image`（首帧、尾帧） | FL2VA 对齐行 | 必须精确落到指定结束状态 |
| Ref2VA | `h3-max-reference` + 图片／视频／音频参考 | `subject_definitions:` | 组合多个角色或场景参考、嗓音或动作参考、视频编辑与续写 |

正式镜头默认 **先出首帧，再做 I2VA**：用 `$gpt-image-generation` 按交付画幅生成并验收首帧，一次锁定身份、服装、构图和光线。Ref2VA 用于必须组合多个参考、复用嗓音或动作参考的镜头。只给尾帧的 L2VA 未在网关验证，不使用。

## 3. 通用写法

- 全英文。只有 `<d>…</d>` 里的台词和双引号里的画面文字保留原语言。
- 三个字段顺序固定，字段名后同一行开始写内容，字段之间空一行：`integrated_multimodal_description:`、`overall_soundscape:`、`non_diegetic_music:`。
- `[Shot 1]` 后先写逗号分隔的风格词，例如 `Live-action, cinematic, warm tungsten light,` 或 `2D anime, cel-shaded, flat colors,`，再写画面。
- 写陈述，不写命令：写 `The camera pushes in slowly as she looks up.`，不写 `Make sure the camera...`、`Do not add text.`。不想出现的东西不写，写出来反而可能出现。
- 人物首次出现时写清年龄段、发型、服装和关键道具，之后固定一个称呼，例如 `the woman in the grey coat`。
- 情绪写成可见表情和动作：`her jaw tightens and she looks away`，不写 `she feels betrayed`。
- 一个镜头一个核心事件；动作写成起始、发展和结果。

## 4. 镜头、摄影机与切镜

- `[Shot 1]` 不写时间戳。之后每个镜头以 `[Shot N] At MM:SS.mmm, the camera cuts to ...` 开头，时间严格递增且小于请求时长。
- 默认硬切；只有需要时才写 dissolve、fade 或 wipe。每次切镜都要带来新信息（新景别、新主体或动作结果），每个镜头不短于约 1.5 秒。
- 摄影机类型用官方词表：Zoom In/Out、Push In/Pull Out、Pan、Truck、Tilt、Pedestal、Arc Shot、Tracking Shot、Static Shot、Shake Slightly/Strongly、POV、Roll。
- 幅度与速度写 `with small amplitude`／`with large amplitude`、`at slow speed`／`at fast speed`；中等幅度、正常速度不写。
- 写成自然句：`The camera trucks right with small amplitude at slow speed, keeping her face in the left third of the frame.`
- 景别用英文：wide shot、medium shot、medium close-up、close-up、extreme close-up、over-the-shoulder、low angle、high angle。

## 5. 声音、对白与画面文字

- 每个开口的人物分配说话人 ID：`(S1)`、`(S2)`；齐声写 `(S1,S2)`；不说话的人物不分配。首次开口时描述嗓音，例如 `the hoarse, low-voiced old man (S1)`。
- 对白：`... (S1) says: <d>[English] Line.</d>`。中文台词写 `<d>[Chinese] 台词</d>`，语言标签用英文语言名。
- 画外音：`(S2) says in an off-screen voiceover: <d>...</d>`，再补一句画面中人物双唇闭合，例如 `Her lips stay closed as she reads.`。
- 台词跨切镜时在切点两侧用 `<scenetrans>` 标记并写明声音延续；被视频结尾截断的台词加 `<cutoff>`。拿不准时让台词在切镜前说完。
- 台词长度要在分配时间内说得完：英文约 2.5 词／秒，中文约 4 字／秒。
- 画面文字逐字写在英文双引号里：`a hand-painted sign reading "OPEN SOON"`。正式字幕、标题和 UI 文字交给后期，不让模型生成可读字幕。
- `overall_soundscape:` 写 1–4 句、一个段落：环境声、动作音及其来源和距离，不写对白、歌声和画内音乐。只有明确要求静音时写 `N/A`。
- `non_diegetic_music:` 写 1–3 句：乐器、速度、节奏、力度变化，不写 `epic`、`sad` 等情绪词；无配乐写 `N/A`。
- 需要后期配音或配乐时：`non_diegetic_music: N/A`，soundscape 只写克制的环境声，生成后丢弃或替换模型音轨。

## 6. I2VA 与 FL2VA 的对齐行

I2VA 第一行逐字写：

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.
```

空一行后接三字段。描述顺序：用一两句复述首帧的景别、主体和光线以对齐 → 动作起始 → 发展 → 结果。不要改写首帧已经确定的外观。

FL2VA 第一行是一整行，`Picture` 不加尖括号：

```text
How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the S.SS-second mark of the target video.
```

`N` 是最后一个镜头号，`S.SS` 是请求时长的两位小数（8 秒写 `8.00`）。描述中同样写 `Picture 1`、`Picture 2`。优先单镜头：从 `the shot begins in the position and framing established by Picture 1` 开始，写连续变化并逐渐收敛，以 `settling into the pose, position, and framing of Picture 2 at the end of the shot` 结束。首尾帧的主体位置、景别和场景都不同时，模型会硬切或突变，应拆成两个 I2VA 镜头。

## 7. Ref2VA 六段结构

六段顺序固定：`subject_definitions:`、`summary:`、`retention_analysis:`、`detailed_description:`、`overall_soundscape:`、`non_diegetic_music:`。段名独占一行，内容从下一行开始，每条一行，段落之间空一行。

**标签**（按类别分别从 1 编号，顺序与请求一致：第 1 个 `--image` 是 `<Picture 1>`）：

- `<Subject N>`：可复用的可见主体（人物、动物、物体、场景），用 is 句定义：`<Subject 1> is the silver-haired swordswoman in <Picture 1>.`；一个主体可引用多张图：`<Subject 2> is the fluffy white Samoyed in <Picture 2>, <Picture 3>, and <Picture 4>.`。只用于定义主体的图片不再单独写 `<Picture N>` 行。
- `<Picture N>` 单独成行只用于首帧、关键帧或构图锚点：`<Picture 3> is the opening frame of the target video.`
- `<Video N>`：整段视频的关系，例如被编辑、被续写或作为动作参考。
- `<Audio N>`：被复制或参考的声音；嗓音参考写 `<Audio 1> is the voice timbre reference for <Subject 1> (S1).`。参考视频的原声需要复用时，也可标为独立的 `<Audio N>`。

**summary**：以方括号任务标签开头，多个用 ` + ` 连接且不重复：`keyframe completion`、`reference generation`、`video editing`、`video continuation`、`audio reuse`、`audio reference`。随后一两句概括目标视频，不引入新标签。视频编辑以 `The target video is an edited version of <Video 1>.` 开头。

**retention_analysis**：每个标签一行，不写 `(Sx)`。

- 视觉：`<Subject 1> (appears in [Shot 1], [Shot 2]): fully_preserved - ...`，标记为 `fully_preserved`、`partially_preserved`、`attribute_transfer`、`weak_reference`。
- 声音：`<Audio 1>: reference - ...`，标记为 `fully_copy`、`partially_copy`、`reference`、`weak_reference`。

**detailed_description**：先写 1–2 句整体风格，再写 `[Shot 1]`；生成任务约 350–500 词。关键帧写 `the shot begins from <Picture N>`、`the keyframe corresponds to <Picture N>` 或 `ends on <Picture N>`。说话主体写 `<Subject 1> (S1) says: <d>[English] ...</d>`。两个声音段同第 5 节。

## 8. 时长预算

H3 Max 为 5–15 秒整数（旧 H3 为 4–15 秒），24 fps。选择能容纳动作和落幅的最短时长：

- 建立：约 0.5–1.5 秒；普通动作：约 1.5–2 秒；复杂动作：约 2–4 秒；结束保持：约 0.6–1.5 秒；台词按第 5 节语速估算后加 0.5 秒。
- `5–6 秒`：一个主体、一个动作；`7–9 秒`：同一事件的两个节拍，或动作加缓慢运镜；`10–12 秒`：完整单镜头表演或人物调度；`13–15 秒`：确有必要的长动作，信息过多时优先拆镜。
- 成片只用 1 秒的插入镜头也按模型最低时长生成，剪辑时取稳定区间。
- 全片最后一镜要在预算里留出结束保持，供剪辑做收尾（见 `$video-editing`）。

## 9. 提示词扩写

H3 Max 的 `prompt_expansion_mode` 有三档：`disabled` 原样使用，`balanced`（网关默认）改写，`quality` 更强改写。改写器的输出就是 Context-IR，改写结果在 `expanded_prompt`。

脚本默认 `--prompt-expansion auto`：Context-IR Prompt 发送 `disabled`，避免二次改写；普通文字 Prompt 不发送该字段，由网关按 `balanced` 改写。不确定某类镜头怎么写时，可以用一句英文描述加 `--prompt-expansion quality` 跑一次 smoke，从 sidecar 的 `expanded_prompt` 学习写法（前提是网关透传该字段），再改成自己的 Context-IR 文件。

## 10. 示例

以下示例可直接通过 `lint`。

### T2VA 示例（8 秒）

请求：`--model h3-max --aspect-ratio 16:9 --duration 8`

```text
integrated_multimodal_description: [Shot 1] Live-action, cinematic, natural morning light, shallow depth of field, a medium shot of a narrow bakery storefront at dawn on a quiet cobblestone street. A broad-shouldered baker in his fifties with a grey beard and a flour-dusted white apron pulls up a squeaking metal shutter with both hands, revealing a window lined with golden loaves beneath a hand-painted sign reading "OPEN SOON". The camera pushes in with small amplitude at slow speed as he wipes his hands on his apron and glances at his wristwatch. The warm, gravelly-voiced baker (S1) says: <d>[English] Right on time, as always.</d> [Shot 2] At 00:05.000, the camera cuts to a close-up of a serrated knife slicing through a crusty loaf on a wooden board, steam rising from the soft crumb as the halves fall apart, while the camera holds a static shot.

overall_soundscape: The metal shutter rattles and squeaks as it rolls up, followed by distant birdsong and a single bicycle bell on the empty street. The knife crunches through the crust with a crisp, dry rasp against the wooden board.

non_diegetic_music: A fingerpicked acoustic guitar plays a light, steady pattern at a moderate tempo, joined by a soft upright bass on the second shot.
```

### I2VA 示例（5 秒）

请求：`--model h3-max-i2v --image FIRST_FRAME --duration 5`

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1] Live-action, cinematic, soft overcast light, muted blue-grey palette, a medium close-up of a young woman with a short black bob and a camel wool coat sitting by a rain-streaked train window, a folded letter resting in her lap. Raindrops slide across the glass as the blurred countryside streams past behind her. She slowly unfolds the letter, reads the first line, and presses her lips together as her eyes grow wet. The camera trucks right with small amplitude at slow speed, keeping her face in the left third of the frame. She lifts her gaze toward the window, and the quiet, breathy young woman (S1) says: <d>[English] I get off at the next station.</d> She folds the letter closed and holds it against her chest as the carriage sways gently.

overall_soundscape: The steady clatter of train wheels runs beneath the soft drumming of rain on the window. Paper rustles crisply as the letter opens and closes, and a faint two-tone station chime sounds in the distance near the end.

non_diegetic_music: A slow solo cello holds long, sustained notes over sparse, soft piano chords.
```

### FL2VA 示例（8 秒）

请求：`--model h3-max-i2v --image FIRST_FRAME --image LAST_FRAME --duration 8`

```text
How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot 1) aligns with the 8.00-second mark of the target video.

integrated_multimodal_description: [Shot 1] Live-action, cinematic, neon-lit night street, wet asphalt reflections, the shot begins in the position and framing established by Picture 1: a wide shot of a young cyclist in a yellow rain jacket standing beside her bicycle at a crosswalk as rain falls hard around her. She reaches into her backpack, pulls out a folded red umbrella, and snaps it open above her head, water spraying off the canopy. The camera pulls out with small amplitude at slow speed, revealing more of the glowing storefronts on both sides of the street. She rests the umbrella on her shoulder, grips the handlebar with her free hand, and turns toward the crossing signal, settling into the pose, position, and framing of Picture 2 at the end of the shot.

overall_soundscape: Heavy rain hisses on the pavement and patters loudly on the umbrella canopy once it opens. A car rolls slowly through a puddle in the background while the crossing signal ticks steadily.

non_diegetic_music: N/A
```

### Ref2VA 示例（8 秒；2 张图片 + 1 段音频）

请求：`--model h3-max-reference --image CHARACTER_SHEET --image ROOFTOP_GARDEN --reference-audio VOICE_SAMPLE --aspect-ratio 9:16 --duration 8`

```text
subject_definitions:
<Subject 1> is the silver-haired swordswoman in <Picture 1>.
<Subject 2> is the overgrown rooftop garden with glowing paper lanterns in <Picture 2>.
<Audio 1> is the voice timbre reference for <Subject 1> (S1).

summary:
[reference generation + audio reference] The target video shows <Subject 1> walking through <Subject 2> in the rain at night and speaking one line in the voice of <Audio 1>.

retention_analysis:
<Subject 1> (appears in [Shot 1], [Shot 2]): fully_preserved - Her face, long silver hair, dark high-collared coat, and the sheathed katana on her left hip match the reference.
<Subject 2> (appears in [Shot 1], [Shot 2]): partially_preserved - The garden layout, wooden planters, and paper lanterns follow the reference, while heavy rain and night lighting are added.
<Audio 1>: reference - Her spoken line follows the low, calm timbre and unhurried pacing of the reference voice without copying its words.

detailed_description:
Live-action, cinematic, rain-soaked night, cool teal shadows with warm lantern highlights, shallow depth of field, slow and deliberate pacing. The palette stays desaturated except for the amber glow of the lanterns. [Shot 1] A wide tracking shot follows <Subject 1> from behind and slightly to her right as she walks along a narrow stone path through <Subject 2>. Rain falls steadily through the beams of the paper lanterns strung overhead, and water drips from the leaves of the overgrown planters on both sides. Her long silver hair is soaked and clings to the shoulders of her dark high-collared coat, and her left hand rests on the hilt of the sheathed katana at her hip. The camera tracks forward at slow speed, keeping her in the right third of the frame while the city skyline glows faintly through the mist beyond the rooftop railing. She passes beneath a swaying lantern, and its warm light slides across her shoulders before she steps back into shadow. Puddles on the stone path ripple under each step, reflecting the amber lanterns and the distant towers. A gust of wind sets the lantern strings swaying and scatters a spray of droplets across the path ahead of her, and the hem of her coat flares briefly before settling back against her boots. [Shot 2] At 00:04.500, the camera cuts to a medium close-up of <Subject 1> from the front as she stops at the edge of the rooftop and turns her head toward the skyline. Raindrops bead on her eyelashes and run down her cheek, and a lantern behind her casts a soft rim of amber light around her silhouette. She narrows her eyes at the distant towers, her expression calm and unreadable, while her fingers tighten slightly around the hilt. The camera holds a static shot, framing her face slightly off-center with the blurred city lights filling the space behind her. Over her shoulder, the lanterns sway gently and the rain streaks through their glow in thin silver lines. <Subject 1> (S1) says: <d>[English] The city never sleeps. Neither do I.</d> After the line, she exhales slowly, a faint cloud of breath drifting past her lips, and keeps her eyes fixed on the skyline as the rain continues to fall around her.

overall_soundscape:
Steady rain patters on the stone path, the wooden planters, and the paper lanterns, with water dripping from leaves and gutters nearby. Her boots splash softly through shallow puddles, and a distant city hum and a faint siren drift up from the streets far below.

non_diegetic_music:
A low analog synth drone sustains beneath slow, sparse electric piano notes at a slow tempo, swelling slightly in volume on the second shot.
```

## 11. 提交前检查

先运行 `lint`（见 SKILL.md），它会检查字段结构、对齐行、镜头时间戳、标签与素材数量、中文残留和指令句。再人工确认：

- 请求的模型 SKU、图片张数和参考素材与 Prompt 模式一致；Ref2VA 标签编号与素材顺序一致；
- 每个镜头一个核心事件，切镜带来新信息，台词在分配时间内说得完；
- 摄影机用官方词表写成自然句，没有“固定同时推进”等冲突；
- 首帧已经锁定的外观没有被改写；FL2VA 首尾帧差异可以在一个连续动作内完成；
- 声音字段不含对白和情绪词；需要后期声音的镜头已写 `N/A` 并计划替换模型音轨；
- A/B 实验的 Prompt 逐字相同，只改一个请求变量，并固定 `--seed`。

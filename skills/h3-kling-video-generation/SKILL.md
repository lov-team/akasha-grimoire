---
name: h3-kling-video-generation
description: 通过 OpenAI-compatible 异步视频端点调用 MiniMax H3 文生视频或图生视频、Kling 3.0 与 Kling 2.5 Turbo；按导演结构编写成片合同、素材职责、连续性、秒级动作、摄影机、结束构图与声音提示词，并支持二维日系赛璐璐、抽象 MG、游戏 UI 合成的宣传 PV 视觉系统与转场编排。用户要求编写或优化 H3/Kling Prompt、制作游戏宣传 PV、调用这些模型、轮询下载或验收 MP4 时使用。
---

# H3 与 Kling 视频生成

使用 [`scripts/video_generation.py`](scripts/video_generation.py) 提交异步任务。真实生成会计费；未明确要求生成时，仅运行帮助、单元测试和本地 mock。

## 选择模型

- `minimax-h3`（默认）→ `minimax-h3/text-to-video`：4–15 秒，`768P` 或 `2K`，纯文生视频。
- `h3-i2v` → `minimax-h3/image-to-video`：4–15 秒，`768P` 或 `2K`；一张 `--image` 为首帧，两张依次为首帧、尾帧。
- `kling-3` → `kling-3.0/video`：3–15 秒，支持单镜头参考图、声音和 `std`/`pro`/`4K`。
- `kling-2.5-t2v` → `kling/v2-5-turbo-text-to-video-pro`：5 或 10 秒，纯文生视频。

需要完整字段约束时读取 [`references/model-contracts.md`](references/model-contracts.md)。不要把其他供应商的字段混入请求。

## 编写 H3 导演级 Prompt

H3 Prompt 使用 Seedance 的导演级表达标准，但必须服从 H3 的素材和请求契约。先读取 [`references/h3-director-prompting.md`](references/h3-director-prompting.md)；需要落盘时复制并填写 [`assets/h3-director-prompt-template.txt`](assets/h3-director-prompt-template.txt)。

游戏宣传 PV、二维赛璐璐与 Editorial MG 合成任务还要读取 [`references/game-pv-motion-design.md`](references/game-pv-motion-design.md)，先填写 [`assets/game-pv-prompt-template.txt`](assets/game-pv-prompt-template.txt) 建立全片视觉母题和转场接力，再拆成单镜头生成 Prompt。不要把全片美术圣经、角色设定、三层 MG 行为和多次转场塞进一个模型镜头。

最小完整结构：

1. **成片合同**：推荐时长、选择理由、预计剪辑采用区间、媒介质感、节奏、唯一核心事件与最终落点；
2. **参考帧职责**：首帧锁定身份、服装、初始景别、构图和光线；尾帧只在实际传入时声明；
3. **连续性硬约束**：只列需要冻结的身份、道具、空间、光线和屏幕方向，并明确唯一允许变化；
4. **秒级动作与摄影机**：时间从 `0.00` 连续覆盖到 `duration`，每段一个主要动作；写清景别/机位、摄影机类型/幅度/速度/目标、焦点与结束构图；
5. **声音策略**：环境声、动作音、对白和配乐逐层选择；后期配音项目明确无对白、无配乐，并在验收后移除模型音轨；
6. **合成与转场**：区分模型内角色／场景运动和后期 MG／UI 图形；为每个镜头指定入场母题、主视觉事件与交给下一镜的出场图形；
7. **高损失限制**：只保留会破坏镜头合同的错误，避免泛化否定词淹没动作。

时长必须给出具体整数秒建议，并选择能完整容纳动作与落幅的最短时长：`4 秒`用于 smoke、静态插入或单一微动作；`5–6 秒`用于默认简单单镜头；`7–9 秒`用于两个连续动作节拍或一个动作加缓慢运镜；`10–12 秒`用于完整单镜头表演或连续人物调度；`13–15 秒`只用于确有必要的长动作和连续编排，信息过多时优先拆镜。最终只需 0.8–1.2 秒的插入镜头也按 H3 最低 4 秒生成，再裁取稳定区间。完整预算方法见导演规范。

4–6 秒单镜头可以写成紧凑的三段微时间轴；不要把多个独立事件塞进一个短镜头。图生视频不重复发明首帧已经锁定的静态美术，只描述素材职责、允许发生的变化、摄影机反应和结束状态。

同一 A/B 实验若只比较首帧景别，两份 H3 Prompt 必须逐字相同，并写“严格保持首帧既有景别与取景范围”；不要在文字里再次分别描述 A/B 景别，否则会引入第二个主要变量。

## 生成

先用一个最小代表镜头验证方向，再批量生成：

```bash
python3 skills/h3-kling-video-generation/scripts/video_generation.py generate \
  --model minimax-h3 \
  --prompt "A cobalt sphere rotates slowly in a clean studio, locked camera, no text" \
  --duration 4 \
  --aspect-ratio 16:9 \
  --resolution 768P \
  --output /tmp/minimax-h3-smoke.mp4
```

Kling 3.0 参考图单镜头：

```bash
python3 skills/h3-kling-video-generation/scripts/video_generation.py generate \
  --model kling-3 \
  --prompt "The subject turns toward camera; preserve identity and clothing" \
  --image https://media.example/subject.png \
  --duration 5 \
  --mode pro \
  --sound \
  --output /tmp/kling-3.mp4
```

MiniMax H3 首帧图生视频：

```bash
python3 skills/h3-kling-video-generation/scripts/video_generation.py generate \
  --model h3-i2v \
  --prompt "$(cat /tmp/h3-director-prompt.txt)" \
  --image https://media.example/first-frame.png \
  --duration 4 \
  --resolution 768P \
  --output /tmp/minimax-h3-i2v.mp4
```

H3 图生视频沿用参考帧宽高比，不发送 `aspect_ratio`。输入必须是上游可匿名读取、任务周期内稳定的公共 HTTPS 图片；如需首尾帧控制，再追加一次 `--image`。脚本同时把参考帧放入标准 `images` 请求信封，并将两张图分别映射为 KIE 原生 `image_url` 和 `end_image_url`；前者用于请求分类和素材处理，后者用于上游模型字段，不能用纯提示词冒充参考帧。

复杂 Kling 3.0 多镜头或元素引用使用 `--metadata-json` 传原生 `multi_shots`、`multi_prompt` 与 `kling_elements`。脚本仍以显式 CLI 的时长、画幅、模式、声音和图片覆盖同名字段。

## H3 图生视频生产闭环

用户已明确批准真实生成，且同一任务的镜头计划、参考图和输出目录齐全时，直接从当前未完成步骤继续；不要重复确认模型、时长、费用或是否生成。先用 `4 秒 + 768P` 代表镜头做低成本方向 smoke；方向通过后，根据镜头合同的动作预算给每个镜头推荐 `4–15` 秒中的最短整数秒数，再按交付要求选择 `768P` 或 `2K`。不得把 10 秒或 15 秒当作统一生产默认值，也不得为了用满时长添加无叙事作用的动作。随后自动继续批量提交、轮询、下载与验收。仅在缺少会实质改变结果的关键输入，或输出覆盖存在冲突时暂停。

提交前先用 `/v1/models` 确认实际 SKU。公共 HTTPS 参考图上传后必须重新匿名下载，逐项核对 SHA-256、字节数、MIME 与像素尺寸；任一不符立即更换端点，不把临时图床当作固定依赖。下载生成结果后必须运行 `ffprobe`、完整解码并抽取首中尾帧；正式配音或配乐项目丢弃模型自带音轨。

若首尾参考帧的主体位置、景别或场景差异明显，把结果按 A/B 两镜或两个独立片段处理，不强求单镜头连续性。竖屏成片需要保留人物关系时，允许完整保留参考图比例并居中置入 1080×1920，以模糊背景填充上下空间，避免直接裁掉主体。

遇到 H3 路由或上游失败时，读取 [`references/model-contracts.md`](references/model-contracts.md) 的“已验证故障与恢复”，按已验证字段修复后继续，不重复付费试错。

## 协议与配置

- 提交：`POST /v1/video/generations`。
- 轮询：`GET /v1/video/generations/{task_id}`。
- 下载：`GET /v1/videos/{task_id}/content`。
- Base URL 优先级：`--base-url`、`H3_KLING_VIDEO_BASE_URL`、共享 Akasha 凭证、`OPENAI_BASE_URL`、默认 `https://llmapi.lovbrowser.com/v1`。
- Key 优先级：`H3_KLING_VIDEO_API_KEY`、共享 Akasha 凭证、`OPENAI_API_KEY`；不得写入命令、日志或仓库。

仅在需要覆盖既有输出时传 `--overwrite`。脚本验证 MP4 `ftyp` 签名并原子写入；随后使用 `ffprobe` 检查视频流、实际时长、分辨率和音轨，再抽帧或播放做视觉验收。

## 余额不足

仅官方入口返回可充值的 `insufficient_user_quota` 时使用共享充值控制器；整条命令至多充值一次并只重试失败请求一次。用户主动充值时运行仓库根目录的 `python3 shared/akasha_recharge.py --recharge-usd 金额`。

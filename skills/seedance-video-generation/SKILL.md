---
name: seedance-video-generation
description: 为 Seedance 编排秒级时间轴、导演级景别运镜、参考素材职责、连续性与声音提示词，并通过 new-api 的异步视频任务端点调用火山方舟 Doubao Seedance 1.0 Pro、1.0 Lite T2V/I2V、1.5 Pro、2.0 Pro/2.0 Fast，按模型校验时长与素材，轮询并安全下载 MP4。用户要求用 Seedance、豆包或 doubao-seedance 设计/优化视频提示词、复刻运镜、做首尾帧或多模态参考生成、生成成片、验证 /v1/video/generations，或排查提交、轮询、分辨率与下载失败时使用。
---

# Seedance 视频生成

先把需求改写成可执行的 Seedance Prompt，再使用 [`scripts/seedance_video.py`](scripts/seedance_video.py) 调用 new-api。真实生成会计费；先提交一个 5 秒、720p 的最小任务，再扩大时长或画质。

## 准备

脚本默认使用 LovBrowser new-api：`https://newapi.1234bot.com/v1`。只有需要切换私有部署时才按 `--base-url`、`SEEDANCE_VIDEO_BASE_URL`、`NEW_API_BASE_URL` 的顺序覆盖，不读取 `OPENAI_BASE_URL`。所有媒体 Skill 共用 `LOVBROWSER_API_KEY`，也可优先复用本地 `OPENAI_API_KEY`。

没有 Key 时，入口会调用共享 `shared/akasha_credentials.py` 进入 `AKASHA_DEVICE_V1`：在对话中渲染本地 PNG 二维码，同时显示可点击链接和短码，用户确认后自动轮询、原子保存、以 `/v1/models` 验证，并让原动作继续一次。不要显示 device code、PKCE verifier、真实 Key 或凭证文件内容。详见 [`akasha-key-setup`](../akasha-key-setup/SKILL.md) 与 [`credentials-contract.md`](../../shared/credentials-contract.md)。

用户明确要求充值时，直接在仓库根目录运行 `python3 shared/akasha_recharge.py`，不要先提交视频请求。仅官方 new-api 在精确识别余额不足且 metadata 允许充值时，才会自动创建 LovBrowser 支付页面。**整次命令最多一次充值**；入账后只重试失败的提交/轮询/下载一次，**已提交任务不会因轮询余额不足而重新提交**。`--recharge-usd` 可写在 `generate` 前或后。收到 `akasha.recharge` 后，Codex 只给出可点击的 `publicPageUrl`，不显示二维码；金额由用户在页面选择。详见 [`shared/recharge-contract.md`](../../shared/recharge-contract.md)。

输入参考素材必须是上游可访问的公共 HTTPS URL，不能依赖客户端 Authorization。输出写到仓库外 staging；脚本拒绝静默覆盖文件。

## 项目级 AGENTS.md

项目需要固化 Seedance 协作规则时，使用 [`assets/AGENTS.md`](assets/AGENTS.md) 作为可复制模板。项目已有 `AGENTS.md` 时只合并「Seedance 视频生成」章节，不覆盖原有规则；项目的更严格约束优先。

## 编排导演级 Prompt

- 4–6 秒、单主体、单动作时，按“起始构图 → 一个主要动作 → 运镜反应 → 结束构图 → 同步声音”写紧凑 Prompt，不强拆多段。
- 7–15 秒、多镜头、参考运镜、动作卡点、广告或剧情请求，读取 [`references/director-prompting.md`](references/director-prompting.md)，复制并填写 [`assets/director-prompt-template.txt`](assets/director-prompt-template.txt)。
- 每个时间段只安排一个主要动作；时间段从 `0.00` 连续覆盖到命令的 `--duration`。运镜写清类型、必要的幅度/速度和目标，不堆叠互相冲突的摄影词。
- new-api 通过 CLI 参数结构化标记首帧、尾帧和参考媒体。Prompt 用自然语言说明素材职责，不写即梦网页端的 `@图片1` / `@视频1` 标记。
- 完整片超过 5 秒时，为 smoke 另写只覆盖前 5 秒的 Prompt；不要把完整 15 秒时间轴与 `--duration 5` 混用。

长 Prompt 写入 UTF-8 文件并使用 `--prompt-file`，避免 shell 引号与换行破坏时间轴：

```bash
cp skills/seedance-video-generation/assets/director-prompt-template.txt /tmp/seedance-director-prompt.txt
# 填完所有槽位并删除不适用行后执行
python3 skills/seedance-video-generation/scripts/seedance_video.py generate \
  --prompt-file /tmp/seedance-director-prompt.txt \
  --duration 10 \
  --resolution 720p \
  --ratio 16:9 \
  --output /tmp/seedance-director.mp4
```

## 文生视频

```bash
python3 skills/seedance-video-generation/scripts/seedance_video.py generate \
  --prompt "雨夜霓虹街道，镜头缓慢向前推进，无文字" \
  --duration 5 \
  --resolution 720p \
  --ratio 16:9 \
  --output /tmp/seedance.mp4
```

默认模型为 `doubao-seedance-2-0-260128`。快速模型需显式传 `--model doubao-seedance-2-0-fast-260128`。Seedance 2.x 时长为 4–15 秒。

`--prompt` 与 `--prompt-file` 必须且只能选择一个。`--prompt-file` 接受不超过 256 KiB 的非空 UTF-8 普通文件。

## 模型选择

- `seedance-1.0-pro` → `doubao-seedance-1-0-pro-250528`，4–12 秒，支持文字或图片输入。
- `seedance-1.0-lite` 根据是否传入图片，自动选择 `doubao-seedance-1-0-lite-t2v-250428` 或 `doubao-seedance-1-0-lite-i2v-250428`，4–12 秒。
- `seedance-1.5-pro` → `doubao-seedance-1-5-pro-251215`，4–12 秒，支持文字或图片输入与原生音频生成。
- `seedance-2` / `seedance-2-fast`：映射到对应 2.0 Ark ID，4–15 秒，支持图片、视频和音频参考。

Seedance 1.x 不接受视频或音频参考；脚本会在发起计费请求前拒绝不兼容的组合。使用前确认 new-api 渠道已启用该 Ark 模型并配置定价。

## 参考素材

按需重复传入素材参数：

```bash
python3 skills/seedance-video-generation/scripts/seedance_video.py generate \
  --prompt "保持角色与服装一致，角色转身并挥手" \
  --first-frame https://media.example.invalid/first.png \
  --last-frame https://media.example.invalid/last.png \
  --reference-video https://media.example.invalid/motion.mp4 \
  --reference-audio https://media.example.invalid/music.mp3 \
  --duration 10 \
  --resolution 720p \
  --output /tmp/seedance-reference.mp4
```

带参考视频时，单条视频不得超过 15 秒。含参考素材的 Seedance 2.0 请求优先用 720p；1080p/4K 是否可用取决于当前模型与参考模式，不要把纯文生视频成功外推为参考视频也兼容同一分辨率。

## 任务与验收

脚本提交 `POST /v1/video/generations`，轮询 `GET /v1/video/generations/{task_id}`，成功后通过 `GET /v1/videos/{task_id}/content` 下载结果。只有终态成功、下载为非空 MP4 且文件签名有效才算协议完成。

交付前继续用 `ffprobe` 检查时长、编码、分辨率，并按 Prompt 时间轴抽取代表帧，检查主体一致性、动作完成度、运镜方向、转场触发、声音同步、文字与水印。不要以 HTTP 200、任务 `SUCCESS` 或脚本 `OK` 代替成片验收。

常见错误：

- `401`：new-api token 缺失、失效或无权访问。
- `400 model price not configured`：管理员尚未配置该 Seedance 模型的倍率。
- `400/404 channel not found`：new-api 尚未启用包含该模型的 DoubaoVideo/VolcEngine 渠道。
- `resolution ... not valid`：改用 720p，尤其是带参考素材时。
- `queued` / `IN_PROGRESS`：继续轮询；超时后明确报告任务未完成，不伪造成功。

脚本只在最终成功后原子写入输出；失败时不要把 JSON、HTML 或空响应保存成视频。

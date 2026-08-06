---
name: newapi-video-generation
description: 通过 LovBrowser new-api 的异步视频任务端点调用 KIE MiniMax H3 文生视频或图生视频、Kling 3.0 与 Kling 2.5 Turbo，执行模型级时长、画幅、清晰度、首尾参考帧校验，静默轮询并安全下载 MP4。用户要求用 minimax-h3、MiniMax H3、H3 图生视频、Kling 3、Kling 2.5、new-api 新视频模型生成视频，或排查 /v1/video/generations 提交、轮询与下载时使用。
---

# NewAPI 多模型视频生成

使用 [`scripts/newapi_video.py`](scripts/newapi_video.py) 提交异步任务。真实生成会计费；未明确要求生成时，仅运行帮助、单元测试和本地 mock。

## 选择模型

- `minimax-h3`（默认）→ `minimax-h3/text-to-video`：4–15 秒，`768P` 或 `2K`，纯文生视频。
- `h3-i2v` → `minimax-h3/image-to-video`：4–15 秒，`768P` 或 `2K`；一张 `--image` 为首帧，两张依次为首帧、尾帧。
- `kling-3` → `kling-3.0/video`：3–15 秒，支持单镜头参考图、声音和 `std`/`pro`/`4K`。
- `kling-2.5-t2v` → `kling/v2-5-turbo-text-to-video-pro`：5 或 10 秒，纯文生视频。

需要完整字段约束时读取 [`references/model-contracts.md`](references/model-contracts.md)。不要把其他供应商的字段混入请求。

## 生成

先用一个最小代表镜头验证方向，再批量生成：

```bash
python3 skills/newapi-video-generation/scripts/newapi_video.py generate \
  --model minimax-h3 \
  --prompt "A cobalt sphere rotates slowly in a clean studio, locked camera, no text" \
  --duration 4 \
  --aspect-ratio 16:9 \
  --resolution 768P \
  --output /tmp/minimax-h3-smoke.mp4
```

Kling 3.0 参考图单镜头：

```bash
python3 skills/newapi-video-generation/scripts/newapi_video.py generate \
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
python3 skills/newapi-video-generation/scripts/newapi_video.py generate \
  --model h3-i2v \
  --prompt "Preserve the character, clothing, drawing lines and colors; only add breathing, grass movement and a slow camera push" \
  --image https://media.example/first-frame.png \
  --duration 10 \
  --resolution 2K \
  --output /tmp/minimax-h3-i2v.mp4
```

H3 图生视频沿用参考帧宽高比，不发送 `aspect_ratio`。输入必须是上游可匿名读取、任务周期内稳定的公共 HTTPS 图片；如需首尾帧控制，再追加一次 `--image`。脚本同时把参考帧放入 new-api 标准 `images` 信封，并将两张图分别映射为 KIE 原生 `image_url` 和 `end_image_url`；前者用于请求分类和素材处理，后者用于上游模型字段，不能用纯提示词冒充参考帧。

复杂 Kling 3.0 多镜头或元素引用使用 `--metadata-json` 传原生 `multi_shots`、`multi_prompt` 与 `kling_elements`。脚本仍以显式 CLI 的时长、画幅、模式、声音和图片覆盖同名字段。

## H3 图生视频生产闭环

用户已明确批准真实生成，且同一任务的镜头计划、参考图和输出目录齐全时，直接从当前未完成步骤继续；不要重复确认模型、时长、费用或是否生成。先生成一个代表镜头，默认用 10 秒、`2K` 检查首帧继承、人物与画风稳定性、运动幅度和首中尾变化；小样通过后自动继续批量提交、轮询、下载与验收。仅在缺少会实质改变结果的关键输入，或输出覆盖存在冲突时暂停。

提交前先用 `/v1/models` 确认实际 SKU。公共 HTTPS 参考图上传后必须重新匿名下载，逐项核对 SHA-256、字节数、MIME 与像素尺寸；任一不符立即更换端点，不把临时图床当作固定依赖。下载生成结果后必须运行 `ffprobe`、完整解码并抽取首中尾帧；正式配音或配乐项目丢弃模型自带音轨。

若首尾参考帧的主体位置、景别或场景差异明显，把结果按 A/B 两镜或两个独立片段处理，不强求单镜头连续性。竖屏成片需要保留人物关系时，允许完整保留参考图比例并居中置入 1080×1920，以模糊背景填充上下空间，避免直接裁掉主体。

遇到 H3 路由或上游失败时，读取 [`references/model-contracts.md`](references/model-contracts.md) 的“已验证故障与恢复”，按已验证字段修复后继续，不重复付费试错。

## 协议与配置

- 提交：`POST /v1/video/generations`。
- 轮询：`GET /v1/video/generations/{task_id}`。
- 下载：`GET /v1/videos/{task_id}/content`。
- Base URL 优先级：`--base-url`、`NEWAPI_VIDEO_BASE_URL`、`NEW_API_BASE_URL`、`OPENAI_BASE_URL`、默认 `https://newapi.1234bot.com/v1`。
- Key 优先级：`NEWAPI_VIDEO_API_KEY`、`NEW_API_API_KEY`、`OPENAI_API_KEY`；不得写入命令、日志或仓库。

仅在需要覆盖既有输出时传 `--overwrite`。脚本验证 MP4 `ftyp` 签名并原子写入；随后使用 `ffprobe` 检查视频流、实际时长、分辨率和音轨，再抽帧或播放做视觉验收。

## 余额不足

仅官方入口返回可充值的 `insufficient_user_quota` 时使用共享充值控制器；整条命令至多充值一次并只重试失败请求一次。用户主动充值时运行仓库根目录的 `python3 shared/akasha_recharge.py --recharge-usd 金额`。

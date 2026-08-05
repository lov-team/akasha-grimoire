---
name: newapi-video-generation
description: 通过 LovBrowser new-api 的异步视频任务端点调用 MiniMax H3、Kling 3.0 与 Kling 2.5 Turbo 文生视频模型，执行模型级时长、画幅、清晰度和参考图校验，静默轮询并安全下载 MP4。用户要求用 minimax-h3、MiniMax H3、Kling 3、Kling 2.5、new-api 新视频模型生成视频，或排查 /v1/video/generations 提交、轮询与下载时使用。
---

# NewAPI 多模型视频生成

使用 [`scripts/newapi_video.py`](scripts/newapi_video.py) 提交异步任务。真实生成会计费；未明确要求生成时，仅运行帮助、单元测试和本地 mock。

## 选择模型

- `minimax-h3`（默认）→ `minimax-h3/text-to-video`：4–15 秒，`768P` 或 `2K`，纯文生视频。
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

复杂 Kling 3.0 多镜头或元素引用使用 `--metadata-json` 传原生 `multi_shots`、`multi_prompt` 与 `kling_elements`。脚本仍以显式 CLI 的时长、画幅、模式、声音和图片覆盖同名字段。

## 协议与配置

- 提交：`POST /v1/video/generations`。
- 轮询：`GET /v1/video/generations/{task_id}`。
- 下载：`GET /v1/videos/{task_id}/content`。
- Base URL 优先级：`--base-url`、`NEWAPI_VIDEO_BASE_URL`、`NEW_API_BASE_URL`、`OPENAI_BASE_URL`、默认 `https://newapi.1234bot.com/v1`。
- Key 优先级：`NEWAPI_VIDEO_API_KEY`、`NEW_API_API_KEY`、`OPENAI_API_KEY`；不得写入命令、日志或仓库。

仅在需要覆盖既有输出时传 `--overwrite`。脚本验证 MP4 `ftyp` 签名并原子写入；随后使用 `ffprobe` 检查视频流、实际时长、分辨率和音轨，再抽帧或播放做视觉验收。

## 余额不足

仅官方入口返回可充值的 `insufficient_user_quota` 时使用共享充值控制器；整条命令至多充值一次并只重试失败请求一次。用户主动充值时运行仓库根目录的 `python3 shared/akasha_recharge.py --recharge-usd 金额`。

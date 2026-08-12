---
name: gemini-omni-video-generation
description: 通过 LovBrowser new-api 的异步 OpenAI-compatible 视频任务端点调用 gemini-omni-video，支持文生视频、通过公开 HTTPS 视频或已完成任务进行视频编辑，轮询终态、下载 MP4、校验签名与媒体流，并诊断 Cloudflare User-Agent、认证、余额、状态映射和意外音轨。用户要求用 Gemini Omni 生成或修改视频、验证 gemini-omni-video、调用 /v1/videos、使用 video_list 编辑、轮询视频任务、下载或验收 MP4 时使用。
---

# Gemini Omni 视频生成与编辑

使用内置脚本提交异步任务，不手写包含凭证的 curl。真实视频任务会计费；未获用户授权时，只运行 `--help`、单元测试或本地 mock。

## 协议

- 提交：`POST /v1/videos`。Kie 渠道不使用 `/v1/videos/generations`。
- 轮询：`GET /v1/videos/{task_id}`。接受短暂 `unknown`，直到成功、失败或超时。
- 下载：`GET /v1/videos/{task_id}/content`。
- 编辑：仍提交 `/v1/videos`，在 `metadata.video_list` 中放置一个参考片段；不使用 `/v1/videos/edits`。
- 无参考视频时，时长只允许 4、6、8 或 10 秒。编辑只允许一段不超过 10 秒的参考视频。

## 准备

默认 API 为 `https://newapi.1234bot.com/v1`。按 `--base-url`、`GEMINI_OMNI_VIDEO_BASE_URL`、`NEW_API_BASE_URL` 的顺序覆盖，不读取 `OPENAI_BASE_URL`。所有媒体 Skill 共用 `LOVBROWSER_API_KEY`，也可优先复用本地 `OPENAI_API_KEY`；忽略媒体专用 Key。

脚本显式使用 `akasha-gemini-omni-video/1.0` User-Agent。不要改回 Python urllib 默认标识；LovBrowser 入口已观察到 Cloudflare 1010 会在请求到达 new-api 前拦截默认 Python 签名。

## 生成

先用 4 秒、720p 做最小 smoke：

```bash
python3 skills/gemini-omni-video-generation/scripts/gemini_omni_video.py \
  --base-url https://llmapi.lovbrowser.com/v1 \
  generate \
  --prompt "A cobalt blue sphere slowly rotates in a clean studio, no text" \
  --duration 4 \
  --resolution 720p \
  --no-generate-audio \
  --output /tmp/gemini-omni-generated.mp4
```

只有任务到达成功终态、下载内容包含 MP4 `ftyp` 签名、`ffprobe` 识别到视频流，且实际短边分辨率与时长符合请求时才算跑通。脚本会在计费前确认 `ffprobe` 可用、输出后缀为 `.mp4` 且无覆盖冲突；只在明确需要时传 `--overwrite`。下载内容先写入同目录临时文件，验收通过后才原子替换最终输出。

## 编辑

参考素材必须是上游能访问的公开 HTTPS URL：

```bash
python3 skills/gemini-omni-video-generation/scripts/gemini_omni_video.py \
  edit \
  --reference-video https://media.example/source.mp4 \
  --start 0 \
  --end 4 \
  --prompt "Keep motion and composition; change only the blue sphere to coral red" \
  --resolution 720p \
  --output /tmp/gemini-omni-edited.mp4
```

如果参考素材是同一 new-api 密钥刚完成的任务，直接传公开任务 ID；脚本会确认任务已成功、模型为 `gemini-omni-video`，再读取 `metadata.url`，日志只显示宿主名：

```bash
python3 skills/gemini-omni-video-generation/scripts/gemini_omni_video.py \
  edit \
  --reference-task-id task_xxx \
  --prompt "Restyle the source as watercolor while preserving timing" \
  --start 0 \
  --end 4 \
  --output /tmp/gemini-omni-edited.mp4
```

在 prompt 中明确保留时序、镜头、构图、主体和禁止变更项。编辑是生成式重建，不保证像素级不变。

## 余额不足

用户明确要求充值时，直接在仓库根目录运行 `python3 shared/akasha_recharge.py --recharge-usd 金额`，不要先提交视频请求。仅官方 `https://newapi.1234bot.com/v1` 返回支持充值的 `insufficient_user_quota` 时，脚本才通过共享充值控制器生成一次充值会话，并在入账后只重试失败请求一次。收到 `akasha.recharge` 事件后，Agent 必须直接渲染 `qrPngPath` 并提供可点击的 `publicPageUrl`，不得显示 ticket、Key 或支付私链。契约见 [`shared/recharge-contract.md`](../../shared/recharge-contract.md)。

## 验收与已知行为

- 检查脚本输出的 `MEDIA codec`、`pixels`、`fps`、`duration` 和 `audio_streams`，再实际播放或抽帧查看。
- 分辨率按短边校验：720p→720、1080p→1080、4k→2160。时长允许最大 0.5 秒或 10% 容差；超出则不提交最终文件。
- `--no-generate-audio` 已观察到上游仍返回非静音 AAC 音轨。脚本会输出 `WARN unexpected_audio_stream`；不得宣称无音频。
- 轮询首次可能返回 `unknown`，随后变为 `queued` 和 `completed`。一次 `unknown` 不是失败，长时间不进展则按 `--poll-timeout` 失败。
- 不输出完整 provider 响应、参考素材临时 URL、凭证或支付授权 URL。

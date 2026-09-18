---
name: minimax-h3-lip-sync
description: 通过 LovBrowser new-api 的异步 OpenAI-compatible 视频任务端点调用 MiniMax H3 Max 对口型（lip-sync），把一张人物图片和一段音频合成嘴型对齐的说话视频。用户要求给图片对口型、让照片说话、把音频套到人物脸上、生成对口型视频、调用 minimax/h3-max/lip-sync/image-to-video 或 minimax-h3-lip-sync 时使用。
---

# MiniMax H3 Max 对口型

使用 `scripts/minimax_h3_lip_sync.py` 提交异步任务。真实任务会计费；未获用户授权时，仅运行 `--help`、单元测试或本地 mock。

## 契约

- 模型：`minimax/h3-max/lip-sync/image-to-video`（也接受 `fal-ai/minimax/h3-max/lip-sync/image-to-video`）
- 提交：`POST /v1/video/generations`，请求体为 `{model, images, audio_url, metadata}`；`audio_url` 同时写入 `metadata.reference_audio_urls` 让服务端解析真实音频时长做计费预估。任务时长由音频决定，不传 `duration`；音频最长 15 秒，超出自动截断。
- 轮询：`GET /v1/video/generations/{task_id}`。
- 下载：`GET /v1/videos/{task_id}/content`。

## 准备

默认 API 为 `https://newapi.1234bot.com/v1`。按 `--base-url`、`MINIMAX_H3_LIP_SYNC_BASE_URL`、`NEW_API_BASE_URL` 的顺序覆盖，不读取 `OPENAI_BASE_URL`。所有媒体 Skill 共用 `LOVBROWSER_API_KEY`，也可优先复用本地 `OPENAI_API_KEY`。

脚本显式使用 `akasha-minimax-h3-lip-sync/1.0` User-Agent；不要改回 Python urllib 默认标识。

## 生成

必须提供一张人物图片（`--image`，比例 0.4–2.5）和一段音频（`--audio`，公开 HTTPS，至少 5 秒）：

```bash
python3 skills/minimax-h3-lip-sync/scripts/minimax_h3_lip_sync.py \
  generate \
  --image https://media.example/portrait.png \
  --audio https://media.example/speech.mp3 \
  --resolution 768P \
  --output /tmp/lip-sync.mp4
```

`--resolution` 支持 `480P`、`768P`（默认）、`1080P`、`2K`。`--seed` 可选；`--no-transcription` 关闭音频转写引导；`--no-safety-checker` 关闭内容安全检查。

先用最短音频做 smoke：任务到达成功终态、下载内容含 MP4 `ftyp` 签名、`ffprobe` 识别到视频流、时长与音频时长匹配时才算跑通。

## 验收与已知行为

- 检查脚本输出的 `MEDIA codec`、`pixels`、`fps`、`duration`、`audio_streams`，再实际播放或抽帧确认嘴型同步。
- 时长由音频决定（5–15 秒自动截断），不按 `--duration` 校验；只验证时长与音频时长一致。
- 轮询首次可能返回 `unknown`，随后变为 `queued` / `completed`；长时间不进展按 `--poll-timeout` 失败。
- 不输出完整 provider 响应、参考素材临时 URL、凭证或支付授权 URL。

## 余额不足

用户明确要求充值时，直接在仓库根目录运行 `python3 shared/akasha_recharge.py --recharge-usd 金额`，不要先提交视频请求。仅官方 `https://newapi.1234bot.com/v1` 返回 `insufficient_user_quota` 时，脚本才通过共享充值控制器生成一次充值会话，并在入账后只重试失败请求一次。契约见 [`shared/recharge-contract.md`](../../shared/recharge-contract.md)。

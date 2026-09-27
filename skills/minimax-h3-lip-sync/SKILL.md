---
name: minimax-h3-lip-sync
description: 通过 LovBrowser new-api 的异步 OpenAI-compatible 视频任务端点调用 MiniMax H3 Max 对口型（lip-sync），把一张人物图片和一段音频合成嘴型对齐的说话视频。用户要求给图片对口型、让照片说话、把音频套到人物脸上、生成对口型视频、调用 minimax/h3-max/lip-sync/image-to-video 或 minimax-h3-lip-sync 时使用。
---

# MiniMax H3 Max 对口型

使用 `scripts/minimax_h3_lip_sync.py` 提交异步任务。真实任务会计费；未获用户授权时，仅运行 `--help`、单元测试或本地 mock。

## 契约

- 模型：`minimax/h3-max/lip-sync/image-to-video`（也接受 `fal-ai/minimax/h3-max/lip-sync/image-to-video`）
- 提交：`POST /v1/video/generations`，请求体为 `{model, images, audio_url, metadata}`；`audio_url` 同时写入 `metadata.reference_audio_urls` 让服务端解析真实音频时长做计费预估。没有 Prompt 和 `duration` 字段。
- 音频：至少 5 秒；超过 14.8 秒时只使用前 14.8 秒。输出时长等于截取后的音频时长，并带有这段音频作为音轨。
- 图片：一张人物图片，宽高比 0.4–2.5；输出使用与图片比例最接近的支持画幅，因此人物图片要按交付画幅准备。
- 轮询：`GET /v1/video/generations/{task_id}`。
- 下载：`GET /v1/videos/{task_id}/content`。

## 准备

默认 API 为 `https://newapi.1234bot.com/v1`。按 `--base-url`、`MINIMAX_H3_LIP_SYNC_BASE_URL`、`NEW_API_BASE_URL` 的顺序覆盖，不读取 `OPENAI_BASE_URL`。所有媒体 Skill 共用 `LOVBROWSER_API_KEY`，也可优先复用本地 `OPENAI_API_KEY`。

脚本显式使用 `akasha-minimax-h3-lip-sync/1.0` User-Agent；不要改回 Python urllib 默认标识。

## 准备音频

上传前先在本地确认时长：

```bash
ffprobe -v error -show_entries format=duration -of csv=p=0 /ABSOLUTE/speech.wav
```

- 短于 5 秒：在结尾补静音到 5 秒，例如 `ffmpeg -i speech.wav -af apad=whole_dur=5 speech-5s.wav`，剪辑时裁掉补出的静音。
- 长于 14.8 秒：在句间停顿处切成每段 5–14.8 秒的多段，逐段生成后按原顺序拼接。先用 `ffmpeg -i speech.wav -af silencedetect=noise=-35dB:d=0.35 -f null -` 找停顿，再用 `-ss`/`-to` 导出各段。每段都从同一张人物图片开始生成，交界处的姿态可能跳回图片中的姿态，剪辑时在交界处插入 B-roll、反应镜头或切换景别。
- 图片和音频都必须是任务期间可以匿名读取的 HTTPS URL。

## 生成

必须提供一张人物图片（`--image`，宽高比 0.4–2.5）和一段音频（`--audio`，公开 HTTPS，5–14.8 秒）：

```bash
python3 skills/minimax-h3-lip-sync/scripts/minimax_h3_lip_sync.py \
  generate \
  --image https://media.example/portrait.png \
  --audio https://media.example/speech.mp3 \
  --resolution 768P \
  --output /tmp/lip-sync.mp4
```

`--resolution` 支持 `480P`、`768P`（默认）、`1080P`、`2K`。`--seed` 固定随机种子，用于 A/B 对比；`--no-transcription` 关闭音频转写引导；`--no-safety-checker` 关闭内容安全检查。输出文件已存在时，脚本在提交任务前就报错，不会产生计费任务；确需替换时加 `--overwrite`。

先用 5–6 秒的音频做 smoke：任务到达成功终态、下载内容含 MP4 `ftyp` 签名、`MEDIA` 行识别到视频流和音轨、`duration` 与音频时长一致时才算跑通。

## 验收与已知行为

- 下载后脚本打印 `MEDIA codec=… pixels=… fps=… duration=… audio_streams=…`（未安装 ffprobe 或解析失败时打印 `MEDIA unavailable`），结果没有音轨时给出警告。
- 脚本在输出旁写入 `<output>.json`：任务 ID、模型、请求参数（媒体 URL 替换为 `<url omitted>`）、seed（优先取任务结果返回的值，否则记录 `--seed`）和媒体信息。
- 输出时长应约等于 `min(音频时长, 14.8)` 秒，明显不符时先核对上传的音频。之后实际播放或抽帧，确认嘴型同步。
- A/B 对比时用 `--seed` 固定 sidecar 中记录的 seed，每次只改一个变量（图片、音频或分辨率）。
- 轮询首次可能返回 `unknown`，随后变为 `queued` / `completed`；长时间不进展按 `--poll-timeout` 失败。
- 不输出完整 provider 响应、参考素材临时 URL、凭证或支付授权 URL。

## 余额不足

用户明确要求充值时，直接在仓库根目录运行 `python3 shared/akasha_recharge.py --recharge-usd 金额`，不要先提交视频请求。仅官方 `https://newapi.1234bot.com/v1` 返回 `insufficient_user_quota` 时，脚本才通过共享充值控制器生成一次充值会话，并在入账后只重试失败请求一次。契约见 [`shared/recharge-contract.md`](../../shared/recharge-contract.md)。

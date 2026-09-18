---
name: codex-live-voice
description: 通过 new-api 的 ChatGPT Codex gpt-live 渠道完成实时双工语音会话。上行音频走 WebRTC 媒体面（PCMU），下行音频和事件走 WebSocket。用于文本转语音（speakable context）、实时语音交互、低延迟 TTS、语音对话。用户要求 Codex 语音、gpt-live、实时语音、双工语音、live TTS、speakable、WebRTC 语音时使用。
---

# Codex Live Voice 双工语音

通过 new-api 的 Codex 渠道把 ChatGPT 的 gpt-live 语音双工模型暴露为 OpenAI-compatible WebRTC + WebSocket 接口。上行音频走 WebRTC RTP（PCMU 8000Hz），下行音频和会话事件走 WebSocket（PCM s16le 24kHz）。

## 前置条件

- new-api 实例上配置了 Codex 渠道，且 `CodexAudio.Enabled = true`
- 渠道模型列表包含 `gpt-live-1-boulder-alpha`
- 有效的 `LOVBROWSER_API_KEY`（或 `OPENAI_API_KEY`）
- Python 3.10+，运行时用 `uv run --with aiortc --with websockets` 提供 WebRTC 和 WebSocket 支持

需要核对 new-api 事件与字段映射时，读取 [references/new-api-contract.md](references/new-api-contract.md)。

## 接入 LovBrowser

没有 Key 时，入口调用共享 `shared/akasha_credentials.py` 进入 `AKASHA_DEVICE_V1` 流程。详见 [`akasha-key-setup`](../akasha-key-setup/SKILL.md) 与 [`credentials-contract.md`](../../shared/credentials-contract.md)。

余额不足时鉴权请求返回 `insufficient_user_quota`，走共享自动充值。详见 [`shared/recharge-contract.md`](../../shared/recharge-contract.md)。

## 两条路径

### speak：文本 → 语音

最简路径——不需要客户端麦克风。脚本创建 WebRTC call、加入 WS、发 speakable context append、录制下行 PCM 音频为 WAV：

```bash
uv run --with aiortc --with websockets \
  python3 scripts/codex_live_voice.py \
  --base-url https://llmapi-direct.lovbrowser.com/v1 \
  speak \
  --text "要念的文本内容" \
  --voice cove \
  --output ./staging/live-tts.wav
```

输出 JSON 含 `pcm_bytes`、`seconds`、`call_id`、`transcript`。

### probe：验证双工链路

```bash
uv run --with aiortc --with websockets \
  python3 scripts/codex_live_voice.py \
  --base-url https://llmapi-direct.lovbrowser.com/v1 \
  -v probe
```

打印每个收到的事件（不含 audio delta payload），验证 call create → WS join → session.started → input_audio.append echo → speakable append → output_audio.delta → turn.done。

## 参数

| 参数 | 说明 |
| --- | --- |
| `--base-url` | new-api 网关 URL，默认 `https://llmapi-direct.lovbrowser.com/v1`（43 产线直连入口） |
| `--voice` | 输出音色，默认 `cove`。可用值取决于上游 |
| `--instructions` | session 级指令，默认 "Speak the user's text exactly as written." |
| `--timeout` | speak 模式等待 turn.done 的最长秒数，默认 60 |
| `-v` / `--verbose` | 打印每个事件到 stderr |
| `--text` / `--text-file` | speak 模式要念的文本 |
| `--output` | speak 模式 WAV 输出路径 |

## 协议要点

- **上行音频必须走 WebRTC**：客户端 SDP offer 里 `m=audio` 至少有一个发送轨（PCMU 8000Hz 即可，静音也行）。没有上行 RTP，speakable context 不会被念出来。
- **speakable channel**：`session.context.append` + `channel:"speakable"` 让 assistant 逐字念出 content 文本。不需要 `response.create` 或 `turn.create`。
- **下行音频**：`session.output_audio.delta` 是连续时间线（含静音填充），`delta` = base64 PCM s16le 24kHz mono。从首个非零 chunk 截取语音。
- **session model**：客户端用 `gpt-live-1-boulder-alpha`，网关自动映射成上游的 `gpt-live-1-codex`。

## 验收

1. `call create` 返回 201 + `Location: /v1/live/{call_id}` + SDP answer
2. WS 握手 101，收到 `session.started`
3. 上行 RTP 启动后收到 `session.input_audio.append` 回显
4. speakable append 后收到 `session.output_audio.delta`（非零 PCM）和 transcript 增量
5. WAV 文件非空且时长合理（PCM 字节 / 48000 = 秒数）
6. `session.usage.updated` 触发计费增量

## 边界

- 纯 WS 客户端只能收不能发——上行音频必须走 WebRTC 媒体面
- `delegation.type` 仅支持 `client`；`responses` 委派不可用（内部 tasksapi 对 OAuth 回 401）
- 不做音频重编码：上行 PCMU 8000 固定、下行 PCM 24kHz 固定
- 同一 call_id 的 WS 和 WebRTC 必须来自同一渠道（affinity 保证）

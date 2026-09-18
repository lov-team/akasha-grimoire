# new-api gpt-live 双工语音对接文档

面向第三方接入方。通过 new-api 网关调用 ChatGPT Codex 的 `gpt-live` 实时双工语音模型。

- **网关 Base URL**：`https://newapi.1234bot.com/v1`
- **模型名**：`gpt-live-1-boulder-alpha`
- **认证**：`Authorization: Bearer <new-api 令牌>`
- **能力**：文本转语音（TTS）、实时语音交互、低延迟双工语音会话

## 架构

```
客户端 --[HTTP multipart]--> POST /v1/realtime/calls   (创建呼叫, SDP offer/answer)
客户端 --[WebRTC RTP]-----> 媒体面                      (上行音频 PCMU 8000Hz)
客户端 <--[WebSocket]------ GET /v1/live/{call_id}     (事件 + 下行音频 PCM 24kHz)
```

三个面缺一不可：
- **呼叫创建**（HTTP）：提交 WebRTC SDP offer，拿回 SDP answer + `call_id`
- **媒体面**（WebRTC）：上行音频必须走 RTP，格式 PCMU 8000Hz
- **事件面**（WebSocket）：下行音频、转写、会话控制全走这条

## 第一步：创建呼叫

`POST /v1/realtime/calls`，`Content-Type: multipart/form-data`，两个字段：

| 字段 | 内容 | 说明 |
| --- | --- | --- |
| `sdp` | WebRTC SDP offer | `application/sdp`。**必须保留结尾 CRLF**，否则上游报 `unmarshal SDP: EOF` |
| `session` | JSON 字符串 | 见下 |

`session` 字段示例：

```json
{
  "model": "gpt-live-1-boulder-alpha",
  "instructions": "Speak the user's text exactly as written.",
  "audio": { "output": { "voice": "cove" } }
}
```

网关会自动：剥掉 `id`/`type`、把 `gpt-live-1-boulder-alpha` 映射为上游模型、补 `delegation:{type:"client"}`、加 `openai-alpha: quicksilver=v2`。

成功响应 `201`：
- Header `Location: /v1/live/rtc_xxx` → `call_id`
- Body 是 SDP answer（`application/sdp`），用它 `setRemoteDescription`

## 第二步：建立媒体面（上行音频）

用 SDP answer 完成 WebRTC 握手。offer 里 `m=audio` 必须至少有一条发送轨（PCMU 8000Hz，静音也行）。

> 没有上行 RTP，后面的 speakable 文本不会被念出来。上游以 `session.input_audio.append` 回显证明音频已入管。

## 第三步：接入事件通道

```
GET wss://newapi.1234bot.com/v1/live/{call_id}
Authorization: Bearer <token>
```

upgrade 到上游 `wss://api.openai.com`。收到 `session.started` 即就绪。

## 事件协议

### 客户端 → 网关

| 事件 | 用途 |
| --- | --- |
| `session.context.append` + `channel:"speakable"` | 让 assistant 逐字念出文本（TTS 化）。**前提：上行 RTP 已在跑** |
| `session.update` | 改 session 配置 |
| `session.close` | 结束会话 |

speakable 示例：

```json
{
  "type": "session.context.append",
  "channel": "speakable",
  "content": [{ "type": "input_text", "text": "要念的文本" }]
}
```

> 上行音频只能走 WebRTC RTP。`input_audio_buffer.append` 这类 WS 音频事件会被上游拒绝。

### 网关 → 客户端

| 事件 | 说明 |
| --- | --- |
| `session.started` | 会话就绪，可以开始 speakable append |
| `session.input_audio.append` | 上行 RTP 入管回显（`audio` = base64 PCMU） |
| `session.output_audio.delta` | **下行语音主通道**，`delta` = base64 PCM s16le 24kHz mono；空闲时为全零流 |
| `output_transcript.added` / `turn.delta` / `turn.created` / `turn.done` | 转写增量与 turn 生命周期 |
| `session.context.appended` | context append 确认 |
| `session.usage.updated` | 累计 `audio_duration_ms`（计费增量） |
| `error` | 错误事件 |

**下行音频**固定 PCM s16le 24kHz mono，不需要解码器。`pcm_bytes / 48000 = 秒数`。`output_audio.delta` 是连续时间线（含静音填充），从首个非零 chunk 截取语音。

## 最快验证（参考脚本）

akasha repo 里有可直接运行的参考客户端（Python 3.10+，`uv` 自动装 aiortc + websockets）：

```bash
export OPENAI_API_KEY=sk-xxxx

# speak：文本 → WAV
uv run --with aiortc --with websockets \
  python3 codex_live_voice.py \
  --base-url https://newapi.1234bot.com/v1 \
  speak --text "要念的文本" --voice cove --output out.wav

# probe：验证链路，打印每个事件
uv run --with aiortc --with websockets \
  python3 codex_live_voice.py \
  --base-url https://newapi.1234bot.com/v1 -v probe
```

成功标志：`call create` 返回 201 → WS 101 → `session.started` → 上行 RTP 回显 → speakable 后收到非零 `output_audio.delta` + transcript 增量 → `turn.done`。

## 参数

| 参数 | 说明 |
| --- | --- |
| `--base-url` | 网关 URL，默认 `https://newapi.1234bot.com/v1` |
| `--voice` | 输出音色，默认 `cove`（可用值取决于上游） |
| `--instructions` | session 级指令 |
| `--timeout` | 等待 turn.done 上限秒数，默认 60 |

## 计费

- `session.usage.updated` 的 `audio_duration_ms` 增量按音频输入价计费
- 会话关闭时尾部未计费时长按墙钟兜底（封顶 60s）
- `gpt-live-1-boulder-alpha` 定价：model_ratio 2 / completion_ratio 4 / audio_ratio 8 / audio_completion_ratio 2

## 边界与注意

- 纯 WS 客户端只能收（下行音频+事件），**上行必须走 WebRTC 媒体面**
- `delegation.type` 仅支持 `client`；`responses` 委派不可用
- 网关透传不重编码：上行 PCMU 8000 固定、下行 PCM 24kHz 固定
- 同一 `call_id` 的 WS 和 WebRTC 必须在同一渠道（affinity 保证）
- `output_transcript` 会同时从 WebSocket 和 WebRTC data-channel 各来一份，按需要去重

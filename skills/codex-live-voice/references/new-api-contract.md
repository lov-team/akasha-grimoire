# new-api Codex Live Voice 事实合同

事实源：`new-api` commit `492029e64`（`fix(codex): harden gpt-live duplex relay edge cases`）及以上，ChatGPT Codex 后端 `backend-api/codex/realtime/calls` 实测。

## 入口与模型

| 能力 | 方法与路径 | 模型 |
| --- | --- | --- |
| 创建双工呼叫 | `POST /v1/realtime/calls` (multipart) | `gpt-live-1-boulder-alpha` |
| 加入事件通道 | `GET /v1/live/{call_id}` (WebSocket upgrade) | 同上 |

认证：`Authorization: Bearer <new-api token>`。呼叫创建和 WS 加入都走 TokenAuth + Distribute。

## 呼叫创建

`POST /v1/realtime/calls`，`Content-Type: multipart/form-data`，两个字段：

- `sdp`：客户端 WebRTC SDP offer（`application/sdp`）。**必须保留结尾 CRLF**——网关原样透传，上游解析器对截断的 SDP 报 `unmarshal SDP: EOF`。
- `session`：JSON 字符串，含 `model`、`instructions`、`audio.output.voice`、可选 `delegation`。网关 `NormalizeRealtimeSession` 会剥 `id`/`type`、把 `gpt-live-1-boulder-alpha` 映射成上游接受的 `gpt-live-1-codex`、补 `delegation:{type:"client"}`。

成功响应 `201`，`Location: /v1/live/{call_id}`（`rtc_xxx`），body 为 SDP answer。`openai-alpha: quicksilver=v2` 由网关在 session model 为 gpt-live 时自动补。

## WebSocket 事件通道

`GET wss://<gateway>/v1/live/{call_id}`，upgrade 到 `wss://api.openai.com`。

### 客户端 → 网关事件

| 事件 | 用途 |
| --- | --- |
| `session.context.append` + `channel: "speakable"` | 让 assistant 逐字念出文本（TTS 化）；**前提是上行 RTP 已在跑**（上游以 `session.input_audio.append` 回显证明入管） |
| `session.update` | 修改 session 配置 |
| `session.close` | 结束会话 |

**上行音频只能走 WebRTC RTP 媒体面**（PCMU 8000Hz）。`input_audio_buffer.append` 等 WS 音频事件会被上游拒绝。

### 网关 → 客户端事件

| 事件 | 说明 |
| --- | --- |
| `session.started` | 会话就绪，可开始 append speakable context |
| `session.input_audio.append` | 上行 RTP 入管回显（`audio` = base64 PCMU） |
| `session.output_audio.delta` | **下行语音主通道**，`delta` = base64 PCM s16le 24kHz mono；空闲时为全零流 |
| `output_transcript.added` / `turn.delta` / `turn.created` / `turn.done` | 转录与 turn 生命周期；部分会话只流转录增量不发 `turn.*` |
| `session.context.appended` | context append 确认 |
| `session.usage.updated` | 累计 `audio_duration_ms`（网关按增量计费） |
| `error` | 错误事件 |

下行音频格式固定为 **PCM s16le 24kHz mono**，不需要解码器。PCM 字节数 / 48000 = 秒数。

## 计费

- `session.usage.updated` 的 `audio_duration_ms` 增量按音频输入价计费（`audio_ratio` × `group_ratio`）
- 会话关闭时尾部未计费时长按墙钟兜底（首个音频标记 − 最后上报 meter），封顶 60s
- `gpt-live-1-boulder-alpha` 定价在 `setting/ratio_setting/model_ratio.go`：model_ratio 2、completion_ratio 4、audio_ratio 8、audio_completion_ratio 2

## 边界

- 纯 WS 客户端只能收（下行音频+事件），上行必须走 WebRTC 媒体面
- `delegation.type` 仅支持 `client`；`responses` 委派需要 `responses.model` 且内部 tasksapi 对 OAuth 回 401，不可用
- 网关透传不做音频重编码；上行 PCMU 8000、下行 PCM 24kHz 固定
- `session.output_audio.delta` 是连续输出时间线（含静音填充），不是仅在有语音时发送

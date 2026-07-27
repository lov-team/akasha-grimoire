# new-api Fish Audio 事实合同

事实源：`new-api` 当前实现（审计提交 `2a6cba7c`）的音频路由、Fish Audio adaptor、模型表与测试。

## 客户端入口与模型

| 能力 | 方法与路径 | 当前模型 |
| --- | --- | --- |
| TTS | `POST /v1/audio/speech` | `fish-s2-pro`、`fish-s1` |
| STT/ASR | `POST /v1/audio/transcriptions` | `fish-transcribe-1` |

认证使用 `Authorization: Bearer <new-api token>`。目标 new-api 环境必须已经配置 Fish Audio 渠道并开放相应模型。

## TTS 客户端请求

OpenAI-compatible JSON 字段：

- `model`：Fish TTS 模型；
- `input`：待合成文本；
- `voice`：Fish Audio `reference_id`；
- `response_format`：当前脚本支持 `mp3`、`wav`、`opus`；
- `extra_body.references`：可选参考数组，每项含 base64 `audio` 与准确对应的 `text`。

new-api 将其转换为 Fish Audio `/v1/tts`，并通过 `model` header 传 `s2-pro` 或 `s1`。成功响应是音频字节，不是 JSON。

## 公开参考音色检索

公开音色目录可通过 `GET https://api.fish.audio/model` 查询，不经过 new-api，也不需要 new-api token。当前脚本使用 `title` 和 `page_size` 查询，并在本地再次检查：

- `type=tts`；
- `state=trained`；
- `visibility=public`；
- `dmca_taken_down` 不为真；
- 可选语言、标签和最低使用次数。

响应 `items[*]._id` 就是 TTS 请求的 `voice/reference_id`。公开可检索只代表平台允许调用，不等于可以声称某位现实人物为项目背书；正式使用前仍需人工试听和内容适配。

## STT 客户端请求

`multipart/form-data` 字段：

- `file`：本地音频；
- `model=fish-transcribe-1`；
- `language`：可选；
- `ignore_timestamps`：可选布尔值。

new-api 转换后请求 Fish Audio `/v1/asr`，上游文件字段名为 `audio`。客户端成功响应遵循 OpenAI 转写 JSON，至少应有字符串 `text`。

## 边界

- `fish-voice-design-1` 虽存在于当前渠道模型表，但不属于本 Skill 的 TTS/STT 合同。
- 不在日志中输出 token、参考音频 base64 或完整敏感转写。
- TTS 返回 JSON、空音频或 STT 缺少字符串 `text` 时不得输出成功。
- 不硬编码生产 base URL、渠道 id、Fish API key 或 new-api token。

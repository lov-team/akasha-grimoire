---
name: fish-audio-speech
description: 通过 new-api 的 OpenAI-compatible 音频入口调用 Fish Audio 完成 TTS 语音合成与 STT/ASR 语音转写，支持参考 voice、参考音频、输出格式、语言和时间戳控制，并安全落盘验收。用户要求 Fish Audio 配音、文本转语音、声音克隆参考、音频转文字、录音转写或字幕底稿时使用。
---

# Fish Audio TTS 与 STT

只覆盖语音合成和语音转写。不要把 voice design、实时流式语音或其他 provider 能力混入当前合同。

## 选择路径

- TTS：文本 → 音频。使用已有 `reference_id`，或同时提供本地参考音频与对应文本。
- STT：音频 → 文本。可选指定语言；只有确实不需要时间戳时才传 `--ignore-timestamps`。

需要核对 new-api 与 Fish Audio 的字段映射时，读取 [references/new-api-contract.md](references/new-api-contract.md)。

## 运行 TTS

设置 `NEW_API_API_KEY`（也兼容 `OPENAI_API_KEY`）和 `NEW_API_BASE_URL`（也兼容 `OPENAI_BASE_URL`）：

```bash
# 使用已有 voice/reference id
python3 scripts/fish_audio.py tts \
  --text "欢迎来到今天的节目。" \
  --voice <reference-id> \
  --output ./staging/narration.mp3

# 使用本地参考音频
python3 scripts/fish_audio.py tts \
  --text-file ./script.txt \
  --reference-audio ./reference.wav \
  --reference-text "参考音频中准确对应的文字" \
  --output ./staging/narration.wav \
  --format wav
```

默认模型为 `fish-s2-pro`。只有项目合同明确时才改为 `fish-s1`。参考音频与参考文本必须语义对应；不要上传没有授权的声音样本。

## 运行 STT

```bash
python3 scripts/fish_audio.py stt ./recording.mp3 \
  --language zh \
  --output ./staging/transcript.txt \
  --json-output ./staging/transcript.json
```

默认模型为 `fish-transcribe-1`。脚本通过 multipart 上传音频；完成前不打印转写正文，避免大段内容进入主 Agent 上下文。

## 验收

TTS：

1. 文件必须非空，且响应不是伪装成成功的 JSON 错误。
2. 播放开头、中段、结尾，检查发音、语言、数字、专有名词、停顿和截断。
3. 与参考声音比较音色时，同时关注清晰度和内容准确性；声音相似不能替代文本正确。

STT：

1. 核对完整文本存在，JSON 中 `text` 字段类型正确。
2. 抽查开头、中段、结尾以及人名、数字、术语和混合语言。
3. 音频质量差、多人重叠或语言不确定时，明确标注人工复核范围。

API key、参考音频 base64、签名 URL 和完整敏感转写不得进入日志。真实调用会消耗额度；基础验证只运行本地无网络测试。

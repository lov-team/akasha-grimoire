---
name: fish-audio-speech
description: 通过 new-api 的 OpenAI-compatible 音频入口调用 Fish Audio 完成 TTS 语音合成与 STT/ASR 语音转写，支持参考 voice、参考音频、输出格式、语言和时间戳控制，并安全落盘验收。用户要求 Fish Audio 配音、文本转语音、声音克隆参考、音频转文字、录音转写或字幕底稿时使用。
---

# Fish Audio TTS 与 STT

只覆盖语音合成和语音转写。不要把 voice design、实时流式语音或其他 provider 能力混入当前合同。

## 选择路径

- 公开参考音色：先检索 Fish Audio 的公开 TTS 模型，取得可审计的 `reference_id`，再做短句 smoke。
- TTS：文本 → 音频。优先使用公开或已获授权的 `reference_id`；也可同时提供本地授权参考音频与对应文本。
- STT：音频 → 文本。可选指定语言；只有确实不需要时间戳时才传 `--ignore-timestamps`。

需要核对 new-api 与 Fish Audio 的字段映射时，读取 [references/new-api-contract.md](references/new-api-contract.md)。

## 先找公开参考音色

检索公开音色不需要 API key。先用中文用途词搜索，再根据语言、标签、使用数和试听结果缩小范围：

```bash
python3 scripts/fish_audio.py voices \
  --query "旁白" \
  --language zh \
  --min-uses 100 \
  --limit 10 \
  --json-output ./staging/fish-voices.json
```

输出中的 `reference_id` 可直接传给 TTS。筛选时必须确认 `visibility=public`、`state=trained`、未被 DMCA 下架；脚本已自动排除不满足条件的结果。标题和标签只能作为初筛，正式长文合成前仍要试听 8—15 秒 smoke。不要因为声音“像某人”就把公开音色描述成该真人授权音色。

## 跑通 TTS smoke

设置 `NEW_API_API_KEY`（也兼容 `OPENAI_API_KEY`）和 `NEW_API_BASE_URL`（也兼容 `OPENAI_BASE_URL`）：

```bash
# 先用含人名、术语和标点停顿的短句 smoke
python3 scripts/fish_audio.py tts \
  --text "邓煜获得菲尔兹奖；钱徐预研究脑类器官。" \
  --voice <reference-id> \
  --format wav \
  --output ./staging/fish-smoke.wav

# 立即用 Fish STT 回验内容是否完整
python3 scripts/fish_audio.py stt ./staging/fish-smoke.wav \
  --language zh \
  --output ./staging/fish-smoke.txt \
  --json-output ./staging/fish-smoke.json

# 使用本地参考音频
python3 scripts/fish_audio.py tts \
  --text-file ./script.txt \
  --reference-audio ./reference.wav \
  --reference-text "参考音频中准确对应的文字" \
  --output ./staging/narration.wav \
  --format wav
```

默认模型为 `fish-s2-pro`。只有项目合同明确时才改为 `fish-s1`。参考音频与参考文本必须语义对应；不要上传没有授权的声音样本。

smoke 的音色、停顿、专有名词和 STT 都通过后，再用同一 `reference_id` 合成长文：

```bash
python3 scripts/fish_audio.py --timeout-seconds 300 tts \
  --text-file ./narration.txt \
  --voice <reference-id> \
  --model fish-s2-pro \
  --format wav \
  --output ./staging/narration-fish.wav
```

全流程的判定顺序是：公开音色记录可用 → smoke 音频非空 → 人工试听自然 → Fish STT 内容完整 → 长文合成 → 长文再次 STT。任何一步失败都不要静默回退到系统 TTS。

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

1. 记录实际使用的模型、公开参考音色名称与 `reference_id`；不得记录 API key。
2. 文件必须非空，且响应不是伪装成成功的 JSON 错误。
3. 播放开头、中段、结尾，检查发音、语言、数字、专有名词、停顿和截断。
4. 与参考声音比较音色时，同时关注清晰度和内容准确性；声音相似不能替代文本正确。

STT：

1. 核对完整文本存在，JSON 中 `text` 字段类型正确。
2. 抽查开头、中段、结尾以及人名、数字、术语和混合语言。
3. 音频质量差、多人重叠或语言不确定时，明确标注人工复核范围。

API key、参考音频 base64、签名 URL 和完整敏感转写不得进入日志。真实调用会消耗额度；基础验证只运行本地无网络测试。

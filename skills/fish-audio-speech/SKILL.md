---
name: fish-audio-speech
description: 通过 new-api 调用 Fish Audio 完成 TTS、STT、私人声线克隆与管理，并搜索公开人物/角色声线、绑定角色声线和按角色配音。用户要求 Fish Audio 配音、指定人物或角色声音、搜索声线、声音克隆、参考音频、音频转文字、录音转写或字幕底稿时使用。
---

# Fish Audio 语音能力

覆盖语音合成、语音转写、公开声线搜索、角色绑定和经授权的私人声线克隆。不要把 voice design、实时流式语音或其他 provider 能力混入当前合同。

## 选择路径

- 公开参考音色：先检索公开 TTS 模型，取得可审计的 `reference_id`，再做短句 smoke。
- 指定人物或角色：以名字搜索公开声线，试听多个候选后绑定角色；标题和标签不能证明真人身份或授权。
- 私人声线：只上传已获授权的样本，通过 new-api 创建 `private` 声线，等待 `state=trained` 后再绑定。
- TTS：文本 → 音频。使用公开、私人或显式绑定角色的 `reference_id`，也可提供单次参考音频与对应文本。
- STT：音频 → 文本。可选指定语言；只有确实不需要时间戳时才传 `--ignore-timestamps`。

需要核对 new-api 与 Fish Audio 的字段映射时，读取 [references/new-api-contract.md](references/new-api-contract.md)。

## 搜索公开声线

按用途搜索：

```bash
python3 scripts/fish_audio.py voices \
  --query "旁白" \
  --language zh \
  --min-uses 100 \
  --limit 10 \
  --json-output ./staging/fish-voices.json
```

按特定人物或角色名称搜索：

```bash
python3 scripts/fish_audio.py voices \
  --character "角色名或人物名" \
  --language zh \
  --limit 10 \
  --json-output ./staging/character-voices.json
```

脚本自动排除非 TTS、未训练完成、非公开或已被 DMCA 下架的结果。标题和标签只能作为初筛；正式配音前生成 8—15 秒试听，比较多个候选。不要因为声音“像某人”就把公开音色描述成该真人授权音色。

## 克隆并管理私人声线

只处理用户明确授权的声音样本。创建入口固定为私人可见；不要上传真人、演员或配音员的未授权素材。

```bash
python3 scripts/fish_audio.py clone \
  --title "我的授权角色声线" \
  --audio ./reference-1.wav \
  --text "第一段音频准确对应的文字" \
  --json-output ./staging/private-voice.json

python3 scripts/fish_audio.py clone-status <reference-id> \
  --json-output ./staging/private-voice-status.json

python3 scripts/fish_audio.py clone-delete <reference-id> --confirm-delete
```

多份样本重复传 `--audio`，最多 10 份；提供文本时必须为每份样本重复传一次 `--text`。只有 `state=trained` 才进入正式配音。重复写入同一个状态文件时，将全局 `--overwrite` 放在子命令前，例如 `fish_audio.py --overwrite clone-status ...`。

## 绑定角色并配音

用显式 registry 保存“角色 → reference_id”，避免每次重新搜索。registry 不得保存 API key 或参考音频。

```bash
python3 scripts/fish_audio.py bind \
  --character "守夜人" \
  --voice <reference-id> \
  --title "低沉克制候选 2" \
  --registry ./voices.json

python3 scripts/fish_audio.py tts \
  --character "守夜人" \
  --registry ./voices.json \
  --text-file ./script.txt \
  --format wav \
  --output ./staging/守夜人.wav
```

也可设置 `FISH_AUDIO_VOICE_REGISTRY` 作为默认 registry。绑定前必须完成候选试听；同一角色正式长文使用同一绑定，除非用户明确要求换声线。

## 跑通 TTS smoke

设置 `NEW_API_API_KEY`（也兼容 `OPENAI_API_KEY`）和 `NEW_API_BASE_URL`（也兼容 `OPENAI_BASE_URL`）：

```bash
python3 scripts/fish_audio.py tts \
  --text "邓煜获得菲尔兹奖；钱徐预研究脑类器官。" \
  --voice <reference-id> \
  --format wav \
  --output ./staging/fish-smoke.wav

python3 scripts/fish_audio.py stt ./staging/fish-smoke.wav \
  --language zh \
  --output ./staging/fish-smoke.txt \
  --json-output ./staging/fish-smoke.json
```

使用本地单次参考音频时，同时提供准确对应的 `--reference-text`。默认 TTS 模型为 `fish-s2-pro`；只有项目合同明确时才改为 `fish-s1`。

smoke 的音色、停顿、专有名词和 STT 都通过后，再用同一 `reference_id` 或角色绑定合成长文。任何一步失败都不要静默回退到系统 TTS。

## 运行 STT

```bash
python3 scripts/fish_audio.py stt ./recording.mp3 \
  --language zh \
  --output ./staging/transcript.txt \
  --json-output ./staging/transcript.json
```

默认模型为 `fish-transcribe-1`。完成前不打印转写正文，避免大段内容进入主 Agent 上下文。

## 验收

TTS 与声线：

1. 记录模型、声线名称、`reference_id` 与角色绑定；不得记录 API key。
2. 文件必须非空，且响应不是伪装成成功的 JSON 错误。
3. 播放开头、中段、结尾，检查发音、语言、数字、专有名词、停顿和截断。
4. 私人声线记录授权来源与训练状态，但不复制原始样本到日志或 registry。
5. 声音相似不能替代内容正确，也不能证明真人授权。

STT：

1. 核对完整文本存在，JSON 中 `text` 字段类型正确。
2. 抽查开头、中段、结尾以及人名、数字、术语和混合语言。
3. 音频质量差、多人重叠或语言不确定时，明确标注人工复核范围。

API key、参考音频 base64、签名 URL 和完整敏感转写不得进入日志。真实调用会消耗额度；基础验证只运行本地无网络测试。

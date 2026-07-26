---
name: suno-music-generation
description: 通过 new-api 的 Suno 异步任务接口生成歌曲，在本地进程中静默轮询直至成功、失败或超时，并安全下载音频、封面和可选视频。用户要求用 Suno 创作歌曲、把歌词或歌曲描述生成音乐、制作纯音乐、等待 Suno 任务或下载验收生成结果时使用。
---

# Suno 歌曲生成

把“提交、等待、下载、验收”作为一个闭环，不把异步轮询交给主 Agent 高频执行。

## 准备合同

1. 明确采用歌曲描述还是自定义歌词；二者只选一种。
2. 自定义歌词模式必须同时提供标题和风格；描述模式不要伪装成歌词模式。
3. 默认让 new-api 决定上游 Suno 版本；只有用户或项目合同明确模型时才传 `--model`。
4. 确认输出目录和覆盖策略。不要把 API key 写入参数、日志、仓库或交付文件。
5. 需要核对端点、字段或状态时，读取 [references/new-api-contract.md](references/new-api-contract.md)。

## 运行闭环

设置 `NEW_API_API_KEY`（也兼容 `OPENAI_API_KEY`）和 `NEW_API_BASE_URL`（也兼容 `OPENAI_BASE_URL`），然后运行：

```bash
# 描述模式
python3 scripts/suno_music.py \
  --description "一首温暖克制的中文城市民谣，女声，木吉他与轻鼓" \
  --output-dir ./staging/suno

# 自定义歌词模式
python3 scripts/suno_music.py \
  --lyrics-file ./lyrics.txt \
  --title "夜航" \
  --style "Mandopop, synthwave, female vocal" \
  --output-dir ./staging/suno
```

脚本默认在自身进程内每 5 秒检查一次，最长等待 20 分钟；完成前不输出轮询流水账。它只在成功下载、任务失败或整体超时时返回摘要。宿主若先返回运行 session，使用宿主支持的最长等待续接，不要由主 Agent 每 5 秒查询。

按需使用：

- `--instrumental`：生成纯音乐；
- `--model <id>`：仅在已有事实合同指定模型时使用；
- `--timeout-seconds`、`--poll-seconds`：调整本地等待窗口；
- `--download-video`：结果提供视频时一并下载；
- `--no-cover`：不下载封面；
- `--overwrite`：明确允许覆盖既有文件。

## 验收

脚本退出 0 后：

1. 核对实际下载数量与最终摘要一致，文件非空。
2. 播放每个音频的开头、中段和结尾，检查是否损坏、是否突然截断。
3. 对照描述或歌词检查语言、演唱、人声/纯音乐、风格和情绪。
4. 多结果任务逐个验收，不要只听第一首。
5. 封面与视频属于辅助结果；音频可播放且符合合同才是歌曲交付成立的核心证据。

任务失败、超时、结果缺少 `audio_url`、结果 URL 使用非 HTTP(S) 协议或下载内容为空时，不得宣称成功。保留 task id 供同一任务诊断，不回显签名 URL。

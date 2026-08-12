---
name: suno-music-generation
description: 通过 new-api 的 Suno 异步任务接口生成歌曲，在本地进程中静默轮询直至成功、失败或超时，并安全下载音频、封面和可选视频。用户要求用 Suno 创作歌曲、把歌词或歌曲描述生成音乐、制作纯音乐、等待 Suno 任务或下载验收生成结果时使用。
---

# Suno 歌曲生成

把“提交、等待、下载、验收”作为一个闭环，不把异步轮询交给主 Agent 高频执行。

## 准备合同

1. 明确采用歌曲描述还是自定义歌词；二者只选一种。
2. 自定义歌词模式必须同时提供标题和风格；描述模式不要伪装成歌词模式。
3. 当前 Kie 音乐生成文档的最新模型为 `V5_5`，脚本默认显式传入它；只有目标环境明确由服务端选择模型时才传 `--model server-default`。
4. 确认输出目录和覆盖策略。不要把 API key 写入参数、日志、仓库或交付文件。
5. 需要核对端点、字段或状态时，读取 [references/new-api-contract.md](references/new-api-contract.md)。

没有 Key 时，入口会调用共享 `shared/akasha_credentials.py` 进入 `AKASHA_DEVICE_V1`：在对话中渲染本地 PNG 二维码，同时显示可点击链接和短码，用户确认后自动轮询、原子保存、以 `/v1/models` 验证，并让原动作继续一次。不要显示 device code、PKCE verifier、真实 Key 或凭证文件内容。详见 [`akasha-key-setup`](../akasha-key-setup/SKILL.md) 与 [`credentials-contract.md`](../../shared/credentials-contract.md)。

用户明确要求充值时，直接在仓库根目录运行 `python3 shared/akasha_recharge.py`，不要先提交音乐请求。官方 new-api 在提交或轮询阶段返回可充值的余额不足时，会自动创建 LovBrowser 支付页面。**整次命令最多一次充值**；只重试该失败请求一次（不会重复提交已成功的任务）。默认 1 USD；支持 `AKASHA_RECHARGE_USD` 与 `--recharge-usd`。收到 `akasha.recharge` 后，Codex 只给出可点击的 `publicPageUrl`，不显示二维码；金额由用户在页面选择。详见 [`shared/recharge-contract.md`](../../shared/recharge-contract.md)。

## 运行闭环

设置 `LOVBROWSER_API_KEY`（也兼容 `OPENAI_API_KEY`），默认 Base URL 无需配置，然后运行：

```bash
# 描述模式
python3 scripts/suno_music.py \
  --description "温暖克制的人文纪录片配乐，极简钢琴、柔和氛围弦乐、无鼓点高潮，留出清晰旁白空间" \
  --instrumental \
  --model V5_5 \
  --output-dir ./staging/suno

# 自定义歌词模式
python3 scripts/suno_music.py \
  --lyrics-file ./lyrics.txt \
  --title "夜航" \
  --style "Mandopop, synthwave, female vocal" \
  --model V5_5 \
  --output-dir ./staging/suno
```

脚本默认在自身进程内每 5 秒检查一次，最长等待 20 分钟；完成前不输出轮询流水账。它只在成功下载、任务失败或整体超时时返回摘要。宿主若先返回运行 session，使用宿主支持的最长等待续接，不要由主 Agent 每 5 秒查询。

按需使用：

- `--instrumental`：生成纯音乐；
- `--model <id>`：默认 `V5_5`；若接口返回 HTTP 400，先核对目标渠道实际支持的模型，而不是反复重试同一请求；
- `--model server-default`：明确要求省略 `mv`，让目标 new-api 环境自行选择版本；
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

用于视频配乐时，还要额外检查前 90 秒而不是只听整首开头：测量该区间响度与峰值，确认没有突然进入人声或高潮；混入成片时可先把音乐控制在约 -25～-22 LUFS，再用旁白做侧链压缩，最后试听“说话段”和“停顿段”的可听度，不能只凭“音轨存在”宣称配乐完成。

任务失败、超时、结果缺少 `audio_url`、结果 URL 使用非 HTTP(S) 协议或下载内容为空时，不得宣称成功。HTTP 400 且省略 `mv` 时，优先显式重试当前文档最新的 `--model V5_5`；已显式使用 `V5_5` 仍失败则停止并核对渠道模型。保留 task id 供同一任务诊断，不回显签名 URL。

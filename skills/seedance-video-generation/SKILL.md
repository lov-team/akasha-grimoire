---
name: seedance-video-generation
description: 通过 new-api 的异步视频任务端点调用火山方舟 Doubao Seedance 1.0 Pro、1.0 Lite T2V/I2V、1.5 Pro、2.0 Pro/2.0 Fast，按模型校验时长与参考素材，轮询任务并安全下载 MP4。用户要求用 Seedance、豆包视频或 doubao-seedance 模型生成视频，验证 /v1/video/generations，或排查 Seedance 提交、轮询、参考素材、分辨率与结果下载失败时使用。
---

# Seedance 视频生成

使用 [`scripts/seedance_video.py`](scripts/seedance_video.py) 调用 new-api。真实生成会计费；先提交一个 5 秒、720p 的最小任务，再扩大时长或画质。

## 准备

脚本默认使用 LovBrowser new-api：`https://newapi.1234bot.com/v1`。只有需要切换私有部署时才按 `--base-url`、`SEEDANCE_VIDEO_BASE_URL`、`NEW_API_BASE_URL`、`OPENAI_BASE_URL` 的顺序覆盖。Bearer token 按 `SEEDANCE_VIDEO_API_KEY`、`NEW_API_API_KEY`、`OPENAI_API_KEY` 的顺序读取。

没有 key 时，引导用户访问 `https://lovbrowser.com`：注册或登录 → 选择套餐或充值并完成付费 → 在控制台创建 new-api key → 设置 `NEW_API_API_KEY` 后重试。不要打印 token、完整响应或临时媒体 URL。

用户明确要求充值时，直接在仓库根目录运行 `python3 shared/akasha_recharge.py`，不要先提交视频请求。仅官方 new-api 在精确识别余额不足且 metadata 允许充值时，才会自动创建 LovBrowser 支付页面。**整次命令最多一次充值**；入账后只重试失败的提交/轮询/下载一次，**已提交任务不会因轮询余额不足而重新提交**。`--recharge-usd` 可写在 `generate` 前或后。收到 `akasha.recharge` 后，Codex 只给出可点击的 `publicPageUrl`，不显示二维码；金额由用户在页面选择。详见 [`shared/recharge-contract.md`](../../shared/recharge-contract.md)。

输入参考素材必须是上游可访问的公共 HTTPS URL，不能依赖客户端 Authorization。输出写到仓库外 staging；脚本拒绝静默覆盖文件。

## 项目级 AGENTS.md

项目需要固化 Seedance 协作规则时，使用 [`assets/AGENTS.md`](assets/AGENTS.md) 作为可复制模板。项目已有 `AGENTS.md` 时只合并「Seedance 视频生成」章节，不覆盖原有规则；项目的更严格约束优先。

## 文生视频

```bash
python3 skills/seedance-video-generation/scripts/seedance_video.py generate \
  --prompt "雨夜霓虹街道，镜头缓慢向前推进，无文字" \
  --duration 5 \
  --resolution 720p \
  --ratio 16:9 \
  --output /tmp/seedance.mp4
```

默认模型为 `doubao-seedance-2-0-260128`。快速模型需显式传 `--model doubao-seedance-2-0-fast-260128`。Seedance 2.x 时长为 4–15 秒。

## 模型选择

- `seedance-1.0-pro` → `doubao-seedance-1-0-pro-250528`，4–12 秒，支持文字或图片输入。
- `seedance-1.0-lite` 根据是否传入图片，自动选择 `doubao-seedance-1-0-lite-t2v-250428` 或 `doubao-seedance-1-0-lite-i2v-250428`，4–12 秒。
- `seedance-1.5-pro` → `doubao-seedance-1-5-pro-251215`，4–12 秒，支持文字或图片输入与原生音频生成。
- `seedance-2` / `seedance-2-fast`：映射到对应 2.0 Ark ID，4–15 秒，支持图片、视频和音频参考。

Seedance 1.x 不接受视频或音频参考；脚本会在发起计费请求前拒绝不兼容的组合。使用前确认 new-api 渠道已启用该 Ark 模型并配置定价。

## 参考素材

按需重复传入素材参数：

```bash
python3 skills/seedance-video-generation/scripts/seedance_video.py generate \
  --prompt "保持角色与服装一致，角色转身并挥手" \
  --first-frame https://media.example.invalid/first.png \
  --last-frame https://media.example.invalid/last.png \
  --reference-video https://media.example.invalid/motion.mp4 \
  --reference-audio https://media.example.invalid/music.mp3 \
  --duration 10 \
  --resolution 720p \
  --output /tmp/seedance-reference.mp4
```

带参考视频时，单条视频不得超过 15 秒。含参考素材的 Seedance 2.0 请求优先用 720p；1080p/4K 是否可用取决于当前模型与参考模式，不要把纯文生视频成功外推为参考视频也兼容同一分辨率。

## 任务与验收

脚本提交 `POST /v1/video/generations`，轮询 `GET /v1/video/generations/{task_id}`，成功后通过 `GET /v1/videos/{task_id}/content` 下载结果。只有终态成功、下载为非空 MP4 且文件签名有效才算协议完成。

交付前继续用 `ffprobe` 检查时长、编码、分辨率，并抽取代表帧检查主体一致性、运动连续性、提示词约束与水印。不要以 HTTP 200、任务 `SUCCESS` 或脚本 `OK` 代替成片验收。

常见错误：

- `401`：new-api token 缺失、失效或无权访问。
- `400 model price not configured`：管理员尚未配置该 Seedance 模型的倍率。
- `400/404 channel not found`：new-api 尚未启用包含该模型的 DoubaoVideo/VolcEngine 渠道。
- `resolution ... not valid`：改用 720p，尤其是带参考素材时。
- `queued` / `IN_PROGRESS`：继续轮询；超时后明确报告任务未完成，不伪造成功。

脚本只在最终成功后原子写入输出；失败时不要把 JSON、HTML 或空响应保存成视频。

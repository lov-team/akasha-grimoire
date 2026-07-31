---
name: grok-media-generation
description: 通过 new-api 的 OpenAI-compatible Grok 端点生成或编辑图片与视频，轮询视频任务并安全下载最终文件。用户要求调用 grok-imagine-image、grok-imagine-image-quality、grok-imagine-video 或 grok-imagine-video-1.5-preview，验证 /v1/images/generations、/v1/images/edits、/v1/videos/generations、/v1/videos/edits，或排查 Grok 媒体生成、图片编辑、视频编辑失败时使用。
---

# Grok 图片与视频生成

使用 [`scripts/grok_media.py`](scripts/grok_media.py) 调用 new-api，不手写包含凭证的 curl。真实生成会计费；先做单个最小 smoke，再扩大任务规模。

## 准备

默认连接 LovBrowser new-api：`https://newapi.1234bot.com/v1`。只配置 Bearer token 即可开始，按 `GROK_MEDIA_API_KEY`、`NEW_API_API_KEY`、`OPENAI_API_KEY` 的顺序读取。通过受控的环境注入或凭证管理器提供 key；不要把 key 写进参数、prompt、日志、代码或仓库。

没有 Key 时，入口会调用共享 `shared/akasha_credentials.py` 进入 `AKASHA_DEVICE_V1`：在对话中渲染本地 PNG 二维码，同时显示可点击链接和短码，用户确认后自动轮询、原子保存、以 `/v1/models` 验证，并让原动作继续一次。不要显示 device code、PKCE verifier、真实 Key 或凭证文件内容。详见 [`akasha-key-setup`](../akasha-key-setup/SKILL.md) 与 [`credentials-contract.md`](../../shared/credentials-contract.md)。

用户明确要求充值时，直接在仓库根目录运行 `python3 shared/akasha_recharge.py`，不要先提交媒体请求。仅官方 new-api 在返回可充值的 `insufficient_user_quota` 时，才会自动创建 LovBrowser 支付页面。**整次命令最多一次 ticket/session**；入账后只重试当时失败的 HTTP 阶段一次（视频已提交后的轮询/下载不会重新提交任务）。默认 1 USD；`--recharge-usd` 可写在子命令前或后（如 `image-generate --recharge-usd 5 ...`）。收到 `akasha.recharge` 后，Codex 只给出可点击的 `publicPageUrl`，不显示二维码；金额由用户在页面选择。详见 [`shared/recharge-contract.md`](../../shared/recharge-contract.md)。

需要切换端点时，按以下优先级覆盖：

1. `--base-url`
2. `GROK_MEDIA_BASE_URL`
3. `NEW_API_BASE_URL`
4. `OPENAI_BASE_URL`
5. `https://newapi.1234bot.com/v1`

base URL 可传 host 根或以 `/v1` 结尾的 API 根；自定义前缀会在末尾补 `/v1`。拒绝 userinfo、query 和 fragment。覆盖配置只影响当前进程或受控运行环境，不要把团队密钥提交到配置文件。

输出必须写到仓库外 staging。脚本拒绝静默覆盖已有文件；只有用户明确要求时才传 `--overwrite`。

## 图片生成

```bash
python3 skills/grok-media-generation/scripts/grok_media.py image-generate \
  --prompt "A red panda astronaut on the moon, no text" \
  --output /tmp/grok-image.jpg
```

默认模型为 `grok-imagine-image`。高质量模式显式传 `--model grok-imagine-image-quality`。成功必须是 2xx、`data` 非空，并将首个 `url` 或 `b64_json` 解码为真实图片文件。

## 图片编辑

图片编辑使用 OpenAI 标准 multipart `/v1/images/edits`：

```bash
python3 skills/grok-media-generation/scripts/grok_media.py image-edit \
  --image /absolute/path/reference.jpg \
  --prompt "Keep the composition; change only the umbrella to green" \
  --output /tmp/grok-image-edited.jpg
```

固定主体、构图和不得变化的元素。不要把 JSON URL 编辑成功外推成 multipart 兼容；需要验证代理兼容性时必须实际使用 `image-edit`。

## 视频生成

```bash
python3 skills/grok-media-generation/scripts/grok_media.py video-generate \
  --prompt "The astronaut waves, stable camera" \
  --duration 4 \
  --output /tmp/grok-video.mp4
```

脚本提交 `/v1/videos/generations`，轮询 `/v1/videos/{request_id}`，完成后从 `/v1/videos/{request_id}/content` 下载 MP4。默认模型为 `grok-imagine-video`；预览模型需显式传 `--model grok-imagine-video-1.5-preview`。

## 视频编辑

优先使用同一 CPA 实例刚生成的视频任务 ID：

```bash
python3 skills/grok-media-generation/scripts/grok_media.py video-edit \
  --video-file-id <generation-request-id> \
  --prompt "Make the scene nighttime while preserving motion" \
  --output /tmp/grok-video-edited.mp4
```

当前 CPA 已支持 `video.file_id` resolver：它会同步确认来源任务已完成，将结果改写为 xAI 可用的 `video.url`，并复用生成来源账号。未知任务返回 404，未完成或失败返回 409，类型错误返回 422，不应先返回 200 再异步失败。

需要编辑外部来源视频，或任务 ID 已因 CPA 重启、缓存过期而无法解析时，改用可被上游直接访问的公开 HTTPS URL：

```bash
python3 skills/grok-media-generation/scripts/grok_media.py video-edit \
  --video-url https://media.example.invalid/source.mp4 \
  --prompt "Make the scene nighttime while preserving motion" \
  --output /tmp/grok-video-edited.mp4
```

`video.url` 不能依赖客户端 Authorization。`video.file_id` 只适用于同一 CPA 运行周期内仍保留任务绑定的生成 ID；当前绑定和完成结果是 TTL 内存缓存，CPA 重启或缓存过期后可能无法解析，此时使用已完成状态中的 `metadata.url` 回退。

## 验收与诊断

- 图片：检查真实文件签名、像素、画面内容和编辑约束，不以 HTTP 200 代替视觉验收。
- 视频：检查文件签名、时长、编码、分辨率、代表帧、运动连续性和编辑指令，不以任务 `completed` 代替成片验收。
- `401`：token 缺失、失效或无权访问。
- `400 multipart: NextPart...`：代理可能把 JSON 请求体与 multipart 请求头混用；检查上游 `Content-Type`。
- `video.file_id` 返回 404：确认 ID 来自同一 CPA 实例且仍在缓存期；否则改用完成状态中的 `metadata.url`。
- `queued` 或 `processing`：继续轮询；超过 `--poll-timeout` 后明确报告未完成，不伪造成功。

脚本只在最终成功后写文件。失败时不要把错误 JSON、登录页或 HTML 保存成图片或视频。

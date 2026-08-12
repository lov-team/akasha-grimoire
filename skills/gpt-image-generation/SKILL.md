---
name: gpt-image-generation
description: 通过 OpenAI-compatible GPT Image 端点生成单张或多张输出、单图编辑或多参考图合成图像，将 b64_json 结果安全落盘，校验真实格式与像素尺寸，并诊断认证、重定向、provider 失败与超时。用户要求用 GPT Image 或 gemini-3.1-flash-image 生图、一次生成多张、参考图改图、上传多张图片合成、验证 /v1/images/generations 或 /v1/images/edits、检查图像代理兼容性或排查生成失败时使用。
---

# GPT Image 生图与端点诊断

使用内置脚本生成或编辑图像，不手写包含凭证的 curl。先用最小 smoke 验证真实端点，再扩大数量或进入生产资产流程。

## 准备合同

明确模型、prompt、尺寸、参考图、输出格式、仓库外 staging 路径和验收标准。脚本默认使用 LovBrowser new-api：`https://newapi.1234bot.com/v1`。只有需要切换私有部署时才按 `--base-url`、`IMAGE_PROXY_BASE_URL`、`NEW_API_BASE_URL` 的顺序覆盖，不读取 `OPENAI_BASE_URL`。

没有 Key 时，入口会调用共享 `shared/akasha_credentials.py` 进入 `AKASHA_DEVICE_V1`：在对话中渲染本地 PNG 二维码，同时显示可点击链接和短码，用户确认后自动轮询、原子保存、以 `/v1/models` 验证，并让原动作继续一次。不要显示 device code、PKCE verifier、真实 Key 或凭证文件内容。详见 [`akasha-key-setup`](../akasha-key-setup/SKILL.md) 与 [`credentials-contract.md`](../../shared/credentials-contract.md)。

### 主动/余额不足充值（仅官方 new-api）

用户明确要求充值时，直接在仓库根目录运行 `python3 shared/akasha_recharge.py`；不要先提交生图请求来制造余额不足。

仅当请求发往官方入口 `https://newapi.1234bot.com/v1`，且服务端返回 HTTP 403、`error.code=insufficient_user_quota`、`error.metadata.recharge.supported=true` 时，脚本才会申请充值票据、创建 LovBrowser 支付会话、输出单行 `akasha.recharge` 结构化事件（含 `publicPageUrl`、`statusUrl`、`publicId`、过期时间与状态；不含 `payUrl`/ticket/Key）。**整次命令最多一次充值**；入账成功后只重试当时失败的请求一次，此后再遇余额不足立即停止。默认 1 USD；`--recharge-usd` 可提前校验，`AKASHA_RECHARGE_USD` 仅在真正触发充值时读取。私有 Base URL 保持原错误语义。

收到 `akasha.recharge` 后，Agent 只提供可点击的 `publicPageUrl`，不显示二维码；金额由用户在页面选择，不得展示 ticket/Key。契约见 [`shared/recharge-contract.md`](../../shared/recharge-contract.md)。

## 生成图像

生成与编辑固定请求 `b64_json` 并直接写入仓库外 staging：

```bash
python3 skills/gpt-image-generation/scripts/generate_openai_image.py \
  --prompt "A tiny red square app icon, clean vector style, no text" \
  --size 1024x1024 \
  --output /tmp/image-smoke.png
```

脚本拒绝静默覆盖已存在文件；明确需要覆盖时才传 `--overwrite`。成功响应的每个 `data` 项都必须包含非空 `b64_json`；代理若忽略请求并返回 URL，脚本会判为协议不兼容。

脚本会读取图片魔数和头部尺寸，不信任输出文件后缀。如果上游返回 JPEG 但 `--output` 指定 `.png`，脚本会保留原始字节并自动改用 `.jpg` 落盘，同时输出 `WARN output_extension_corrected`。实际像素与 `--size` 不一致时输出 `WARN output_size_mismatch`；这类警告表示上游忽略了格式或尺寸提示，不得在交付时隐藏。

### Gemini 3.1 Flash Image

`gemini-3.1-flash-image` 已通过 LovBrowser new-api 的生成与单图编辑 smoke。显式传模型：

```bash
python3 skills/gpt-image-generation/scripts/generate_openai_image.py \
  --base-url https://llmapi.lovbrowser.com/v1 \
  --model gemini-3.1-flash-image \
  --prompt "A cobalt blue circle on an off-white background, no text" \
  --size 1024x1024 \
  --output /tmp/gemini-image-smoke.png
```

已观察到该链路可将 `1024x1024` 生成请求返回为 2048×2048 JPEG，而编辑返回 1024×1024 JPEG。将尺寸与容器格式视为需要验收的上游输出，不要根据请求参数推定。

一次生成多张时传 `--n`（1–10）。响应数量必须与请求完全一致，多张结果以 `-1`、`-2` 编号落盘：

```bash
python3 skills/gpt-image-generation/scripts/generate_openai_image.py \
  --prompt "Two distinct clean vector icon variations, no text" \
  --n 2 \
  --output /tmp/variant.png
```

ChatGPT Subscription（Codex）图片通道只支持单张输出，必须使用 `n=1`；`n>1` 只交给已用 smoke 证明支持完整多输出的上游，不能把 200 但仅返回一项当作成功。

## 编辑参考图

传 `--image` 后调用 `/v1/images/edits`：

```bash
python3 skills/gpt-image-generation/scripts/generate_openai_image.py \
  --image /absolute/path/to/reference.png \
  --prompt "Keep the composition; change only the background to deep blue" \
  --output /tmp/image-edit.png
```

固定参考图、角色身份和 freeze-list。不要把一次 edits 成功外推为所有格式、尺寸或多图输入均受支持。

重复传 `--image` 可上传 2–5 张参考图并合成为一张结果。脚本使用重复的 `image[]` multipart 字段；prompt 必须说明每张图要保留的对象、位置和禁止变化项：

```bash
python3 skills/gpt-image-generation/scripts/generate_openai_image.py \
  --image /absolute/path/to/first.png \
  --image /absolute/path/to/second.png \
  --prompt "Keep the first object on the left and the second on the right, no text" \
  --output /tmp/image-composite.png
```

编辑与多参考图合成固定单张输出；脚本拒绝同时使用 `--image` 和 `--n > 1`。

## 使用项目环境文件

本地后端可显式读取同一环境文件：

```bash
python3 skills/gpt-image-generation/scripts/generate_openai_image.py \
  --base-url http://127.0.0.1:8010 \
  --env-file backend/.env \
  --output /tmp/image-local-smoke.png
```

环境文件只用于进程内载入，不回显其内容。

## 判断结果

- `401`：bearer key 缺失、失效或被拒绝。
- `302`、`307` 或 `/login?...`：请求在到达图像路由前被认证层截获，不能当成功。
- `502`：已到达后端，但上游图像 provider 失败。
- `504`：provider 轮询超时；生产 smoke 可提高 `--timeout`。
- 成功必须是 2xx JSON，含 `created` 与非空 `data`；数量等于请求的 `n`，每项都有非空 `b64_json`。
- 脚本会拒绝非 PNG/JPEG/GIF/WebP 签名，并在落盘后输出 `format`、`pixels` 和 `alpha`。
- 声称生成完成前，仍需实际查看内容；API 200 或脚本 `OK` 只证明协议成功。

不要在诊断时输出完整 provider 响应、base64 正文、临时授权 URL 或凭证。真实生图可能计费；未经用户授权时只做 `--help`、语法和本地无网络验证。

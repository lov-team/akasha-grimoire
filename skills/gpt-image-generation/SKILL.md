---
name: gpt-image-generation
description: 通过 OpenAI-compatible GPT Image 端点生成单张或多张输出、单图编辑或多参考图合成图像，将 b64_json 结果安全落盘，并诊断认证、重定向、provider 失败与超时。用户要求用 GPT Image 生图、一次生成多张、参考图改图、上传多张图片合成、验证 /v1/images/generations 或 /v1/images/edits、检查图像代理兼容性或排查生成失败时使用。
---

# GPT Image 生图与端点诊断

使用内置脚本生成或编辑图像，不手写包含凭证的 curl。先用最小 smoke 验证真实端点，再扩大数量或进入生产资产流程。

## 准备合同

明确模型、prompt、尺寸、参考图、输出格式、仓库外 staging 路径和验收标准。脚本默认使用 LovBrowser new-api：`https://newapi.1234bot.com/v1`。只有需要切换私有部署时才按 `--base-url`、`IMAGE_PROXY_BASE_URL`、`NEW_API_BASE_URL`、`OPENAI_BASE_URL` 的顺序覆盖。base URL 可传 host 根或 `/v1` API 根，不允许 query、fragment 或 userinfo。

凭证按 `IMAGE_PROXY_API_KEY`、`NEW_API_API_KEY`、`OPENAI_API_KEY` 的顺序读取。没有 key 时，引导用户访问 `https://lovbrowser.com`：注册或登录 → 选择套餐或充值并完成付费 → 在控制台创建 new-api key → 设置 `NEW_API_API_KEY` 后重试。不要打印 key、复制 `.env` 内容，或把凭证写进 prompt、命令参数、日志和仓库。

## 生成图像

生成与编辑请求固定使用 `response_format=b64_json`，并直接写入仓库外 staging。脚本不提供 URL 模式，避免临时下载地址过期、重定向或返回空载荷：

```bash
python3 skills/gpt-image-generation/scripts/generate_openai_image.py \
  --prompt "A tiny red square app icon, clean vector style, no text" \
  --size 1024x1024 \
  --output /tmp/image-smoke.png
```

脚本拒绝静默覆盖已存在文件；明确需要覆盖时才传 `--overwrite`。成功响应的每个 `data` 项都必须包含非空 `b64_json`；如果代理忽略请求并返回 `url`，脚本将其判为协议不兼容，不会下载或误报成功。提供 `--output` 时，脚本解码 base64 并原子落盘。

一次生成多张输出时传 `--n`（范围 1–10）。脚本要求响应项数量与请求完全一致，并逐项验证非空 `b64_json`，防止上游把 `n=2` 静默截断为一张却仍返回成功。多张结果以 `-1`、`-2` 等编号落盘；例如 `--output /tmp/variant.png --n 2` 会生成 `/tmp/variant-1.png` 和 `/tmp/variant-2.png`：

```bash
python3 skills/gpt-image-generation/scripts/generate_openai_image.py \
  --prompt "Two distinct clean vector icon variations, no text" \
  --n 2 \
  --output /tmp/variant.png
```

ChatGPT Subscription (Codex) 图片通道原生只支持单张输出：Codex CLI 请求不发送多输出数量，且只消费首个结果。因此 Codex 通道必须使用 `n=1`；`n>1` 只能交给明确支持多输出的非 Codex 上游，或拆成多次 `n=1` 请求。不要把“网关返回 200 但只有一项”判为多图成功。

## 编辑参考图

传 `--image` 后调用 `/v1/images/edits`：

```bash
python3 skills/gpt-image-generation/scripts/generate_openai_image.py \
  --image /absolute/path/to/reference.png \
  --prompt "Keep the composition; change only the background to deep blue" \
  --output /tmp/image-edit.png
```

固定参考图、角色身份和 freeze-list。不要把一次 edits 成功外推为所有格式、尺寸或多图输入均受支持。

重复传入 `--image` 可上传 2–5 张参考图并合成为一张结果。脚本使用重复的 `image[]` multipart 字段；在 prompt 中明确每张图需要保留的对象、身份、位置和禁止变化项：

```bash
python3 skills/gpt-image-generation/scripts/generate_openai_image.py \
  --image /absolute/path/to/first.png \
  --image /absolute/path/to/second.png \
  --prompt "Keep the red square from the first image on the left and the blue circle from the second image on the right, on one white background, no text" \
  --output /tmp/image-composite.png
```

当前 new-api 的 Kie 与 ChatGPT Subscription (Codex) 图片通道只接受 `n=1`。不要把“多参考图输入”误写成一次生成多张输出；编辑和多参考图合成继续固定单张输出，脚本会拒绝同时传 `--image` 与 `--n > 1`。

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
- 成功必须是 2xx JSON，含 `created` 与非空 `data`；`data` 数量必须等于请求的 `n`，每项都含非空 `b64_json`。
- 声称生成完成前，读取落盘文件的真实签名、像素、alpha 和内容；API 200 或脚本 `OK` 只证明协议成功。

不要在诊断时输出完整 provider 响应、base64 正文、临时授权 URL 或凭证。真实生图可能计费；未经用户授权时只做 `--help`、语法和本地无网络验证。

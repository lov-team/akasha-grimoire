---
name: gpt-image-generation
description: 通过 OpenAI-compatible GPT Image 端点生成、单图编辑或多参考图合成图像，将 b64_json 结果安全落盘，并诊断认证、重定向、provider 失败与超时。用户要求用 GPT Image 生图、参考图改图、上传多张图片合成、验证 /v1/images/generations 或 /v1/images/edits、检查图像代理兼容性或排查生成失败时使用。
---

# GPT Image 生图与端点诊断

使用内置脚本生成或编辑图像，不手写包含凭证的 curl。先用最小 smoke 验证真实端点，再扩大数量或进入生产资产流程。

## 准备合同

明确 base URL、模型、prompt、尺寸、参考图、输出格式、仓库外 staging 路径和验收标准。base URL 必须由 `--base-url` 或 `IMAGE_PROXY_BASE_URL` 明确提供；不要假定供应商或硬编码项目地址。可传 host 根、以 `/v1` 结尾的 API 根或自定义前缀，脚本只在末段不是 `v1` 时补 `/v1`。base URL 不允许 query、fragment 或 userinfo。

凭证只从 `IMAGE_PROXY_API_KEY` 或 `OPENAI_API_KEY` 读取。不要打印 key、复制 `.env` 内容，或把凭证写进 prompt、命令参数、日志和仓库。

## 生成图像

生成与编辑请求固定使用 `response_format=b64_json`，并直接写入仓库外 staging。脚本不提供 URL 模式，避免临时下载地址过期、重定向或返回空载荷：

```bash
python3 skills/gpt-image-generation/scripts/generate_openai_image.py \
  --base-url https://example.invalid \
  --prompt "A tiny red square app icon, clean vector style, no text" \
  --size 1024x1024 \
  --output /tmp/image-smoke.png
```

脚本拒绝静默覆盖已存在文件；明确需要覆盖时才传 `--overwrite`。成功响应必须在首个 `data` 项中包含非空 `b64_json`；如果代理忽略请求并返回 `url`，脚本将其判为协议不兼容，不会下载或误报成功。提供 `--output` 时，脚本解码 base64 并原子落盘。

## 编辑参考图

传 `--image` 后调用 `/v1/images/edits`：

```bash
python3 skills/gpt-image-generation/scripts/generate_openai_image.py \
  --base-url https://example.invalid \
  --image /absolute/path/to/reference.png \
  --prompt "Keep the composition; change only the background to deep blue" \
  --output /tmp/image-edit.png
```

固定参考图、角色身份和 freeze-list。不要把一次 edits 成功外推为所有格式、尺寸或多图输入均受支持。

重复传入 `--image` 可上传 2–5 张参考图并合成为一张结果。脚本使用重复的 `image[]` multipart 字段；在 prompt 中明确每张图需要保留的对象、身份、位置和禁止变化项：

```bash
python3 skills/gpt-image-generation/scripts/generate_openai_image.py \
  --base-url https://example.invalid \
  --image /absolute/path/to/first.png \
  --image /absolute/path/to/second.png \
  --prompt "Keep the red square from the first image on the left and the blue circle from the second image on the right, on one white background, no text" \
  --output /tmp/image-composite.png
```

当前 new-api 的 Kie 图片通道只接受 `n=1`。不要把“多参考图输入”误写成一次生成多张输出；在路由支持 `n>1` 前，脚本继续固定单张输出。

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
- 成功必须是 2xx JSON，含 `created` 与非空 `data`，首项含非空 `b64_json`。
- 声称生成完成前，读取落盘文件的真实签名、像素、alpha 和内容；API 200 或脚本 `OK` 只证明协议成功。

不要在诊断时输出完整 provider 响应、base64 正文、临时授权 URL 或凭证。真实生图可能计费；未经用户授权时只做 `--help`、语法和本地无网络验证。

---
name: akasha-key-setup
description: 当 Akasha 媒体 Skill 需要复用本地 OpenAI Key、验证并降级到显式配置，或用户要求配置、查看、取消、恢复 Akasha 凭证时，使用共享凭证探测与 LovBrowser AKASHA_DEVICE_V1 扫码授权流程。
---

# Akasha Key Setup

所有媒体 Skill 共用 `shared/akasha_credentials.py`，不要复制实现，也不要要求用户把真实 Key 发到对话中。

## 自动降级流程

GPT Image、Grok、Seedance、Fish Audio、Suno 的入口会自动：

1. 优先读取本地 `OPENAI_API_KEY`，但 URL 仍使用当前媒体 Skill 的专用 Base URL、`NEW_API_BASE_URL` 或仓库默认 URL；忽略 `OPENAI_BASE_URL`。调用该 URL 的 `/v1/models`，验证成功就直接复用 Key。
2. 本地 OpenAI Key 不可达、被拒绝或响应不兼容时，依次验证统一的 `LOVBROWSER_API_KEY` 和 `~/.config/akasha/credentials.env`。
3. 所有候选都缺失或验证失败时，调用 LovBrowser Device Flow，生成 PKCE S256 verifier/challenge。
4. 输出 `akasha.device_authorization` 事件，其中只有短码、公开验证链接和本地 PNG 绝对路径。
5. 用 Markdown 图片语法渲染 `qrPngPath`，并同时给出可点击的 `verificationUriComplete` 与 `userCode`。
6. 保持原命令运行，低噪声等待用户在手机上确认。
7. 兑换 Key 后原子写入用户凭证文件，调用官方 `/v1/models` 验证，再让最初的媒体动作继续执行一次。

不要显示或转述 device code、PKCE verifier、真实 Key、状态文件或凭证文件内容。

## 独立命令

在仓库根目录运行：

```bash
python3 shared/akasha_credentials.py status
python3 shared/akasha_credentials.py start
python3 shared/akasha_credentials.py finish
python3 shared/akasha_credentials.py cancel
python3 shared/akasha_credentials.py rollback
```

- `start` 创建一次 600 秒设备会话与真实 PNG，然后退出；适合分两步操作。
- `finish` 从 0600 本地状态读取秘密并轮询；秘密不进入 argv。
- `cancel` 删除未完成设备状态。
- `rollback` 用上一版 `credentials.env.bak` 恢复凭证。
- `status` 只输出来源、Base URL 和是否存在进行中会话，不输出 Key。

用户中断、拒绝或会话过期后清理状态；过期会话重新执行 `start`，不复活旧会话。

## 配置发现与运行优先级

新配置只写 `LOVBROWSER_API_KEY`。为兼容存量环境，统一 Key 不存在时才低优先级读取旧 `NEW_API_API_KEY` 及媒体专用 Key；不得在新配置中继续使用旧名称。旧 `credentials.env` 首次读取时自动原子改写字段名，并把原文件保存为 `credentials.env.bak`。

媒体入口必须走 `bootstrap` 的验证式运行顺序：本地 `OPENAI_API_KEY` > `LOVBROWSER_API_KEY` > `~/.config/akasha/credentials.env` > LovBrowser 配置引导。只降级 Key，不跟随 Key 切换 URL；URL 始终由媒体 Skill 自身解析。不要只检查变量是否存在；每个候选都要先通过 `/v1/models`。

用户目录权限为 0700，凭证、备份、锁、Device 状态及二维码文件为 0600。生产只接受精确的 `https://lovbrowser.com` 和 `https://llmapi.lovbrowser.com/v1`，且不跟随重定向。

跨仓协议固定于 [LovBrowser #1256](https://github.com/jingx8885/lovbrowser/issues/1256)，客户端实现关联 [Akasha #4](https://github.com/lov-team/akasha-grimoire/issues/4)。

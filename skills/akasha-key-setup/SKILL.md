---
name: akasha-key-setup
description: 当 Akasha 媒体 Skill 缺少 new-api Key，或用户要求配置、查看、取消、恢复 Akasha 凭证时，使用 LovBrowser AKASHA_DEVICE_V1 扫码授权流程。
---

# Akasha Key Setup

所有媒体 Skill 共用 `shared/akasha_credentials.py`，不要复制实现，也不要要求用户把真实 Key 发到对话中。

## 缺 Key 自动流程

GPT Image、Grok、Seedance、Fish Audio、Suno 的入口会自动：

1. 调用 LovBrowser Device Flow，生成 PKCE S256 verifier/challenge。
2. 输出 `akasha.device_authorization` 事件，其中只有短码、公开验证链接和本地 PNG 绝对路径。
3. 用 Markdown 图片语法渲染 `qrPngPath`，并同时给出可点击的 `verificationUriComplete` 与 `userCode`。
4. 保持原命令运行，低噪声等待用户在手机上确认。
5. 兑换 Key 后原子写入用户凭证文件，调用官方 `/v1/models` 验证，再让最初的媒体动作继续执行一次。

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

## 凭证优先级

专用环境变量 > `NEW_API_API_KEY` > `~/.config/akasha/credentials.env` > `OPENAI_API_KEY`。

用户目录权限为 0700，凭证、备份、锁、Device 状态及二维码文件为 0600。生产只接受精确的 `https://lovbrowser.com` 和 `https://llmapi.lovbrowser.com/v1`，且不跟随重定向。

跨仓协议固定于 [LovBrowser #1256](https://github.com/jingx8885/lovbrowser/issues/1256)，客户端实现关联 [Akasha #4](https://github.com/lov-team/akasha-grimoire/issues/4)。

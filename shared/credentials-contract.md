# Akasha shared credential contract

实现：`shared/akasha_credentials.py`。协议版本为 `AKASHA_DEVICE_V1`，服务端契约固定于 [LovBrowser #1256](https://github.com/jingx8885/lovbrowser/issues/1256)。

## 运行时降级顺序

所有媒体 Skill 只使用一套共享 Key。先读取本地 `OPENAI_API_KEY`，但忽略 `OPENAI_BASE_URL`；随后读取 `LOVBROWSER_API_KEY` 与用户级 Akasha 凭证。统一 Key 缺失时，才低优先级兼容旧 `NEW_API_API_KEY` 和媒体专用 Key。URL 始终由媒体 Skill 自身解析。旧 `credentials.env` 首次读取时原子改写为 `LOVBROWSER_API_KEY`，并把原文件以 0600 权限保存为 `credentials.env.bak`；新文件只允许 `LOVBROWSER_API_KEY` 与 `NEW_API_BASE_URL`。

## 客户端流程

1. `start` 生成 PKCE S256，调用 Device start endpoint，把 device code 与 verifier 仅写入 0600 临时状态。
2. 本机二维码仅编码公开的 `verificationUriComplete`；事件只输出绝对 PNG 路径、短码和公开链接。
3. `finish` 从状态文件读取秘密，通过 JSON body 轮询 token endpoint；处理 `authorization_pending` 与 `slow_down`。
4. 成功后先以 `/v1/models` 验证，再原子写入凭证并清理临时状态。
5. 生产 origin、Base URL 精确匹配 allowlist，所有 Device 响应要求 `Cache-Control: no-store`，HTTP 重定向一律拒绝。

自动化通过显式的进程内 HTTP fixture 注入测试，不向生产配置加入测试地址。

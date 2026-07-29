# 官方 new-api 余额不足充值契约

实现：`shared/akasha_recharge.py`。五个媒体入口仅做薄适配，**每次 CLI 顶层命令创建一个 `RechargeController`**，整次命令最多一次 ticket/session。

## 触发条件（同时满足）

1. 请求 base URL 规范化后属于官方 origin：`https://newapi.1234bot.com`（默认端口，无 userinfo）。
2. HTTP 状态码为 `403`。
3. `error.code` 精确为 `insufficient_user_quota`。
4. `error.metadata.recharge.supported` 为布尔 `true`。

私有/相似域名/端口/userinfo 欺骗或其它 403，一律不触发签票或 LovBrowser 请求，并保持原错误语义。

## 金额

- 产品默认：10 USD（1000 cent）。
- 显式 CLI `--recharge-usd` 可在启动时校验；`AKASHA_RECHARGE_USD` **仅在真正触发充值时**解析，私有网关或成功路径不受非法环境变量影响。
- CLI 优先于环境变量；十进制定点换算 cents；拒绝非数值、超过两位小数、非有限值、以及 1–10000 USD 之外金额。
- metadata 中的 `default_face_value_usd_cent` 仅作服务端信息，不覆盖产品默认。

## 协议步骤

1. `POST https://newapi.1234bot.com/v1/tooling/recharge-ticket`（官方 HTTPS only）
   `Authorization: Bearer <API Key>`，body `{"face_value_usd_cent":N}`。拒绝跨源重定向重放凭证。
2. 向响应中的 `lovbrowser_session_endpoint`（HTTPS、无 userinfo）发送且只发送 `{"ticket":"..."}`，**不**发送 API Key。
3. 下载 HTTPS `qrPngUrl` 到唯一仓库外临时 PNG，拒绝覆盖，校验非空 PNG 头。
4. 输出单行 JSON 事件 `event=akasha.recharge`，字段：`publicId`、`status`、`faceValueUsdCent`、`currency`、`expireTime`、`qrPngPath`、`publicPageUrl`、`statusUrl`。**不**暴露 `payUrl`/ticket/Key。
5. 轮询 `GET {session_endpoint}/{publicId}`；`CREDITING`/`PENDING_PAYMENT` 继续等待；`SUCCEEDED` 后只重试当时失败的 HTTP 闭包一次；此后任何阶段再次余额不足停止且不再签票。

## Agent / Codex 展示要求

收到 `akasha.recharge` 事件后，消费方必须：

1. 使用 `qrPngPath` 在 Codex 对话中**直接渲染二维码图片**（不要只打印路径）；
2. 同时提供可点击的 `publicPageUrl`；
3. 可附带安全 `statusUrl`；
4. 不得展示 ticket、API Key、Authorization 或直接支付凭证 URL。

## 禁止泄露

日志、事件、异常与落盘文件不得包含 API Key、Authorization、完整票据、支付凭证、服务端原始 `message` 中的敏感片段或签名密钥类敏感值。充值错误只输出 HTTP 状态、白名单短 code 与本地固定文案。

## 企业 Key

LovBrowser 拒绝企业成员自助充值时，输出清晰中文/英文提示联系管理员分配额度，不回显敏感响应字段。

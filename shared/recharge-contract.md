# 官方 new-api 主动/余额不足充值契约

实现：`shared/akasha_recharge.py`。五个媒体入口仅做薄适配，**每次 CLI 顶层命令创建一个 `RechargeController`**，整次命令最多一次 ticket/session。用户明确要求充值时，可直接运行共享 CLI，不需要先制造余额不足：

```bash
python3 shared/akasha_recharge.py --recharge-usd 1
```

CLI 按本地 `OPENAI_API_KEY`、`LOVBROWSER_API_KEY` 顺序读取统一共享 Key，不接受媒体专用 Key 或命令行明文 Key。

## 触发条件（同时满足）

1. 请求 base URL 规范化后属于精确官方 origin：`https://llmapi.lovbrowser.com`、`https://llmapi-direct.lovbrowser.com` 或兼容旧入口 `https://newapi.1234bot.com`（默认端口，无 userinfo）。
2. HTTP 状态码为 `403`。
3. `error.code` 精确为 `insufficient_user_quota`。
4. `error.metadata.recharge.supported` 为布尔 `true`。

私有/相似域名/端口/userinfo 欺骗或其它 403，一律不触发签票或 LovBrowser 请求，并保持原错误语义。

## 金额

- Agent 不在对话中询问或固定最终支付金额，只创建一次公开支付会话并给出 LovBrowser 页面链接。
- 用户在 LovBrowser 页面选择 5、20、100、200 USD 或输入 1–10000 USD 自定义金额；首次点击 Alipay 后金额锁定。
- 签票仍携带 1 USD（100 cent）兼容面值；最终订单金额只以 LovBrowser 支付页首次提交并由服务端校验、冻结的金额为准。

## 协议步骤

1. `POST {当前官方 new-api origin}/v1/tooling/recharge-ticket`（官方 HTTPS only）
   `Authorization: Bearer <API Key>`，body `{"face_value_usd_cent":N}`。拒绝跨源重定向重放凭证。
2. 向响应中的 `lovbrowser_session_endpoint`（HTTPS、无 userinfo）发送且只发送 `{"ticket":"..."}`，**不**发送 API Key。
3. 输出单行 JSON 事件 `event=akasha.recharge`，字段：`publicId`、`status`、`faceValueUsdCent`、`currency`、`expireTime`、`publicPageUrl`、`statusUrl`。**不**下载或展示二维码，也不暴露 `payUrl`/ticket/Key。
5. 轮询 `GET {session_endpoint}/{publicId}`；`CREDITING`/`PENDING_PAYMENT` 继续等待；`SUCCEEDED` 后只重试当时失败的 HTTP 闭包一次；此后任何阶段再次余额不足停止且不再签票。

主动充值只执行步骤 1–5，不提交媒体生成请求；余额不足自动充值在 `SUCCEEDED` 后额外重试原失败请求一次。

## Agent / Codex 展示要求

收到 `akasha.recharge` 事件后，消费方必须：

1. 只提供一个可点击的 `publicPageUrl`，引导用户在 LovBrowser 页面选择金额并点击 Alipay；
2. 对话中不显示二维码、不固定支付金额；
3. 可附带安全 `statusUrl`；
4. 不得展示 ticket、API Key、Authorization 或直接支付凭证 URL。

## 禁止泄露

日志、事件、异常与落盘文件不得包含 API Key、Authorization、完整票据、支付凭证、服务端原始 `message` 中的敏感片段或签名密钥类敏感值。充值错误只输出 HTTP 状态、白名单短 code 与本地固定文案。

## 企业 Key

LovBrowser 拒绝企业成员自助充值时，输出清晰中文/英文提示联系管理员分配额度，不回显敏感响应字段。

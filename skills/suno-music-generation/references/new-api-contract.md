# new-api Suno 事实合同

事实源：`new-api` 当前实现（审计提交 `2a6cba7c`）的路由、DTO、Suno adaptor 与测试。部署可能改变可用渠道和上游模型，调用前以目标环境模型列表为准。

## 客户端入口

| 动作 | 方法与路径 | new-api 路由模型 |
| --- | --- | --- |
| 生成歌曲 | `POST /suno/submit/MUSIC` | `suno_music` |
| 查询任务 | `GET /suno/fetch/{public_task_id}` | 不重新选渠道 |

认证使用 `Authorization: Bearer <new-api token>`。

提交响应是对象，成功时 `code` 为 `success`，`data` 是 new-api 公开 task id。查询响应成功时 `data` 是任务对象，核心字段为：

- `status`：`SUBMITTED`、`QUEUED`、`IN_PROGRESS`、`SUCCESS` 或 `FAILURE`；
- `fail_reason`：失败原因；
- `data`：成功时为歌曲数组；
- 每首歌曲可含 `audio_url`、`image_url`、`video_url`、`title`、`text` 与 `metadata.duration`。

## 提交字段

| 字段 | 用途 |
| --- | --- |
| `gpt_description_prompt` | 自然语言歌曲描述 |
| `prompt` | 自定义歌词 |
| `title` | 自定义歌词模式标题 |
| `tags` | 风格、流派、人声等标签 |
| `mv` | 上游音乐模型；2026-07-27 Kie 文档列出的最新版本为 `V5_5` |
| `make_instrumental` | 是否生成纯音乐 |

描述与自定义歌词应二选一。当前 Kie adaptor 会把 title/tags 视为 custom mode 信号，因此脚本要求自定义歌词同时提供标题和风格，描述模式则不附加 title/tags。

## 模型兼容基线

2026-07-26 在当前目标 new-api/Kie 渠道实测：省略 `mv` 会因上游默认旧模型不兼容返回 HTTP 400，显式 `mv=V4_5` 可正常提交、轮询并返回两首结果。2026-07-27 复核 Kie [`Generate Music`](https://docs.kie.ai/suno-api/generate-music) 文档后，音乐模型已列出 `V5_5` 与 `V5`，其中 `duration` 仅对 `V5_5` 生效；本地 new-api 的 MUSIC 适配器会把 `mv` 原样映射为 Kie 的 `model` 字段。因此脚本默认值升级为 `V5_5`，同时保留 `--model server-default` 供其他部署明确选择服务端默认值。部署差异仍以目标环境的渠道模型和实时错误为准，不应无限重试 400。

## 等待与安全

- Suno 是异步任务，不能把提交 2xx 当成歌曲生成完成。
- 本地脚本内部轮询即可；不要让主 Agent 高频读取任务。
- 只下载 `http`/`https` 结果，拒绝 `file:` 等协议。
- 结果 URL 可能带签名 query；日志只记录文件名、字节数和 task id，不记录完整 URL。
- 不在 Skill 中硬编码 new-api 地址、token、渠道 id 或生产配置。

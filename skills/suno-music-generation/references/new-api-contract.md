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
| `mv` | 可选上游模型；不明确时省略，由服务端处理 |
| `make_instrumental` | 是否生成纯音乐 |

描述与自定义歌词应二选一。当前 Kie adaptor 会把 title/tags 视为 custom mode 信号，因此脚本要求自定义歌词同时提供标题和风格，描述模式则不附加 title/tags。

## 等待与安全

- Suno 是异步任务，不能把提交 2xx 当成歌曲生成完成。
- 本地脚本内部轮询即可；不要让主 Agent 高频读取任务。
- 只下载 `http`/`https` 结果，拒绝 `file:` 等协议。
- 结果 URL 可能带签名 query；日志只记录文件名、字节数和 task id，不记录完整 URL。
- 不在 Skill 中硬编码 new-api 地址、token、渠道 id 或生产配置。

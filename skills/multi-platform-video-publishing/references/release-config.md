# 发布配置合同

从 `assets/release-config.example.json` 复制一份到内容项目。所有媒体路径允许相对配置文件目录或使用绝对路径；正式发布前脚本会解析并验证。

## 顶层字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `version` | 是 | 当前为 `1` |
| `release_id` | 是 | 单次发布唯一 ID；同一视频重发必须使用新 ID |
| `video` | 是 | 最终成片路径 |
| `video_sha256` | 是 | 64 位小写 SHA-256 |
| `platforms` | 是 | 平台到元数据的对象 |

平台键仅支持 `douyin`、`xiaohongshu`、`bilibili`、`tencent`。每个平台都需要 `enabled`、`account` 和 `title`；`enabled=false` 时跳过。

## 通用平台字段

- `desc`：简介；允许换行。
- `tags`：字符串数组，不带 `#`。
- `schedule`：可选，格式 `YYYY-MM-DD HH:MM`；不填表示立即发布。
- `browser_mode`：可选，`headed` 或 `headless`；抖音、小红书、视频号默认 `headed`。

## 专项字段

- 抖音：`thumbnail_portrait`、`thumbnail_landscape`。
- 小红书：`thumbnail`。
- 哔哩哔哩：`tid` 必填；CLI 当前不保证设置自定义封面。
- 微信视频号：`thumbnail`、`short_title`、`category`；页面可能不展示自定义封面入口。

## 内容适配

动画、MV 与口播共用同一 schema。口播发布前另外确认：

- 标题和封面兑现成片真实论点，不把字幕中的一句话夸大成完整结论；
- 简介保留讲话者的限定条件与事实边界；
- 平台标题长度、话题和封面裁切分别审阅，不机械复用一套文案；
- 置顶评论不属于当前 CLI 提交字段，作为发布后人工动作记录在台账证据中。

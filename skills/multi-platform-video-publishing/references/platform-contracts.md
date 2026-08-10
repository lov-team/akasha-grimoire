# 四平台执行合同

## 抖音

- 登录态：`mpau douyin check --account ACCOUNT`。
- 发布：视频、标题、简介、标签和竖版/横版封面；页面可能要求短信或自主声明。
- 可靠成功证据：作品管理页出现精确标题、提交时间与 `审核中`/`已发布`。
- 已知陷阱：页面版本变化时，CLI 可能一直轮询“重新上传”选择器，即使远端条目已经进入审核。重复两分钟以上且浏览器状态异常时，先查 `https://creator.douyin.com/creator-micro/content/manage`，不要重投。
- 不把真实账号 `--dry-run` 视作零副作用预览；计划阶段只打印命令。

## 小红书

- 登录态：`mpau xiaohongshu check --account ACCOUNT`。
- 发布：标题、简介、标签与 3:4 封面；没有无副作用预览参数。
- 可靠成功信号：`视频发布成功` 与 `cookie 更新完毕`；随后在创作中心查精确标题和状态。
- 封面设置成功必须有日志或作品管理页截图；仅传入 `--thumbnail` 不等于页面已采用。

## 哔哩哔哩

- 登录态：`mpau bilibili check --account ACCOUNT`。
- `tid` 必填；上传器调用 `biliup`，返回码非 0 才算提交失败。
- 可靠成功证据：创作中心稿件列表或管理 API 找到精确标题，记录 `aid`/`bvid` 与审核状态。
- CLI 当前只回传 `submitted` 文本时，先记为 `submitted`；不要提前写 `published`。

## 微信视频号

- 登录态：`mpau tencent check --account ACCOUNT`。
- 没有 `dry-run`；`--draft` 会真实保存草稿，也属于远端副作用。
- 正文通常由标题、话题和简介组合；可选 `short_title`、`category` 与封面。
- 可靠成功信号：`视频发布成功` 与 `cookie 更新完毕`；随后到 `https://channels.weixin.qq.com/platform/post/list` 查条目。
- 页面没有出现封面编辑弹窗时，上传器会使用平台自动封面；交付中必须注明，不声称自定义封面已采用。

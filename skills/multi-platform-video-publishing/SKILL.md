---
name: multi-platform-video-publishing
description: 将已验收的动画、口播、采访、知识讲解或其他成片逐个平台发布到抖音、小红书、哔哩哔哩和微信视频号，并保存可恢复的发布台账与远端核验证据。用户要求多平台分发、一键发布、登录或校验发布账号、为不同平台改写标题简介标签、上传视频和封面、继续中断的发布批次、确认审核状态、避免重复投稿，或希望让动画与口播项目复用同一发布能力时使用。
---

# 多平台视频发布

把一次发布建模为四个并行但状态隔离、可恢复的提交，不把“一条命令退出 0”当成四个平台都已发布。始终按 `本地成片 → 平台元数据 → 并行账号校验 → 并行提交 → 逐平台远端核验 → 台账` 推进。

## 绑定发布对象

1. 读取项目 `AGENTS.md`、最终 QA、发布文案、封面和最新用户确认；口播项目同时读取语义地图、最终字幕与封面承诺。
2. 只绑定一个最终视频绝对路径，记录字节、SHA-256、时长、画面/音频流和完整解码结果。源素材只读。
3. 从 `assets/release-config.example.json` 复制发布配置；同一视频允许平台标题、简介、标签、封面和分区不同。
4. 不读取、打印、复制或提交 Cookie、Token、二维码载荷和账号凭据。发布运行时与项目仓库分离。
5. 读取 [references/release-config.md](references/release-config.md) 完成配置；平台字段或页面行为不确定时再读 [references/platform-contracts.md](references/platform-contracts.md)。

## 使用真实运行时

优先使用用户已经登录的 `multi-platform-auto-upload` / `mpau` 运行时：

```bash
runtime="${MPAU_RUNTIME:-$HOME/.local/share/multi-platform-auto-upload}"
uv run --project "$runtime" mpau --help
```

如果项目或用户已声明其他运行时，以现有状态为准。先读取当前 CLI `--help` 和已安装的平台 Skill，不凭记忆猜参数。登录时按平台逐个完成 `check → login → check`；二维码必须直接显示，Cookie 只留在运行时目录。

## 发布阶段门

1. **本地可发布**：最终视频、封面、标题、简介、标签和平台专项字段齐全；完整解码为 0；视频 SHA 与配置一致。
2. **账号可发布**：四个平台逐个 `check`；超时不是失效，放宽一次等待后再判定。
3. **计划可审阅**：运行脚本 `plan`，确认每个平台的真实命令；计划阶段不上传文件、不保存草稿。
4. **并行提交**：`publish` 默认并发运行所有已启用平台，必须传确认 SHA；每个平台使用独立进程、日志和台账状态，单个平台失败不取消其他平台。
5. **发布后核验**：打开作品管理页或调用可靠管理接口，以精确标题、提交时间、时长和状态确认远端条目。

```bash
python3 scripts/publish_release.py validate /ABS/PATH/release.json --full-decode
python3 scripts/publish_release.py check /ABS/PATH/release.json
python3 scripts/publish_release.py plan /ABS/PATH/release.json
python3 scripts/publish_release.py publish /ABS/PATH/release.json \
  --confirm-sha VIDEO_SHA256 \
  --max-workers 4
```

脚本会在配置旁的 `reports/` 中保存台账，并把四个平台的实时输出加上平台前缀。`publish` 检测到某个平台已是 `submitted`、`reviewing` 或 `published` 时跳过该平台，只并行执行其余平台；先核验远端状态，再用 `record` 更新：

```bash
python3 scripts/publish_release.py record /ABS/PATH/release.json \
  --platform xiaohongshu \
  --status reviewing \
  --evidence "作品管理页：标题匹配，2026-08-10 12:01，审核中"

python3 scripts/publish_release.py status /ABS/PATH/release.json
```

## 并行边界与完成条件

默认同时启动抖音、小红书、哔哩哔哩和微信视频号，`--platform` 可重复传入以只跑选中平台，`--max-workers` 控制并发数。浏览器窗口、Cookie 文件、日志与结果按平台隔离；验证码或人工页面只暂停对应平台。每个平台只在以下证据成立时标记：

- `submitted`：上传命令退出 0，并出现平台成功信号；
- `reviewing`：远端作品管理页存在精确标题且显示审核/处理中；
- `published`：远端页面或管理 API 显示已发布，并记录 URL 或远端 ID；
- `failed`：保存错误原文、阶段和重试决策；
- `unknown`：CLI 卡住、窗口关闭或网络中断，远端事实尚未查清。

出现卡住时先读 [references/verification-and-recovery.md](references/verification-and-recovery.md)。不得因 CLI 一直打印“上传中”就重复投稿；也不得仅因浏览器跳转或进程退出就声称成功。

## 关键防重复规则

- 真实账号上的 `dry-run`、草稿和预览都可能产生远端副作用；计划阶段只生成命令，不上传真实文件。
- 单个平台 CLI 卡住超过其 Skill 规定时间时，只停止该平台进程并记录最后日志；其他平台继续执行，随后先查该平台作品管理页。
- 已找到同标题、同提交时间、同时长的条目时，直接记入台账并继续下一个平台。
- 不把四个平台放进一个串行黑盒；并行调度器必须保留逐平台退出码、日志和远端核验状态。
- 用户在网页端补完验证码、原创声明或发布按钮后，把网页结果作为当前事实，不再次提交。

## 交付

返回：视频路径与 SHA、四个平台的标题/状态/时间、成功信号、远端 URL 或 ID、封面实际采用情况、失败与人工动作、发布台账绝对路径。视频号未出现自定义封面弹窗、小红书或抖音进入审核、B站只拿到投稿 ID 等情况必须如实写明。

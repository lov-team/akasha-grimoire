---
name: video-source-research
description: 根据脚本、镜头表、对白或 B-roll 需求检索、比较、下载并登记可追溯的视频、图片和音频素材，支持用户提供 URL、公开素材站、网页视频、现有素材目录、yt-dlp 和直接媒体 URL，并用哈希与 ffprobe 验证下载结果。用户要求搜索视频素材、找 B-roll、下载视频、建立素材库、记录素材来源、批量检查媒体或为剪辑准备素材时使用。
---

# 视频素材检索

把“搜索到链接”“下载成功”和“适合该镜头”分开验收。

## 从镜头表生成检索任务

读取 `shot-list.csv`，对 `source_strategy=search` 的镜头建立查询：主体、动作、场景、时间、机位、情绪、画幅和必须避免的元素。为同一镜头准备具体查询、同义查询和宽泛查询，先看候选再下载。

## 搜索与筛选

优先级：用户已有素材 → 明确可下载的公共素材库 → 用户指定平台或页面 → 通用网页搜索。可使用浏览器检查候选页面的真实画面、时长、分辨率、作者/页面信息和下载入口。

选择候选时检查：

- 画面是否真正满足动作和机位，而不是只匹配标题。
- 时长是否覆盖剪辑点前后余量。
- 分辨率、方向、帧率和运动质量是否适配成片。
- 水印、烧录字幕、Logo、压缩伪影和镜头抖动是否可接受。
- 来源页面、作者/发布者、许可或用户给定的使用说明是否可记录。

## 下载并登记

执行脚本前将本 Skill 目录解析为绝对路径并记作 `source_skill_dir`。

先检查依赖：`ffprobe` 用于所有媒体验证，网页视频下载还需要 `yt-dlp`。macOS 缺少时可使用 `brew install ffmpeg yt-dlp`；Python 环境也可用 `python3 -m pip install yt-dlp`。不要在未确认当前环境包管理方式时自动改动系统依赖。

已有网页 URL 时使用 `yt-dlp`：

```bash
python3 "$source_skill_dir/scripts/source_media.py" download \
  --url URL \
  --shot-id S003 \
  --output-dir /ABSOLUTE/STAGING/assets \
  --manifest /ABSOLUTE/PROJECT/sources.json
```

直接媒体 URL 使用 `--direct`；只登记已存在的本地文件使用 `add-local`。先运行 `inspect-url` 可查看 yt-dlp 元数据而不下载。完整字段见 [references/manifest-schema.md](references/manifest-schema.md)。

脚本必须：拒绝覆盖现有文件、限制输出到给定目录、下载到临时文件、用 ffprobe 验证媒体流、计算 SHA-256，并原子更新清单。日志中不写 Cookie、Token 或完整签名查询串。

## 为剪辑准备素材

1. 每个采用文件分配稳定 `asset_id` 并关联 `shot_id`。
2. 保留原始下载文件；转码、裁切、去音频等操作写入派生文件。
3. 记录 `in`/`out` 候选、画面用途和弃用原因。
4. 把最终采用项交给 `$video-editing`，把全部来源清单交给 `$video-qc`。

不要把搜索结果页、HTTP 200、扩展名或下载器退出码当作媒体验收。只有本地文件非空、ffprobe 能识别音视频流、哈希已写入清单，才算完成下载。

---
name: seedance-video-continuation
description: 从已有 MP4 的最后有效画面继续生成下一段 Seedance 视频，覆盖尾帧提取、公开 HTTPS 素材核验、first_frame 续拍、角色与镜头连续性提示、分段拼接和成片验收。用户要求尾帧续拍、视频接龙、延长 AI 视频、保持上一镜头继续生成、根据最后一帧生成下一段或拼接多段 Seedance 视频时使用。
---

# Seedance 尾帧续拍

把每次续拍分成“确定性媒体处理”和“计费生成”两段。上一段的最后有效画面必须成为下一段请求的 `first_frame`，不能只在提示词里描述上一段。

执行脚本前，将本 `SKILL.md` 所在目录解析为绝对路径并记作 `continuation_skill_dir`。不要假定当前工作目录就是 Skill 目录。

## 建立续拍合同

开始前明确：上一段 MP4、下一段动作、模型、时长、画幅、分辨率、声音策略、分段输出、拼接输出和允许消耗的额度。默认沿用上一段画幅与分辨率；Seedance 2.x 参考素材优先使用 720p。

真实生成前确认用户已授权本次计费。一次只提交一个 smoke，失败或连续性不合格时不要自动批量重试。

## 提取最后有效帧

先检查 `ffmpeg` 与 `ffprobe`，再提取距离结尾约一帧的画面，避开容器尾部空帧：

```bash
python3 "$continuation_skill_dir/scripts/video_continuation.py" extract \
  --source previous.mp4 \
  --output staging/previous-last-frame.png
```

脚本拒绝覆盖已有文件。成片若以淡出、黑场或转场结束，增大 `--seconds-before-end`，并目视确认选择的是希望延续的画面。

## 上传并核验首帧

Seedance 上游必须能匿名访问参考图。将 PNG 上传到公共 HTTPS URL；URL 不能依赖 Cookie、Authorization、内网或短于任务周期的临时签名。随后核验远端内容与本地帧完全一致：

```bash
python3 "$continuation_skill_dir/scripts/video_continuation.py" verify-url \
  --frame staging/previous-last-frame.png \
  --url https://media.example.invalid/previous-last-frame.png
```

没有合规上传位置时停止，不要把本地路径或 `file://` URL 发给生成接口。

## 生成下一段

使用同仓库或已安装的 `seedance-video-generation` 脚本，把核验后的 URL 作为 `--first-frame`：

```bash
python3 "$continuation_skill_dir/../seedance-video-generation/scripts/seedance_video.py" generate \
  --model seedance-2 \
  --prompt "保持小猪外观、舞台、光线和镜头方向一致，小猪接着上一动作继续跳舞" \
  --first-frame https://media.example.invalid/previous-last-frame.png \
  --duration 5 \
  --resolution 720p \
  --ratio 9:16 \
  --output staging/next.mp4
```

需要端点、凭证、模型限制或任务轮询细节时，读取相邻的 `seedance-video-generation/SKILL.md`。当前 `lovskills video` 若 `--help` 中没有 `--first-frame`，不得用纯文本请求冒充尾帧续拍；等待该入口支持参考图，或在用户明确授权后改用已配置的 new-api 路径。

提示词只描述下一段发生的变化，同时锁定主体身份、服装/纹理、场景、光线、镜头方向和运动趋势。更详细的连续性合同见 [references/continuity-contract.md](references/continuity-contract.md)。

## 拼接并验收

单独保留每一段，再生成拼接版：

```bash
python3 "$continuation_skill_dir/scripts/video_continuation.py" stitch \
  --previous previous.mp4 \
  --next staging/next.mp4 \
  --output staging/continued.mp4 \
  --trim-next-start 0.033
```

只有两段分辨率、帧率和音频流结构一致时才拼接。`--trim-next-start` 可去除下一段开头重复的一帧；不确定时设为 `0`，先看原始衔接。

验收至少覆盖：

- 抽取上一段尾帧、下一段首帧和接缝前后代表帧，检查角色、构图、光线与运动方向。
- 用 `ffprobe` 核对时长、分辨率、帧率、视频/音频流和文件大小。
- 播放接缝前后 1 秒，检查跳帧、静音、爆音、重复帧和动作突变。
- 报告每次任务 ID、计费事实、分段路径、拼接路径，以及未通过的连续性问题。

生成成功不等于续拍成功。只有真实 MP4 可播放、边界连续且证据齐全，才算完成。

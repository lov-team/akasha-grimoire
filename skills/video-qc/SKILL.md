---
name: video-qc
description: 对视频成片、预览和生成片段执行联合质量验收，覆盖 ffprobe/FFmpeg 解码、时长、分辨率、帧率、音视频流、黑帧、冻结、静音、响度、字幕，以及代表帧、人物/商品连续性、镜头方向、叙事节奏、开场与结尾兑现、来源完整性。用户要求检查视频质量、验收成片、诊断导出、检查黑帧静音、生成 QA 报告或判断视频是否完成时使用。
---

# 视频成片验收

把机器可测指标、视觉抽查和完整播放分开记录。退出码或模型任务成功只证明处理完成。

## 运行技术检查

执行脚本前将本 Skill 目录解析为绝对路径并记作 `qc_skill_dir`：

```bash
python3 "$qc_skill_dir/scripts/check_video.py" /ABSOLUTE/PATH/final.mp4 \
  --report /ABSOLUTE/PROJECT/qa/technical.json \
  --frames-dir /ABSOLUTE/PROJECT/qa/frames
```

按项目合同传入 `--width`、`--height`、`--fps`、时长或响度阈值。脚本执行完整解码、媒体探测、黑帧/冻结/静音检测、响度分析和代表帧提取；有 SRT 时传 `--srt`。无声片必须显式传 `--allow-no-audio`。

## 视觉与叙事检查

读取 `technical.json` 和全部代表帧，再按 [references/review-rubric.md](references/review-rubric.md) 检查：

- 主体、商品、服装、道具、场景和光线连续性。
- 轴线、视线、运动方向、动作衔接和转场意义。
- 开场观看理由、信息推进、情绪曲线、镜头可读时间和结尾兑现。
- 字幕逐字准确性、安全区、断句和与说话者/画面的冲突。
- 对白、环境、音效和音乐的层级与空间连续性。

代表帧通过后仍必须完整播放一次；抽帧发现不了短闪、爆音、音画不同步和节奏问题。

## 追溯与裁决

将每个问题记录为：严重级别、时间码、`clip_id`/`shot_id`、观察事实、责任阶段和最小重跑范围。

- `blocker`：文件损坏、缺轨、错误画幅、关键事实/主体错误、严重连续性或来源缺失。
- `major`：明显黑帧、冻结、不同步、字幕错误、节奏或声音问题影响观看。
- `minor`：不阻断发布但应在下一版修复的问题。

仅当技术报告 `ok=true`、blocker/major 清零、来源清单覆盖所有采用素材且完整播放通过时，写入最终 PASS。不要用平均分抵消关键失败。

交付技术 JSON、代表帧目录、人工审阅 Markdown 和最终裁决。

---
name: remotion-video-production
description: Use when the user explicitly chooses Remotion or video-shotcraft for a complete video, requests code-driven motion graphics, interface or photo choreography, deterministic React video rendering, or a recoverable Remotion production package.
---

# Remotion 视频生产

用 Remotion 作为最终成片引擎，把 brief、镜头表、素材和声音交付为可恢复工程与通过验收的成片。点名 Remotion 或 video-shotcraft 已视为路线确定，直接执行。

## 锁定制作合同

读取已有 brief、脚本、分镜和素材。缺失时使用 `$video-director` 补齐。开始实现前集中确认尚未给出的平台、画幅、分辨率、帧率、时长、音乐和旁白；已有值直接沿用。完整合同和目录见 [references/production-contract.md](references/production-contract.md)。

Brief 完整时连续制作。只有视觉方向或最终分镜存在高成本分歧时暂停确认；工程参数、镜头实现和 SFX 钉帧由 Agent 决定。

## 处理素材缺口

先列出已具备素材、缺口、建议来源和会产生的模型调用。取得用户确认后再调用：静态视觉 `$gpt-image-generation`、视频片段对应视频模型 Skill、旁白 `$fish-audio-speech`、音乐 `$suno-music-generation`。Remotion 始终负责最终时间线与渲染。

## 使用 video-shotcraft

上游固定范围与升级规则见 [references/upstream-integration.md](references/upstream-integration.md)。每个采用镜头必须依次：

1. 从 `assets/video-shotcraft/library.json` 解析卡名、变体和 `source` 路径。
2. 将 `source` 的 `references/shots/` 前缀映射到 `references/video-shotcraft/shots/`，完整阅读对应卡片。
3. 按卡片“参考实现”读取准确 TSX：`demos/` 映射到 `assets/video-shotcraft/demos/`；`assets/lib/` 映射到 `assets/video-shotcraft/lib/`；指向 `template/src/aifl/` 的 9 张卡映射到 `assets/video-shotcraft/template-source/aifl/`。
4. 将 Demo 和 `assets/video-shotcraft/lib/` 所需组件复制到项目后适配；不要从 Skill 目录运行时 import。

镜头结构、运动语法和调校参数来自卡片；字体、配色、材质与信息层级来自目标内容。每镜只让一种动效担任主角，并为信息落定预留停留帧。

## 实现与声音

- 所有状态由 `useCurrentFrame()`、fps 和确定性输入计算。
- 禁用实时日期与非确定性随机数；需要粒子或抖动时使用固定种子。
- 有音乐时 Composition 提供 `bgm:boolean`；有旁白时提供 `voiceover:boolean`。
- 动作拟音从 `assets/video-shotcraft/audio/sfx/SFX_MANIFEST.json` 选择，使用 `scripts/fetch_shotcraft_sfx.py` 下载到当前生产项目并校验 SHA-256，再按场景起始帧加 offset 钉帧。Skill 中只保存来源和校验值，音频进入具体视频项目后使用。
- 带音乐项目从同一 Composition 渲染“BGM＋SFX”和“仅 SFX”两版，画面参数保持一致。
- 使用强节奏音乐时，先按 `references/video-shotcraft/music-beat-sync.md` 建立节拍网格再排时间线。

## 验收与交付

逐镜渲染静帧，整片渲染后运行：

```bash
python3 scripts/validate_remotion_delivery.py /ABS/PROJECT \
  --composition COMPOSITION_ID --video /ABS/PROJECT/render/final.mp4 \
  --width WIDTH --height HEIGHT --fps FPS --duration-frames FRAMES \
  --report /ABS/PROJECT/qa/remotion-validation.json
```

有第二版、非默认关键帧目录或字幕时追加 `--sfx-only-video`、`--keyframes-dir`、`--captions`；省略 `--keyframes-dir` 时默认检查 `qa/keyframes/`。随后使用 `$video-qc` 检查黑帧、冻结、静音、响度、字幕、连续性和完整播放。

交付前派干净上下文 Agent，按 `references/video-shotcraft/final-review.md` 对照 brief、分镜、镜头卡、准确 Demo、成片和关键帧独立终检。Blocker 与 major 清零后交付源码、素材、时间线、渲染命令、成片、关键帧、设计说明和 QA 报告。默认写入独立本地内容包；发布或写入业务仓库由用户另行指定。

能力示例见[案例四：雪后故宫旧纸手帐 Remotion Case](../../docs/cases/snowy-forbidden-city-remotion-case.md)：用 8 段确定性时间线组合终端打字、纸片重构、双色套印、Before/After、SFX 钉帧和双版本渲染。

# 视频号口播项目合同

## 默认目录

```text
PROJECT/
├── project/
│   └── sources.json
├── source/
│   └── source.sha256
├── editorial/
│   ├── transcript-verbatim.json
│   ├── semantic-map.md
│   ├── cut-plan.csv
│   ├── edl.json
│   ├── visual-overlay-plan.json
│   └── captions.srt
├── assets/
│   ├── selected-frames/
│   ├── b-roll/
│   └── cover-background.png
├── render/
│   ├── rough-v1.mp4
│   └── final.mp4
├── deliverables/
│   ├── final.mp4
│   ├── captions.srt
│   ├── cover-3x4.png
│   └── publish-copy.md
└── qa/
    ├── technical.json
    ├── final-transcript.json
    ├── caption-sync-report.json
    ├── visual-review.md
    ├── verification.md
    └── frames/
```

源视频本体和大体积媒体可位于仓库外；`source.sha256`、编辑决策与 QA 记录必须保留绝对来源路径和哈希。
外部图片、视频和文献在 `project/sources.json` 记录原页面、作者、许可、本地路径和文件哈希。

## 默认制作参数

| 项目 | 默认值 |
| --- | --- |
| 平台 | 微信视频号 |
| 画幅 | 9:16，1080×1920 |
| 帧率 | 30fps；源素材为 25fps 且无混帧需求时可保持 25fps |
| 视频 | H.264，yuv420p，Fast Start |
| 音频 | AAC，48kHz，双声道 |
| 主画面 | A-roll 真人默认始终存在；资料优先画中画，不长期全屏遮挡 |
| 字幕 | 最终声音锁定后重新 STT；每屏不超过两行，不用字数比例推时 |
| 封面 | 3:4，1080×1440 PNG；中心 1:1 裁切仍可读 |
| 首版剪辑 | 保留 90%—100% 有效语义句 |

这些值是缺省合同，不覆盖用户明确给出的时长、画幅、风格或发布要求。

## 阶段门

1. **Source Ready**：绝对路径、SHA-256、时长、旋转/显示方向和代表帧一致，源文件可完整解码。
2. **Meaning Locked**：逐字稿校正，语义图完整，所有 `must_keep` 已标记。
3. **Cut Approved**：`cut-plan.csv` 可回溯，粗剪完整播放后没有意思缺失。
4. **Picture Locked**：A-roll、画中画、画面节奏和最终声音完成；此门之后才从最终音轨重做字幕。
5. **Captions Locked**：最终音轨 STT、术语校正、SRT 和同步报告完成，烧录抽查无漂移或断词。
6. **Cover Locked**：封面、标题和简介与成片一致，缩略图可读。
7. **Delivery Passed**：最终编码文件的技术 QA 与人工完整播放均通过，响度和真峰值为最终 AAC 实测值。

## 失败回退

- 意思缺失：回到 Meaning Locked，只恢复对应原始片段并更新 EDL。
- 跳切突兀：回到 Cut Approved，增加 handle、J/L cut、轻微变焦或合理 B-roll。
- 字幕错误：以最终声音为事实源重新定时，不沿用旧 SRT。
- 画中画遮人：保持已锁定声音和 A-roll，仅修改 `visual-overlay-plan.json` 的位置、尺寸或时段后重渲染。
- 封面不好看：保留已确认成片和文案，仅重做封面底图或排版。
- 标题不兑现：改标题和简介，不反向篡改内容迎合标题。

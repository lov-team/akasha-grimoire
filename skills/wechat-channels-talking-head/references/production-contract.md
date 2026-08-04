# 视频号口播项目合同

## 默认目录

```text
PROJECT/
├── source/
│   └── source.sha256
├── editorial/
│   ├── transcript-verbatim.json
│   ├── semantic-map.md
│   ├── cut-plan.csv
│   ├── edl.json
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
    ├── visual-review.md
    └── frames/
```

源视频本体和大体积媒体可位于仓库外；`source.sha256`、编辑决策与 QA 记录必须保留绝对来源路径和哈希。

## 默认制作参数

| 项目 | 默认值 |
| --- | --- |
| 平台 | 微信视频号 |
| 画幅 | 9:16，1080×1920 |
| 帧率 | 30fps；源素材为 25fps 且无混帧需求时可保持 25fps |
| 视频 | H.264，yuv420p，Fast Start |
| 音频 | AAC，48kHz，双声道 |
| 字幕 | 每屏不超过两行，按最终音轨定时 |
| 封面 | 3:4，1080×1440 PNG；中心 1:1 裁切仍可读 |
| 首版剪辑 | 保留 90%—100% 有效语义句 |

这些值是缺省合同，不覆盖用户明确给出的时长、画幅、风格或发布要求。

## 阶段门

1. **Source Ready**：源文件可完整解码，哈希已记录。
2. **Meaning Locked**：逐字稿校正，语义图完整，所有 `must_keep` 已标记。
3. **Cut Approved**：`cut-plan.csv` 可回溯，粗剪完整播放后没有意思缺失。
4. **Picture Locked**：字幕、画面节奏、B-roll 和声音完成。
5. **Cover Locked**：封面、标题和简介与成片一致，缩略图可读。
6. **Delivery Passed**：技术 QA 与人工完整播放均通过。

## 失败回退

- 意思缺失：回到 Meaning Locked，只恢复对应原始片段并更新 EDL。
- 跳切突兀：回到 Cut Approved，增加 handle、J/L cut、轻微变焦或合理 B-roll。
- 字幕错误：以最终声音为事实源重新定时，不沿用旧 SRT。
- 封面不好看：保留已确认成片和文案，仅重做封面底图或排版。
- 标题不兑现：改标题和简介，不反向篡改内容迎合标题。

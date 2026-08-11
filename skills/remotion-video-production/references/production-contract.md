# Remotion 生产合同

## 开工输入

锁定：受众、平台、时长、画幅、宽高、fps、核心信息、视觉方向、素材边界、字幕、音乐、旁白和交付格式。用户已提供的值直接写入 brief；其余字段一次集中确认。

## 项目目录

```text
project/
├── brief.md
├── design.md
├── storyboard.md
├── timeline.json
├── commands.md
├── package.json
├── src/
├── public/
├── render/
└── qa/
    ├── keyframes/
    ├── remotion-validation.json
    ├── technical.json
    └── final-review.md
```

`design.md` 记录视觉 tokens、镜头卡映射、准确 Demo 路径和适配取舍。`storyboard.md` 为每镜记录帧区间、画面、字幕、素材、转场与 SFX。`timeline.json` 是按播放顺序排列的场景数组，每项至少包含 `id`、`from`、`durationInFrames`；区间必须从第 0 帧连续覆盖到总帧数。每镜关键帧命名为 `<scene-id>-f<frame>.png` 并放入 `qa/keyframes/`。`commands.md` 保存安装、Studio、静帧、双版渲染和验证命令。

## Composition 合同

- Composition id 使用项目语义名称。
- 宽高、fps、总帧数由 brief 固定；场景区间连续覆盖 `[0, durationInFrames)`。
- 有音乐时 props 包含 `bgm:boolean`，默认 `true`；第二版传 `false`。
- 有旁白时 props 包含 `voiceover:boolean`，默认 `true`。
- 字幕每屏最多两行并位于平台安全区。
- `Date.now()` 与 `Math.random()` 视为验收失败；伪随机从固定 seed 派生。

## 交付门禁

1. `npx remotion compositions` 能解析目标 Composition。
2. 每镜至少一张静帧，开头、中段、结尾和转场均有代表帧。
3. 最终文件为 H.264/AAC，完整解码通过。
4. 有 BGM 时两版使用同一时间线，宽高、fps、帧数和逐帧解码哈希一致。
5. Remotion 专项验证、`$video-qc` 和独立终检全部通过。

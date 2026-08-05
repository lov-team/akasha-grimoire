# 最终音轨字幕对齐

## 事实源与阶段门

字幕时间只以最终成片音轨为事实源。先锁定 A-roll、补录/TTS、停顿、变速、J/L cut 和混音，再从最终音轨重新 STT。旧逐字稿可校正文案，不能沿用旧时间码，也不能按段落字数比例分摊时长。

## 确定性流程

1. 导出最终音轨并生成带逐字或逐词 `start/end` 的 STT JSON。
2. 复制 `assets/caption-terms.json`，校正人名、机构、模型、奖项、数字和术语；校正文案继承原音对应词的首尾时间，不移动周围锚点。顶层标点仍需人工读顺，脚本只自动修复少量明显的助词断句。
3. 用顶层带标点文本恢复自然语义边界，再把字符顺序映射回时间段。
4. 删除字幕显示中的“嗯、呃、啊”等语气词，但保留其前后原始时间锚，不拉伸邻句填空。
5. 用术语表把不可拆词合为一个时间单元；长句按真实字符时间和停顿拆分，不按平均语速估计。
6. 生成 SRT 和同步报告，检查无重叠、每屏最多两行、时间范围有效、术语未跨屏或跨行拆开。

推荐命令：

```bash
python3 scripts/align_final_captions.py \
  --transcript /ABSOLUTE/PROJECT/qa/final-transcript.json \
  --terms /ABSOLUTE/PROJECT/editorial/caption-terms.json \
  --output /ABSOLUTE/PROJECT/editorial/captions.srt \
  --report /ABSOLUTE/PROJECT/qa/caption-sync-report.json
```

术语文件可使用：

```json
{
  "protected_terms": ["OpenAI", "形式化证明", "菲尔兹奖"],
  "replacements": {
    "ASR中的错误文本": "审核后的正确文本"
  }
}
```

替换项必须可在逐字时间段中找到，并继承被替换原文的首尾时间。不要用替换功能改写讲话者没有说过的内容。

## 排版回退

先探测 FFmpeg：`ffmpeg -filters`。若缺少 `subtitles`、`ass` 或 `drawtext`，用 Pillow 按 SRT 生成透明 RGBA 字幕帧/视频，再以支持 alpha 的中间编码（如 `qtrle`/`argb`）overlay；不得因滤镜缺失跳过字幕核验。

## 回验

- 抽查钩子、专名密集处、中段机制、长停顿前后和结尾。
- 重新打开烧录成片，不能只看 SRT 文本。
- 最终 AAC 编码后再次确认画面字幕与实际听感一致。
- 保留旧字幕版本；发现漂移时回到最终音轨 STT，不在错误 SRT 上整体平移掩盖问题。

---
name: wechat-channels-talking-head
description: 将已有中文口播、采访或知识讲解素材剪成语义完整、节奏自然、适合微信视频号发布的成片，并生成参考风格封面、吸睛标题、简介和发布包。用户要求剪口播、删停顿和口误但保留原意、修复“剪掉太多意思”的版本、制作视频号竖屏成片、模仿参考封面风格、生成封面标题或整理发布文案时使用。
---

# 视频号口播精剪与封面

把论证完整度放在节奏之前。先锁定讲话者真正表达的命题和推理链，再剪停顿、口误和重复；不按“短就是好”压缩观点。

## 绑定项目

1. 读取源视频、用户反馈、参考封面、已有转写、字幕、EDL、预览和 QA 记录。
2. 以最新确认版本为起点，只修复第一个未完成环节；用户指出“意思被剪没”时，恢复受影响语义段，不重新粗暴压缩全片。
3. 对源视频计算 SHA-256 并只读保存；编辑副本、代理和大体积媒体放在仓库外 staging。
4. 默认使用 Akasha 的本地脚本、FFmpeg 和下列 REQUIRED SUB-SKILL，不使用 gigglecut。
5. 按 [references/production-contract.md](references/production-contract.md) 建立项目目录和验收合同。

## 先锁定语义，再决定剪点

1. 探测音视频流并生成带时间码的逐字转写；专有名词、数字和引用必须人工回听。
2. 复制 [assets/semantic-map.md](assets/semantic-map.md)，写出核心命题、论证链、必要定义、例证、转折、限定和结论。
3. 复制 [assets/cut-plan.csv](assets/cut-plan.csv)，逐段标记：
   - `safe_cut`：纯静音、无意义语气词、完整重复、明确口误后的废弃版本；
   - `review`：看似重复但承担递进、转折、情绪或解释作用；
   - `must_keep`：命题、因果桥、定义、例证、反方回应、限定和结论。
4. 第一版保留 90%—100% 的有效语义句，只做保守净化。不得剪掉抽象概念之间的连接句；“数学—经典思想—AI”这类跨域主题尤其要保留定义、类比边界和推导桥梁。
5. 每个删除决定记录原始时间码、逐字内容、删除理由和对语义链的影响。无法证明“删除后命题不变”的片段先保留。

详细判定规则见 [references/semantic-editing.md](references/semantic-editing.md)。

## 完成口播剪辑

**REQUIRED SUB-SKILL:** 使用 `$video-editing` 建立可追溯 `edl.json` 并确定性渲染。

1. 先按转写完成 A-roll 粗剪，再处理画面节奏；不要先凭波形批量删静音。
2. 删除停顿时保留自然呼吸和句间余量，避免切掉辅音、尾音、笑声或思考感。硬跳切前后保留小 handle。
3. 优先用轻微 punch-in、字幕层级、关键词卡片和少量 B-roll 缓解视觉疲劳，不靠高频跳切制造节奏。
4. B-roll 只覆盖有明确视觉解释价值的句子；主体观点、重要表情和个人判断优先保留真人画面。
5. 字幕从最终音轨重新定时，每屏不超过两行；姓名、书名、术语、数字和引文逐字回听。
6. 默认输出 1080×1920、30fps、H.264/AAC；源画幅或用户合同不同则以合同为准。

需要修补单个口误或补录短句时，**REQUIRED SUB-SKILL:** 使用 `$fish-audio-speech` 的已绑定私人声线和 S2.1 `--style`；生成后用 STT 回验并与原声响度、房间感和节奏匹配。原声可用时不整段替换。

## 生成封面与发布文案

1. 从成片选取表情清楚、眼神自然、留有文字空间的高清帧。用户提供参考封面时，提取构图、色彩、字重、层级和留白，不复制人物或品牌元素。
2. 背景或概念视觉需要生成时，**REQUIRED SUB-SKILL:** 使用 `$gpt-image-generation`；参考图要显式作为 edits 输入。让模型生成无文字底图，中文标题用本 Skill 的脚本确定性排版。
3. 先写 5 个标题候选，再选 1 个封面标题：8—16 个汉字优先，包含具体矛盾或认知收益，不夸大成片没有兑现的结论。
4. 按 [references/cover-and-copy.md](references/cover-and-copy.md) 完成 `cover-brief.md` 与 `publish-copy.md`。
5. 渲染 3:4 视频号封面母版：

```bash
python3 scripts/render_cover.py \
  --image /ABSOLUTE/PATH/cover-background.png \
  --title "数学·道德经|AI的底层联系" \
  --subtitle "它们都在寻找世界背后的结构" \
  --label "认知与技术" \
  --output /ABSOLUTE/PROJECT/deliverables/cover-3x4.png
```

标题中的 `|` 表示编导指定的换行位置，避免自动排版拆开专有名词。

6. 实际查看封面，并检查 3:4 全图和中心 1:1 裁切：脸、主标题和核心视觉不能被裁断，缩略图下仍须一眼可读。

## 验收与交付

**REQUIRED SUB-SKILL:** 使用 `$video-qc` 完成完整解码、黑帧/冻结/静音/响度、代表帧、字幕和完整播放验收。

另外逐项审查：

- `semantic-map.md` 的每个 `must_keep` 是否都能在成片定位；
- 前 3 秒是否给出观看理由，但没有为了钩子改变原意；
- 跳切是否自然，口型、手势和环境声是否连续；
- 封面承诺、标题、简介是否由成片内容兑现；
- 成片、封面和文案是否重新打开并实际查看。

交付 `final.mp4`、`captions.srt`、`semantic-map.md`、`cut-plan.csv`、`edl.json`、渲染记录、`cover-3x4.png`、`publish-copy.md` 和 QA 报告。任何 blocker/major 未清零时继续修订，不把预览当成最终成片。

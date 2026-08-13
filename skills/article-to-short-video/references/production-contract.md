# 文章转 Remotion 视频制作合同

## 目录约定

```text
topic/
├── article.md
├── images/                         # 已确认使用的事实图片
├── video_project/
│   ├── narration.md                # 核心判断、小标题、页面结论和旁白
│   ├── narration_tts.txt
│   ├── visual-contract.md          # 排版方向和逐页动效说明
│   ├── captions.json               # Remotion Caption[]
│   ├── captions.srt
│   ├── timeline.ts                 # 页面、字幕和 SFX 的唯一时间线
│   └── src/                        # Remotion 工程
└── production-record.md            # 五个确认门和素材来源

staging-outside-repo/
├── voice/
├── music/
├── sfx/
├── samples/
├── final/
└── qa/
```

仓库内文件表达可重复的决策；仓库外目录承载可再生成的大文件。

## 五个确认门

| 门 | 提交给用户 | 放行后才能做 |
|---|---|---|
| 1 内容 | 核心判断、逐页标题/结论/旁白、预计时长 | 排版设计 |
| 2 视觉 | 2—3 种方向、选定方向的逐页动效和转场 | 声音与画面样片 |
| 3 声音 | 8—15 秒合成样片；样片确认后的全文旁白和完整配乐 | 最终时间线 |
| 4 时间线 | 最终页面帧、完整句字幕、SFX 表 | 完整渲染 |
| 5 成片 | 两版 MP4、代表帧、QA 报告 | 宣称完成 |

用户明确说“直接生成”不等于跳过确认门。用户只能在看过当前门交付物后确认该门。

## 分页与视觉合同

- 门 1 先确认全片传播重点和观众反应，再为每页指定唯一传播任务；两者必须写入内容合同。
- 一个小标题对应一个页面，标题是旁白章节、Remotion 场景和时间线的共同 ID。
- 页面只表达一个核心结论。过载时先精简，仍过载再拆出有独立含义的小标题，最后才延长总时长。
- 生成图片或页面图前先确认全片背景；记录颜色、材质、空间感及其与传播重点的关系。
- 每页文字分镜固定包含：`标题 / 唯一传播任务 / 唯一视觉事件 / 页面目的 / 主视觉 / 信息层级 / 必要元素 / 出现顺序 / 停留 / 转场 / 音效意图`。
- 页面只保留标题、关键词、数字和必要短句；删除英文眉题、页码、分类标签、下一页提示及无旁白依据的小字，不通过缩小字号容纳正文。
- 每页围绕一个核心判断与必要证据建立唯一视觉焦点，排除同权卡片和旁白逐句陈列；遮住辅助文字后仍应能看出页面重点。
- 动效前先用前端同时展示全部页面的完整静态终态，所有必要元素均可见；逐页检查空间利用率、安全区、遮挡、重叠和无意义空白。
- 每页一个主动画，使用内容对象自身的位移、形变、筛选、汇聚或传递解释内容；信息落定后必须留出可读停顿，转场延续上一页的元素或语义。
- 画面禁止播放进度、百分比完成条、横纵阶段线和伪装成流程传递的进度 UI；先后关系直接通过内容对象的动作表达。

## Remotion 时间线

最终旁白确定后再计算时间线，所有时间统一落到整数帧。页面时长、顺序和 SFX 只在一个中央文件维护：

```ts
export const CAPTION_LEAD_MS = 150;

export const PAGES = [
  {id: 'context', title: '上下文为什么会爆炸', from: 0, duration: 240},
  {id: 'handoff', title: '跨会话如何传递', from: 240, duration: 300},
] as const;

export const SFX = [
  {pageId: 'context', offset: 12, src: 'transition/transition-soft.mp3', role: 'primary'},
  {pageId: 'handoff', offset: 18, src: 'transition/swoosh-quick.mp3', role: 'primary'},
] as const;

export const absoluteSfxFrame = (item: (typeof SFX)[number]) => {
  const page = PAGES.find((candidate) => candidate.id === item.pageId);
  if (!page) throw new Error(`Unknown SFX page: ${item.pageId}`);
  return page.from + item.offset;
};
```

改变任一页面的 `duration` 或顺序后，重新累计所有 `from`，并重新生成该页及后续字幕、转场和 SFX 绝对帧；不要手工平移散落在组件里的 `<Audio>`。

## 字幕合同

- Remotion 内部使用 `@remotion/captions` 的 `Caption[]`；同时导出 UTF-8 SRT 供交付和检查。
- `startMs = max(0, voiceStartMs - CAPTION_LEAD_MS)`，默认提前量为 150ms；不得因提前造成上一条字幕重叠。
- 每条字幕是一句完整语义句，序号连续、时间递增、不重叠且不超过成片时长。
- 每屏最多两行；单行优先控制在 16—18 个中文字符内，视觉中心约在 y=1540—1600，并保留平台安全区。
- 两行放不下时回改旁白并重合成受影响语句；不缩小字号、不删改意思、不在句中硬切。
- TTS 可以展开易误读缩写，字幕保留受众熟悉的正确写法。人名同音字不能只依赖 STT，必须人工试听。

## 声音合同

### 合成样片

先选最能代表全片的一页制作 8—15 秒合成样片。它必须包含最终候选音色、BGM、至少一个转场 SFX、至少一个关键动作 SFX、临时完整句字幕和基础动效。用户确认合成关系后才批量生成；批量完成后提交全文旁白和完整配乐供用户试听，两者确认后才进入最终时间线。

### 三层总线

| 总线 | 起始目标 | 关系 |
|---|---|---|
| VOICE | 约 -16 LUFS | 始终保证最高可懂度 |
| BGM | 约 -25～-22 LUFS | 由 VOICE sidechain ducking，停顿时缓慢恢复 |
| SFX | VOICE=100 时默认 10—15 | Remotion 从 `volume={0.1—0.15}` 起步；不压或盖住 VOICE，重要钉点只短暂压 BGM 2—4 dB |

同一时刻一个主 SFX、最多一个辅助 SFX。主音效默认不超过 `0.15`，辅助音效还要更低；以旁白听感为 `100` 时，最终合成中的 SFX 保持在约 `10—15`。长尾跨页时避开下一页同频段声音，长样本按动作显式截断。素材偏轻时先按 `video-shotcraft/references/sound-design.md` 换音色或预归一化，不通过把单条 Remotion `volume` 抬过 `0.15` 来补偿；用户明确要求强化某个钉点时，才单独调整并重新提交合成样片。

FFmpeg 混音起点：

```text
[voice] loudnorm=I=-16:LRA=7:TP=-1.5, asplit
[music] atrim=0:<duration>, afade=in/out, loudnorm=I=-23:LRA=9:TP=-3
[music][voice-control] sidechaincompress=threshold=0.035:ratio=4:attack=20:release=400
[voice][ducked-music][sfx] amix=normalize=0, alimiter=limit=0.95
```

数值只是起点。分别试听说话段、停顿段和转场峰值，终渲检查整体 LUFS 与 True Peak。

## 动态时长验收

成片期望时长来自最终 Remotion 时间线，不使用固定 90 秒默认值，也不从待验 MP4 反推期望值。检查时用 `sum(PAGES.duration) / fps` 得到 `EXPECTED_DURATION_SECONDS`，再显式传入 `--duration`：

```bash
# 例：timeline.ts 导出的总帧数为 1674，fps 为 30。
EXPECTED_DURATION_SECONDS="$(python3 -c 'print(1674 / 30)')"

python3 scripts/validate_short_video.py \
  ./staging/final-with-bgm.mp4 \
  --duration "$EXPECTED_DURATION_SECONDS" \
  --duration-tolerance 0.05 \
  --srt ./video_project/captions.srt \
  --report ./staging/validation.json
```

交付前人工抽查钩子页、信息最密页、转场最复杂页和结尾页；核对标题与旁白一致性、文字安全区、完整句字幕、音画钉帧、来源和 AI 意象声明。

成片反馈必须重开最早受影响的确认门：旁白/标题/分页回门 1，排版/动效/转场回门 2，音色/BGM/SFX 回门 3，字幕/时长/钉帧回门 4。重新确认后再渲染，不能在门 5 静默修改。

## 证据边界

- 人物履历、奖项和本人言论优先使用官方机构、大学主页或本人公开账号。
- 网友二创不能写成本人事实；作者分析不能伪装成当事人自述。
- 授权不明的视频只作研究参考，不直接截入成片。
- AI 意象不代表真实实验、邮件、地点或人物经历，片尾要明确声明。

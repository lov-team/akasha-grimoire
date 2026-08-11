# 雪后故宫旧纸手帐 Remotion Case

## 案例目标

把“一张照片如何经过图片 Skill 变成旧纸手帐海报”制作成一支 35 秒竖屏 Case Film。观众既能看清最终海报，也能理解 Prompt、留白、纸张质感、朱红色块和套印效果分别做了什么。

[▶ 播放或下载 35 秒仅 SFX 预览](../assets/snowy-forbidden-city-remotion-case-sfx-preview.mp4)

![雪后故宫旧纸手帐 Remotion 案例八镜头联系表](../assets/snowy-forbidden-city-remotion-case-contact-sheet.jpg)

## 能力边界

- 上游图片步骤使用 `gc-minimal-zine-poster-v0-1`，输入为用户提供的雪后故宫照片，输出为旧纸手帐海报。
- `gc-minimal-zine-poster-v0-1` 在本案例中仅代表素材来源；Akasha 展示的能力从已提供原图与海报素材进入 Remotion 编排开始。
- `remotion-video-production` 负责叙事拆解、镜头卡选型、代码动画、字幕、SFX、双版本渲染和最终 QA。
- 视频渲染过程只读取本地素材，未在运行时调用图片或视频模型。

## 制作合同

| 项目 | 结果 |
| --- | --- |
| Composition | `GcZineCaseC` |
| 画幅 | 1080 × 1920，9:16 |
| 帧率与时长 | 30 fps，1050 帧，35 秒 |
| 输入参数 | `bgm:boolean` |
| 文案 | 中文字幕，无旁白，每屏最多两行 |
| 视觉 | 旧纸 `#E9E1CF`、墨黑 `#24201C`、朱红 `#DC3F2E` |
| 字体 | 系统宋体；终端使用 Menlo |
| 确定性 | 动画由帧号计算，固定输入，运行时无网络素材 |

## 八段时间线

| # | 帧 | 画面任务 | Remotion 实现 |
| ---: | ---: | --- | --- |
| 1 | 0–89 | “一张普通照片，如何变成旧纸手帐？” | 编辑部大字 Hook，先建立问题再进入工具流程 |
| 2 | 90–209 | 展示雪后故宫原图 | 纸框承载原图，克制推近，保留故宫中轴、雪屋顶、红墙和雾气 |
| 3 | 210–359 | 展示 Skill 名和四段式 Prompt | `terminal-typewriter`，2 帧一个字符，方波光标，结果出现前做一次快速推近 |
| 4 | 360–539 | 主体缩小并放入 3:5 纸张 | 用尺寸和位置插值把照片从普通展示转成小型视觉锚点 |
| 5 | 540–689 | 扩大留白，加入撕边、网点和扫描颗粒 | 纸张图层依次建立，胶带拍定后减弱主体晃动并收薄投影 |
| 6 | 690–809 | 朱红色块与双色错版套准 | `misregistration-hit` 让色块和错版文字共同撞入、震荡，再硬切套准 |
| 7 | 810–929 | 完整海报揭晓 | 900 × 1500 海报静止展示 120 帧，让观众读完整体构图 |
| 8 | 930–1049 | 原图与海报 Before/After | `before-after-slider-scrub` 完成快甩、回弹、停顿、慢扫和末段静止 |

## video-shotcraft 镜头卡适配

| 镜头卡 | 本案例中的用途 | 保留的动作语法 |
| --- | --- | --- |
| `terminal-typewriter` | 展示 Skill 名和真实 Prompt 关键词 | 逐字出现、方波光标、结果前快速推近 |
| `masking-tape-slap` | 让照片从悬浮纸片变成被固定的手帐材料 | 胶带扑入、压扁、停晃、阴影收薄 |
| `misregistration-hit` | 强调唯一朱红色锚点和双色套印 | 共同撞入、衰减震荡、残余错位、硬切套准 |
| `before-after-slider-scrub` | 同尺寸比较原图与最终海报 | 快甩、回弹、阅读停顿、慢速扫动、定格 |

镜头卡提供运动结构与调校基线；旧纸材质、故宫照片、朱红色块和中文信息层级来自本案例内容。每个场景只保留一个主要动作，信息落定后留出阅读帧。

## 确定性与声音

- 所有场景使用固定 `from` 和 `durationInFrames`，连续覆盖 0–1049 帧。
- SFX 统一使用 `SCENES.<name>.from + offset` 定位；调整场景起点时，声音会随场景整体移动。
- 源码扫描未发现 `Math.random()`、`Date.now()` 或运行时日期。
- 同一 Composition 通过 `bgm:boolean` 输出 BGM＋SFX 与仅 SFX 两版，两个版本的视频轨逐帧一致。

公开预览使用以下 [video-shotcraft SFX manifest](../../skills/remotion-video-production/assets/video-shotcraft/audio/sfx/SFX_MANIFEST.json) 中的 Mixkit 音效：

| SFX | 用途 | 来源 |
| --- | --- | --- |
| `typewriter-digital` | Prompt 逐字输入 | [Mixkit 1363](https://assets.mixkit.co/active_storage/sfx/1363/1363-preview.mp3) |
| `typewriter-return-bell` | 终端回车落点 | [Mixkit 1383](https://assets.mixkit.co/active_storage/sfx/1383/1383-preview.mp3) |
| `paper-slide` | 纸片移动 | [Mixkit 1530](https://assets.mixkit.co/active_storage/sfx/1530/1530-preview.mp3) |
| `paper-scissors-cut` | 撕边与裁切 | [Mixkit 2378](https://assets.mixkit.co/active_storage/sfx/2378/2378-preview.mp3) |
| `paper-staple` | 胶带与纸张拍定 | [Mixkit 2995](https://assets.mixkit.co/active_storage/sfx/2995/2995-preview.mp3) |
| `swoosh-quick` | 快速推近和滑块甩动 | [Mixkit 166](https://assets.mixkit.co/active_storage/sfx/166/166-preview.mp3) |

## 成片验收

| 项目 | BGM＋SFX 母版 | 仅 SFX 母版 |
| --- | ---: | ---: |
| 视频规格 | 1080 × 1920、30 fps、1050 帧 | 1080 × 1920、30 fps、1050 帧 |
| 编码 | H.264 / AAC | H.264 / AAC |
| 容器时长 | 35.000 秒 | 35.000 秒 |
| 音频 | 48 kHz、双声道 | 48 kHz、双声道 |
| 完整解码 | 通过 | 通过 |
| 黑帧 | 0 | 0 |
| True Peak | -3.6 dBFS | -5.5 dBFS |

- 两版视频轨 `framemd5` 完全一致，PSNR 为 `inf`。
- 八段时间线连续覆盖全部 1050 帧，字幕最多两行。
- 完整海报从第 810 帧起静止展示 120 帧。
- 独立终检关闭了文字可读性、海报停留时间和镜头卡动作还原问题，最终 blocker 与 major 均为 0。

## 公开预览

公开仓库使用仅 SFX 的网页预览副本：

| 项目 | 结果 |
| --- | --- |
| 视频 | H.264、540 × 960、30 fps、1050 帧 |
| 音频 | AAC、48 kHz、双声道 |
| 容器时长 | 35.008 秒 |
| 文件大小 | 1,396,722 字节 |
| SHA-256 | `8befbf3d069af88c0b072de0252ccdeb9bbc249686957c0ecd70ed64f175f3e9` |
| 完整解码 | 通过 |
| 联系表 | 1080 × 960、4 × 2、132,393 字节 |
| 联系表 SHA-256 | `5958a2ecdf50962bc9b8e6a6008c986cb436e622c6daedad29d9fa3d678c17b2` |

高分辨率双版本母版、原始照片、独立海报、Prompt 响应和完整 Remotion 工程继续保存在本地案例包中。

## 案例结论

这个案例展示的重点不是“Remotion 生成了一张海报”，而是：**Remotion 把素材生成过程变成了可读、可控、可复验的动态叙事**。同一套方法也适合界面操作演示、产品能力讲解、照片故事、图文教程和确定性品牌短片。

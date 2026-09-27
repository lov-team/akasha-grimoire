---
name: h3-kling-video-generation
description: Write Context-IR prompts for or generate videos with MiniMax H3 Max/H3 or Kling, including T2V, I2V, first/last frames, references, and game PVs.
---

# H3 与 Kling 视频生成

使用 [`scripts/video_generation.py`](scripts/video_generation.py) 提交异步任务。真实生成会计费；未明确要求生成时，只运行 `--help`、`lint`、单元测试和本地 mock。

## 选择模型

- `h3-max`（默认）→ `h3-max`：5–15 秒，`480P`/`768P`/`1080P`。无图为文生视频（画幅默认 `16:9`，不支持 `adaptive`）；一张 `--image` 为首帧图生视频；带 `--reference-video`/`--reference-audio` 时转参考生视频。两张及以上图片有歧义，脚本直接报错，改用下面的显式 SKU。
- `h3-max-i2v` → `minimax/h3-max/image-to-video`：一张 `--image` 为首帧，两张依次为首帧、尾帧；画幅由首帧决定。
- `h3-max-reference` → `minimax/h3-max/reference-to-video`：图片、视频、音频参考合计最多 12 个；画幅默认 `adaptive`。
- `h3-max-t2v` → `minimax/h3-max/text-to-video`：纯文生视频，画幅默认 `16:9`。
- `h3`/`minimax-h3` → `minimax-h3/text-to-video`；`h3-i2v` → `minimax-h3/image-to-video`：旧 H3，4–15 秒，`768P`/`2K`，仅用于明确的模型偏好。
- `kling-3` → `kling-3.0/video`：3–15 秒，支持单镜头参考图、声音和 `std`/`pro`/`4K`。
- `kling-2.5-t2v` → `kling/v2-5-turbo-text-to-video-pro`：5 或 10 秒，纯文生视频。

完整字段约束见 [`references/model-contracts.md`](references/model-contracts.md)。不要把其他供应商的字段混入请求。

## H3 Prompt：制作单 ≠ 模型 Prompt

H3 只按官方 **Context-IR** 格式理解 Prompt：英文、固定字段、`[Shot N]` 编号镜头。先读 [`references/h3-context-ir-prompting.md`](references/h3-context-ir-prompting.md)。每个镜头准备两份文件：

1. **中文制作单**：复制 [`assets/h3-shot-plan-template.md`](assets/h3-shot-plan-template.md)，写镜头定位、请求参数、后期与验收，只留在本地；
2. **英文模型 Prompt**：按模式复制 `assets/h3-prompt-t2va.txt`、`h3-prompt-i2va.txt`、`h3-prompt-fl2va.txt` 或 `h3-prompt-ref2va.txt`，填写后用 `--prompt-file` 提交。

核心规则：

- Prompt 只描述目标视频中看得见、听得见的内容；时长理由、剪辑区间、后期 MG／UI／字幕和“不要……”一类指令都不写。
- I2VA／FL2VA 第一行是固定对齐行；Ref2VA 用六段结构和 `<Subject N>`／`<Picture N>`／`<Video N>`／`<Audio N>` 标签，编号与请求素材顺序一致。
- 对白写 `(S1) says: <d>[English] ...</d>`；画面文字写在英文双引号里；正式字幕交给后期。
- Context-IR Prompt 默认以 `prompt_expansion_mode=disabled` 提交，不让网关再次改写。

| 用途 | 模式 | CLI |
| --- | --- | --- |
| 概念 smoke | T2VA | `--model h3-max --aspect-ratio 16:9` |
| 已有首帧（正式镜头默认） | I2VA | `--model h3-max-i2v --image FIRST` |
| 首尾帧 | FL2VA | `--model h3-max-i2v --image FIRST --image LAST` |
| 组合参考素材 | Ref2VA | `--model h3-max-reference --image ... [--reference-video ...] [--reference-audio ...] --aspect-ratio 9:16` |

正式角色镜头先用 `$gpt-image-generation` 按交付画幅生成并验收首帧，再做 I2VA／FL2VA；需要组合多个参考、复用嗓音或动作参考时用 Ref2VA；T2VA 只做概念 smoke。时长选能容纳动作、台词和落幅的最短整数秒，预算方法见写作规范第 8 节。

游戏宣传 PV、二维赛璐璐与 Editorial MG 合成任务先读 [`references/game-pv-motion-design.md`](references/game-pv-motion-design.md)，用 [`assets/game-pv-prompt-template.txt`](assets/game-pv-prompt-template.txt) 建立全片视觉系统和拆镜。PV 总表不发送给模型，每个生成镜头再单独写 Context-IR Prompt。

## 生成

先 lint（本地检查，不联网、不计费）：

```bash
python3 skills/h3-kling-video-generation/scripts/video_generation.py lint \
  --prompt-file shots/s01.txt --model h3-max-i2v --images 1 --duration 5
```

`generate` 遇到 Context-IR Prompt 时会在提交前自动做同样的检查，有错误就不提交（确需绕过时传 `--skip-lint`）；遇到普通文字 Prompt 时提示它将被扩写器改写。

H3 Max 首帧图生视频：

```bash
python3 skills/h3-kling-video-generation/scripts/video_generation.py generate \
  --model h3-max-i2v \
  --prompt-file shots/s01.txt \
  --image https://media.example/s01-first-frame.png \
  --duration 5 \
  --resolution 768P \
  --seed 42 \
  --output renders/s01.mp4
```

概念 smoke 可以只写一句英文，交给官方扩写器改写，再从 sidecar 的 `expanded_prompt` 学习写法：

```bash
python3 skills/h3-kling-video-generation/scripts/video_generation.py generate \
  --model h3-max \
  --prompt "A lighthouse keeper climbs a spiral staircase at night, lantern in hand" \
  --prompt-expansion quality \
  --aspect-ratio 16:9 \
  --output renders/concept.mp4
```

Kling 3.0 参考图单镜头：

```bash
python3 skills/h3-kling-video-generation/scripts/video_generation.py generate \
  --model kling-3 \
  --prompt "The subject turns toward camera; preserve identity and clothing" \
  --image https://media.example/subject.png \
  --duration 5 \
  --mode pro \
  --sound \
  --output renders/kling-3.mp4
```

复杂 Kling 3.0 多镜头或元素引用用 `--metadata-json` 传原生 `multi_shots`、`multi_prompt` 与 `kling_elements`；显式 CLI 的时长、画幅、模式、声音和图片会覆盖同名字段。

成功时输出三行：

- `OK task_id=... output=... bytes=...`
- `MEDIA codec=... pixels=WxH fps=... duration=... audio_streams=...`（需要本机 `ffprobe`；时长与请求相差超过 1 秒时另有警告）
- `SIDECAR <output>.json`：记录模型、请求参数（不含素材 URL）、Prompt、seed、`expanded_prompt`（网关返回时）和媒体信息，用于复现和 A/B 对比。

## H3 生产闭环

用户已明确批准真实生成，且镜头计划、参考图和输出目录齐全时，直接从当前未完成步骤继续；不要重复确认模型、时长、费用或是否生成。仅在缺少会实质改变结果的关键输入，或输出覆盖冲突时暂停。

1. 为每个镜头填写制作单，确定模式、时长和素材顺序；
2. 生成并验收首帧（I2VA／FL2VA）或参考素材（Ref2VA）；
3. 写 Context-IR Prompt 并通过 `lint`；
4. 用一个代表镜头以 `5 秒 + 768P` 做方向 smoke，通过后再批量提交；
5. 验收每个结果：`MEDIA` 行符合请求，完整解码，抽取首、中、尾帧，确认身份、动作和起止状态；
6. 不合格时一次只改一个变量（Prompt 的一处描述、首帧或一个请求参数），固定 `--seed` 重跑，并在制作单记录结论。

提交前先用 `/v1/models` 确认实际 SKU。公共 HTTPS 参考素材上传后必须重新匿名下载，核对 SHA-256、字节数、MIME 和像素尺寸，任一不符立即更换托管端点。首帧按交付画幅生成，不指望模型把 3:4 扩展成 9:16。字幕、标题、UI 文字和精确卡点交给后期；正式配音或配乐项目丢弃模型音轨；全片最后一镜在时长预算里留出结束保持，收尾交给 `$video-editing`。

遇到 H3 路由或上游失败时，读 [`references/model-contracts.md`](references/model-contracts.md) 的“已验证故障与恢复”，按已验证字段修复后继续，不重复付费试错。

## 协议与配置

- 提交：`POST /v1/video/generations`。
- 轮询：`GET /v1/video/generations/{task_id}`。
- 下载：`GET /v1/videos/{task_id}/content`。
- Base URL 优先级：`--base-url`、`H3_KLING_VIDEO_BASE_URL`、共享 Akasha 凭证、默认 `https://llmapi.lovbrowser.com/v1`；不读取 `OPENAI_BASE_URL`。
- Key 优先级：本地 `OPENAI_API_KEY`、统一的 `LOVBROWSER_API_KEY`、共享 Akasha 凭证；忽略媒体专用 Key，不得写入命令、日志或仓库。

输出文件已存在时脚本在提交前就报错；只有需要覆盖时才传 `--overwrite`。脚本校验 MP4 `ftyp` 签名并原子写入。

## 余额不足

仅官方入口返回可充值的 `insufficient_user_quota` 时使用共享充值控制器；整条命令至多充值一次并只重试失败请求一次。用户主动充值时运行仓库根目录的 `python3 shared/akasha_recharge.py --recharge-usd 金额`。

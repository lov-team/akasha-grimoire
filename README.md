<div align="center">

# Akasha Grimoire · 阿卡夏秘典

**把一次成功的 Agent 协作，沉淀成团队可以反复调用的能力。**

[![Agent Skills](https://img.shields.io/badge/Agent_Skills-23-6C5CE7?style=flat-square)](#能力目录)
[![Best on Codex App](https://img.shields.io/badge/Best_on-Codex_App-111827?style=flat-square)](#graph-engineering)
[![Languages](https://img.shields.io/badge/Languages-中文_·_English_·_日本語-2D9CDB?style=flat-square)](#)
[![Source of Truth](https://img.shields.io/badge/Source_of_Truth-Git-2EA44F?style=flat-square)](#设计原则)
[![License: Apache 2.0 + Commercial](https://img.shields.io/badge/License-Apache_2.0_%2B_Commercial-F59E0B?style=flat-square)](LICENSE)

**简体中文** · [English](README.en.md) · [日本語](README.ja.md)

</div>

---

Akasha Grimoire 是团队共享的 Agent Skill 合集，最佳使用环境是 **Codex App**。它把任务边界、工具事实、执行脚本、低噪声等待和独立验收组织成可安装的能力包，让 Agent 在真实项目中少猜、少重复轮询，并用证据完成交付。其他兼容 Agent 与 CLI 仍可使用其中的独立 Skill。

> **想直接体验图片、视频、语音和音乐生成？** 访问 [LovBrowser](https://lovbrowser.com) 注册账号并开通额度。阿卡夏秘典默认连接 `https://newapi.1234bot.com/v1`，拿到一把 new-api Key 后即可调用 GPT Image、Grok、Seedance、MiniMax H3、Kling、Fish Audio 与 Suno，无需逐项配置 Base URL。

## 一分钟开通

1. 在 Codex 中直接要求 GPT Image、Grok、Seedance、MiniMax H3、Kling、Fish Audio 或 Suno 执行媒体任务。
2. 首次缺少 Key 时，Agent 会生成 LovBrowser 设备授权二维码，并同时显示可点击链接与短码。
3. 用手机扫码，注册或登录后确认同一短码；本机随后自动轮询、保存凭证并用 `/v1/models` 验证。
4. 验证成功后，最初的媒体任务自动继续一次。真实 Key 不经过对话、剪贴板或命令参数。

也可运行 `python3 shared/akasha_credentials.py status|start|finish|cancel|rollback` 管理配置。凭证默认保存到 `~/.config/akasha/credentials.env`。已有环境变量仍兼容，优先级为专用变量 > `NEW_API_API_KEY` > 用户凭证 > `OPENAI_API_KEY`。

## 为什么使用

- **合同优先**：先明确触发条件、输入输出、禁止项和完成标准。
- **事实驱动**：CLI 版本、参数、端点和限制以当前运行环境及可靠实现为准。
- **低噪声执行**：把固定轮询和机械动作交给脚本，保留 token 给判断与 Review。
- **独立验收**：worker 自述不能替代累计 diff、测试、产物和远端事实核查。
- **唯一事实源**：仓库是通用 Skill 的唯一来源，本地通过符号链接安装。

## Graph Engineering

Graph Engineering 把交付建模为一张可追踪的工作图，而不是一串临时 prompt：

`Spec → Epic → Issue → Agent Task → Evidence`

| 层级 | 职责 |
| --- | --- |
| **Spec** | 定义目标、边界、非目标、关键决策和最终验收，作为根合同 |
| **Epic** | 把 Spec 拆成里程碑子图，组织跨 Issue 依赖和汇总验收 |
| **Issue** | 最小可执行节点，包含 owner、范围、依赖、输出与验证 |
| **Agent Task** | Issue 在 Codex App 或外部 worker 中的运行实例，不替代 Issue 事实 |
| **Evidence** | 用 diff、测试、产物、Review 与远端 SHA 关闭 Issue，并向上关闭 Epic 和 Spec |

所有需要实施和验收的工作都由 Issue 驱动。任务必须映射到 Issue；依赖以 `depends_on`、`blocks`、`produces`、`validates` 关系边表达；只有依赖已满足的节点才能并行。方向变化先更新 Spec/Epic/Issue，完成状态则按 Evidence 自底向上汇总。Codex App 负责展示任务、承载隔离 worktree、长等待与验收闭环，因此是这套方法的首选控制平面。

## 能力目录

### 协作与治理

| Skill | 适用场景 | 核心能力 |
| --- | --- | --- |
| [`agent-task-supervisor`](skills/agent-task-supervisor/) | 用 Spec/Epic/Issue 图谱监工、协调和验收多个任务 | Issue 制定计划/验收矩阵；Sol Codex worker 按难度选择 thinking 开发；直接父层负责 monitor |
| [`codex-app-development`](skills/codex-app-development/) | 由独立 Issue 计划/验收任务创建 Codex App 开发会话 | Epic 监工 → Issue 计划/验收 → Sol 按难度选择 thinking 的 developer、隔离 worktree 与独立 diff Review |

### 内容生产

| Skill | 适用场景 | 核心能力 |
| --- | --- | --- |
| [`content-pipeline`](skills/content-pipeline/) | 把中文想法、文章、资料或中断任务制作成小红书式图文内容包 | 内容合同、来源研究、原文忠实度、文案、内容地图、HTML/CSS 卡片、按需生图和移动端 QA |

单独安装 `content-pipeline` 可完成纯文字 HTML/CSS 卡片；需要生成照片或插画时，同时安装 `gpt-image-generation` 和 `akasha-key-setup`。

### 视频生产

| Skill | 适用场景 | 核心能力 |
| --- | --- | --- |
| [`video-production`](skills/video-production/) | 从创意、文章、脚本或已有素材生产完整视频 | 编导 → 素材/生成 → EDL 剪辑 → 技术与创作 QA 的阶段门总编排 |
| [`h3-kling-video-generation`](skills/h3-kling-video-generation/) | 用 H3 与 Kling 生成导演级镜头 | MiniMax H3、Kling 3.0 / 2.5 的 Prompt 编排、模型级校验、异步轮询与 MP4 安全下载 |
| [`video-director`](skills/video-director/) | 编剧、导演、分镜、镜头表和生成前规划 | 叙事节拍、镜头覆盖、摄影运动、连续性 Bible 和生成计划 |
| [`video-source-research`](skills/video-source-research/) | 搜索、下载和整理 B-roll、视频、图片或音频素材 | 逐镜查询、yt-dlp/直接下载、ffprobe、SHA-256 和可追溯 `sources.json` |
| [`video-editing`](skills/video-editing/) | 通用粗剪、精剪、B-roll、声音、字幕和导出 | 可审阅 `edl.json`、确定性 FFmpeg 渲染、缺音轨补齐与输出复验 |
| [`video-qc`](skills/video-qc/) | 生成片段、预览和最终成片验收 | 完整解码、黑帧/冻结/静音/响度/字幕、代表帧和叙事连续性审阅 |
| [`article-to-short-video`](skills/article-to-short-video/) | 把中文长文、人物故事或观点稿制作成 60—120 秒竖屏短视频 | 在通用视频生产闭环上增加证据边界、Fish 旁白、Suno 配乐和竖屏专项验收 |

完整安装建议同时启用以上六个通用视频 Skill；未指定模型时，`video-production` 默认按 MiniMax H3 → Grok → Seedance 2.0 的顺序选择第一个满足镜头能力的直生视频入口；Kling、Gemini Omni 及其他专用能力按用户指定或镜头硬约束选用。静态视觉、旁白和音乐继续分别路由到 GPT Image、Fish Audio 与 Suno。网页视频下载额外需要 `yt-dlp`，确定性剪辑和 QA 需要 FFmpeg/ffprobe。

### 图像、游戏与音频

| Skill | 适用场景 | 核心能力 |
| --- | --- | --- |
| [`game-asset-forge`](skills/game-asset-forge/) | 角色、场景、UI、图标、Tileset、特效、Sprite 和动画帧 | 资产合同、先 smoke 后批量、透明度与 halo、角色一致性、动画循环、2×2 tile、引擎导入和截图验收 |
| [`gpt-image-generation`](skills/gpt-image-generation/) | GPT Image 生图、参考图编辑和端点诊断 | OpenAI-compatible generations/edits、base URL 归一化、结果安全落盘、协议限制和失败诊断 |
| [`grok-media-generation`](skills/grok-media-generation/) | Grok 图片/视频生成与编辑 | 调用 OpenAI-compatible 媒体端点，以当前 CPA 的 `video.file_id` resolver 续接生成结果，静默轮询并安全下载真实文件 |
| [`suno-music-generation`](skills/suno-music-generation/) | 用歌曲描述或自定义歌词生成音乐 | 提交 Suno 异步任务、本地每 5 秒静默检查、下载多首音频/封面/可选视频并逐项验收 |
| [`fish-audio-speech`](skills/fish-audio-speech/) | Fish Audio 配音、声音参考和录音转写 | 通过 OpenAI-compatible 音频接口完成 TTS/STT，支持 reference id、本地参考音频、语言、时间戳控制与安全落盘 |

### App 子任务与 CLI 开发 worker

开发默认采用三层闭环：**Epic 监工 App 找到 ready Issue → 独立 Issue App 制定实现计划与验收矩阵 → 使用 GPT-5.6 Sol、按任务难度选择 thinking 的 Codex worker 实现 → Issue App 独立 Review 并把 P0–P2 发回原 worker → Issue 写 Evidence 供 Epic 读取**。所有代码开发默认直接使用隔离的 Codex App task/worktree，不再按前端、后端或任务规模自动切换 worker；纯媒体生成仍使用对应媒体技能。用户点名其他开发 worker 时遵从指定，只替换最底层 worker。Issue App 始终不写业务代码。每次单向下发后，直接父层启动一个最长 20 分钟、每 20 秒扫描状态/交付文件的 monitor。

| Skill | Worker | 特点 |
| --- | --- | --- |
| [`gemini-cli-development`](skills/gemini-cli-development/) | Gemini CLI | 用户明确指定 Gemini CLI 时使用 |
| [`grok-cli-development`](skills/grok-cli-development/) | Grok CLI | 用户明确指定 Grok CLI 时使用；内置媒体任务仍可单独调用 |
| [`codex-app-development`](skills/codex-app-development/) | Codex App developer | 所有代码开发的默认 worker；GPT-5.6 Sol、按任务难度选择 thinking |
| [`claude-code-cli-development`](skills/claude-code-cli-development/) | Claude Code | 权限模式、会话续接、状态交付与独立验收 |
| [`codex-cli-development`](skills/codex-cli-development/) | Codex CLI | 在独立交互 TUI 中实施，不与 Codex App 任务管理混用 |

## 实战案例：为亚马逊拖鞋卖家制作商品视觉

下面是一套在真实调用中完成的跨境电商样例。Agent 先锁定“雾蓝色人体工学 EVA 云朵拖鞋”的颜色、鞋面凹槽和厚底轮廓，再生成亚马逊白底主图、浴室上脚图与材质细节图，最后分别调用 Grok 和 Seedance 生成 5 秒商品视频并完成解码、参数与抽帧验收。

![亚马逊拖鞋白底主图](docs/assets/amazon-slippers-main.jpg)

| 交付物 | 使用能力 | 实际结果 |
| --- | --- | --- |
| 白底主图、场景图、细节图 | `gpt-image-generation` / `gpt-image-2` | 1536 px 商品图，白底主图四角为纯白 |
| 商品棚拍视频 | `grok-media-generation` / `grok-imagine-video` | 5.04 秒，848 × 480，24 fps |
| 商品旋转视频 | `seedance-video-generation` / `doubao-seedance-2-0-260128` | 5.04 秒，1280 × 720，24 fps |

![Grok 与 Seedance 拖鞋视频抽帧对比：上方为 Grok，下方为 Seedance](docs/assets/amazon-slippers-video-comparison.jpg)

这个案例也说明了生产边界：纯文生视频可以快速验证方向，但商品颜色、凹槽和鞋底结构仍可能漂移。正式上架时应提供真实样品图，通过图生视频锁定商品身份，并对“防滑”“防水”“缓震”等卖点准备真实测试或供应商证据。

## 实战案例：60 秒《一枚鸡蛋的幕后团队》

这支梵净山鸡蛋搞笑宣传片用 Seedance 2.0 生成 4 段 × 15 秒的竖屏 3D 动画，通过同一枚拟人鸡蛋角色、上一段真实尾部视频与全屏前景遮挡保持连续性。内容明确呈现现代化笼养和自动化集蛋流程，不用鸡窝或山坡散养画面误导观众。

[![60 秒《一枚鸡蛋的幕后团队》封面](docs/assets/fanjingshan-eggs-behind-team-poster.jpg)](docs/assets/fanjingshan-eggs-behind-team-60s.mp4)

[▶ 播放或下载 60 秒完整视频](docs/assets/fanjingshan-eggs-behind-team-60s.mp4) · [查看完整案例与验收记录](docs/cases/fanjingshan-eggs-behind-team.md)

| 验收项 | 实际结果 |
| --- | --- |
| 成片参数 | 60 秒、720 × 1280、24 fps、1440 帧、H.264/AAC |
| 养殖表达 | 明确标注“3D 动画流程示意｜非企业实拍”；不出现鸡窝、草地散养或山坡奔跑 |
| 饲料与营养 | 只展示玉米、豆粕等配方饲料原料；营养信息以产品标签和检测报告为准 |
| 连续性 | 红色幕布、浅棕饲料袋、深蓝笔记本三处授权遮挡转场；如实披露为非原生像素无缝 |

## 快速安装

克隆仓库后，优先用符号链接安装，让仓库持续充当唯一事实源。

```bash
git clone git@github.com:lov-team/akasha-grimoire.git
cd akasha-grimoire
```

安装单项 Skill：

```bash
skill_name="suno-music-generation"
skills_home="${CODEX_HOME:-$HOME/.codex}/skills"
mkdir -p "$skills_home"
ln -s "$PWD/skills/$skill_name" "$skills_home/$skill_name"
```

安装全部 Skill，并保留已有目标：

```bash
skills_home="${CODEX_HOME:-$HOME/.codex}/skills"
mkdir -p "$skills_home"

for skill_dir in "$PWD"/skills/*; do
  skill_name="$(basename "$skill_dir")"
  target="$skills_home/$skill_name"
  if [ -e "$target" ] || [ -L "$target" ]; then
    echo "保留已有目标：$target"
  else
    ln -s "$skill_dir" "$target"
  fi
done
```

不要使用强制覆盖。若目标已存在，先审计差异，并用可恢复方式保留未知内容。

## 使用示例

在 Codex 中直接点名 Skill：

```text
使用 $agent-task-supervisor 轻量监工这些任务，并在交付后独立验收。

使用 $agent-task-supervisor 把这份 Spec 拆成 Epic/Issue 依赖图，在 Codex App 中只启动已就绪的 Issue，并用证据自底向上关闭整张图。

使用 $codex-app-development 让当前 Issue 任务先制定实现计划与验收矩阵，再创建 GPT-5.6 Sol、按任务难度选择 thinking 的独立 Codex App worker；开发会话只实现，Issue 任务独立 Review 并把 P0–P2 发回原会话。

使用 $content-pipeline 把这篇中文文章制作成一套小红书图文；保留原意，先确认封面方向，最后交付可恢复的本地内容包。

使用 $video-production 把这份产品创意制作成 30 秒竖屏视频：先完成编导包和镜头表，再搜索或生成素材、输出 EDL、渲染并做完整成片 QA。

使用 $video-source-research 为这份镜头表检索 B-roll，下载采用项并输出带 ffprobe 元数据和 SHA-256 的 sources.json。

使用 $game-asset-forge 为 2D 游戏制作一套透明背景角色动画帧，先 smoke 再批量。

使用 $grok-media-generation 生成或编辑这段图片/视频，并验收下载后的真实文件。

使用 $suno-music-generation 根据这段歌曲描述生成音乐，并下载所有候选结果。

使用 $fish-audio-speech 把旁白文本合成为语音，并检查开头、中段和结尾。
```

## 凭证与运行环境

| 能力 | 配置来源 | 约定 |
| --- | --- | --- |
| 默认 new-api | `https://newapi.1234bot.com/v1` | 无需配置 Base URL；充值签票也支持 `llmapi.lovbrowser.com` 与 `llmapi-direct.lovbrowser.com` 官方入口；私有部署才用 `NEW_API_BASE_URL` 或 `--base-url` 覆盖 |
| GPT Image | `IMAGE_PROXY_API_KEY`、`NEW_API_API_KEY` 或 `OPENAI_API_KEY` | 不把 key 写进命令参数、prompt、日志或仓库 |
| Grok / Seedance | 专用 key、`NEW_API_API_KEY` 或 `OPENAI_API_KEY` | 真实调用会计费，先做单个 smoke，再扩大任务规模 |
| Suno / Fish Audio | `NEW_API_API_KEY` 或 `OPENAI_API_KEY` | 真实调用会消耗额度；基础测试不调用外部服务 |
| 官方主动/余额不足充值 | 运行 `python3 shared/akasha_recharge.py` 创建支付会话；金额在 LovBrowser 页面选择 | 主动充值不需要余额不足；仅官方 new-api；Agent 只给出可点击的 `publicPageUrl`，不显示二维码；不泄露 Key/票据 |
| Codex App 三层任务 | Epic 监工 task、Issue 计划/验收 task、Sol 按难度选择 thinking 的 developer task/worktree | Epic→Issue→developer 单向下发；Issue 先计划再委托并独立验收完整 diff |
| CLI worker | 本机已安装的对应 CLI、macOS Terminal、tmux | 首次使用或版本变化时重新核对 `--version` 与 `--help` |
| 视频剪辑与素材 | FFmpeg/ffprobe；网页下载另需 yt-dlp | macOS 可使用 `brew install ffmpeg yt-dlp`；下载后仍必须探测媒体并记录来源与哈希 |

## 验证

每个 Skill 都包含标准 frontmatter 和 `agents/openai.yaml`。修改后至少运行：

```bash
validator="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"
for skill_dir in skills/*; do
  python3 "$validator" "$skill_dir"
done

git diff --check
```

新增脚本还必须执行语法检查和无副作用行为测试。涉及生图、音乐、语音、视频或外部写入时，默认先使用本地假服务或 smoke；未真实端到端验证的能力必须明确披露。

## 目录与维护

```text
skills/<skill-name>/
├── SKILL.md              # 触发描述与核心工作合同
├── agents/openai.yaml    # Agent UI 元数据
├── scripts/              # 可重复、确定性的执行逻辑（按需）
├── references/           # 工具事实与专项合同（按需）
└── assets/               # 可复制到交付物中的模板与资源（按需）
```

- Skill 正文保持简洁，复杂事实放到一层 `references/` 中渐进披露。
- 不在 Skill 目录加入 README、变更日志、缓存或过程总结。
- 修改 CLI/API 合同时重新核对真实版本、帮助信息、schema 和可靠实现。
- 正式交付前通读累计 diff，检查 TODO、凭证、本机绝对路径、缓存和生成产物。
- 推送后核对本地 SHA、远端 SHA 和关键文件内容。

## 许可证

当前版本采用 [Apache License 2.0 + 附加商业条件](LICENSE)：非商业支付使用按 Apache 2.0 条款授权；生产环境中的商业支付使用，累计支付总额不超过 1,000,000 美元（USD 1,000,000）免费，超过前须取得书面商业授权。该组合许可证不是未经修改的 Apache License 2.0。完整说明见 [授权说明](LICENSING.md)，中文商业条件见 [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)。

此前按 GPLv3 发布的版本仍适用原许可证。

---

<div align="center">

**让 Agent 的能力不只存在于一次会话，而成为团队可以验证、复用和进化的工作系统。**

</div>

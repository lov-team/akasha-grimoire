<div align="center">

# Akasha Grimoire · 阿卡夏秘典

**把一次成功的 Agent 协作，沉淀成团队可以反复调用的能力。**

[![Agent Skills](https://img.shields.io/badge/Agent_Skills-10-6C5CE7?style=flat-square)](#能力目录)
[![Languages](https://img.shields.io/badge/Languages-中文_·_English_·_日本語-2D9CDB?style=flat-square)](#)
[![Source of Truth](https://img.shields.io/badge/Source_of_Truth-Git-2EA44F?style=flat-square)](#设计原则)

**简体中文** · [English](README.en.md) · [日本語](README.ja.md)

</div>

---

Akasha Grimoire 是团队共享的 Agent Skill 合集。它把任务边界、工具事实、执行脚本、低噪声等待和独立验收组织成可安装的能力包，让 Agent 在真实项目中少猜、少重复轮询，并用证据完成交付。

## 为什么使用

- **合同优先**：先明确触发条件、输入输出、禁止项和完成标准。
- **事实驱动**：CLI 版本、参数、端点和限制以当前运行环境及可靠实现为准。
- **低噪声执行**：把固定轮询和机械动作交给脚本，保留 token 给判断与 Review。
- **独立验收**：worker 自述不能替代累计 diff、测试、产物和远端事实核查。
- **唯一事实源**：仓库是通用 Skill 的唯一来源，本地通过符号链接安装。

## 能力目录

### 协作与治理

| Skill | 适用场景 | 核心能力 |
| --- | --- | --- |
| [`agent-task-supervisor`](skills/agent-task-supervisor/) | 监工、协调、等待和验收多个任务 | 维护紧凑任务板；Codex App 按当前 120 秒上限等待，外部 Agent 用 240 秒静默脚本；只在阻塞、偏航、正式 Review 或 P0–P2 时下钻 |

### 图像、游戏与音频

| Skill | 适用场景 | 核心能力 |
| --- | --- | --- |
| [`game-asset-forge`](skills/game-asset-forge/) | 角色、场景、UI、图标、Tileset、特效、Sprite 和动画帧 | 资产合同、先 smoke 后批量、透明度与 halo、角色一致性、动画循环、2×2 tile、引擎导入和截图验收 |
| [`gpt-image-generation`](skills/gpt-image-generation/) | GPT Image 生图、参考图编辑和端点诊断 | OpenAI-compatible generations/edits、base URL 归一化、结果安全落盘、协议限制和失败诊断 |
| [`grok-media-generation`](skills/grok-media-generation/) | Grok 图片/视频生成与编辑 | 通过 new-api 调用媒体端点，以当前 CPA 的 `video.file_id` resolver 续接生成结果，静默轮询并安全下载真实文件 |
| [`suno-music-generation`](skills/suno-music-generation/) | 用歌曲描述或自定义歌词生成音乐 | 提交 Suno 异步任务、本地每 5 秒静默检查、下载多首音频/封面/可选视频并逐项验收 |
| [`fish-audio-speech`](skills/fish-audio-speech/) | Fish Audio 配音、声音参考和录音转写 | 通过 new-api 完成 TTS/STT，支持 reference id、本地参考音频、语言、时间戳控制与安全落盘 |

### CLI 开发 worker

四项 CLI Skill 采用同一个闭环：**主 Agent 定义合同 → 可见 Terminal + tmux 中实施 → 轻量状态/交付文件 → 主 Agent 独立 Review → 复用同一会话返工**。它们不会采集 worker 的思考过程，也不会把需求判断外包给 CLI。

| Skill | Worker | 特点 |
| --- | --- | --- |
| [`grok-cli-development`](skills/grok-cli-development/) | Grok CLI | 开发、图像/视频生成、中文计划、自检与同会话返工 |
| [`gemini-cli-development`](skills/gemini-cli-development/) | Gemini CLI | 依据本机真实 CLI 合同执行开发与交付闭环 |
| [`claude-code-cli-development`](skills/claude-code-cli-development/) | Claude Code | 权限模式、会话续接、状态交付与独立验收 |
| [`codex-cli-development`](skills/codex-cli-development/) | Codex CLI | 在独立交互 TUI 中实施，不与 Codex App 任务管理混用 |

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

使用 $game-asset-forge 为 2D 游戏制作一套透明背景角色动画帧，先 smoke 再批量。

使用 $grok-media-generation 通过 new-api 生成或编辑这段图片/视频，并验收下载后的真实文件。

使用 $suno-music-generation 根据这段歌曲描述生成音乐，并下载所有候选结果。

使用 $fish-audio-speech 把旁白文本合成为语音，并检查开头、中段和结尾。
```

## 凭证与运行环境

| 能力 | 配置来源 | 约定 |
| --- | --- | --- |
| GPT Image | `IMAGE_PROXY_BASE_URL`、`IMAGE_PROXY_API_KEY`，或兼容的 OpenAI 环境变量 | 不把 key 写进命令参数、prompt、日志或仓库 |
| Grok 媒体 | 默认 `https://llmapi.lovbrowser.com/v1`；key 使用 `GROK_MEDIA_API_KEY` 或 `OPENAI_API_KEY`，端点可用 `--base-url`、`GROK_MEDIA_BASE_URL`、`OPENAI_BASE_URL` 依次覆盖 | 不内置 key；真实调用会计费，先做单个 smoke，再扩大任务规模 |
| Suno / Fish Audio | `NEW_API_BASE_URL`、`NEW_API_API_KEY`，或兼容的 OpenAI 环境变量 | 真实调用会消耗额度；基础测试不调用外部服务 |
| CLI worker | 本机已安装的对应 CLI、macOS Terminal、tmux | 首次使用或版本变化时重新核对 `--version` 与 `--help` |

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
└── references/           # 工具事实与专项合同（按需）
```

- Skill 正文保持简洁，复杂事实放到一层 `references/` 中渐进披露。
- 不在 Skill 目录加入 README、变更日志、缓存或过程总结。
- 修改 CLI/API 合同时重新核对真实版本、帮助信息、schema 和可靠实现。
- 正式交付前通读累计 diff，检查 TODO、凭证、本机绝对路径、缓存和生成产物。
- 推送后核对本地 SHA、远端 SHA 和关键文件内容。

---

<div align="center">

**让 Agent 的能力不只存在于一次会话，而成为团队可以验证、复用和进化的工作系统。**

</div>

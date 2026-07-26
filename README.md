# Akasha Grimoire（阿卡夏秘典）

团队共享的 Agent Skill 合集。仓库是通用 Skill 的唯一事实源。

## Skills

- `agent-task-supervisor`：轻量监工多个任务并独立验收。
- `game-asset-forge`：生成并验收可直接导入引擎的游戏资产。
- `gpt-image-generation`：通过 OpenAI-compatible GPT Image 端点生图、改图和诊断。
- `suno-music-generation`：通过 new-api 生成歌曲，静默等待并下载验收结果。
- `fish-audio-speech`：通过 new-api 完成 Fish Audio TTS 与 STT。
- `grok-cli-development`：在可见 Terminal + tmux 中驱动 Grok CLI。
- `gemini-cli-development`：在可见 Terminal + tmux 中驱动 Gemini CLI。
- `claude-code-cli-development`：在可见 Terminal + tmux 中驱动 Claude Code。
- `codex-cli-development`：在可见 Terminal + tmux 中驱动 Codex CLI。

## 安装

推荐把所需目录符号链接到 Codex Skills 目录，使本仓库保持唯一事实源：

```bash
ln -s "$(pwd)/skills/<skill-name>" "${CODEX_HOME:-$HOME/.codex}/skills/<skill-name>"
```

安装前先审计同名目标；不要覆盖未知内容。更新仓库后重新运行对应 Skill 的 `quick_validate.py`。

## 维护

每个 Skill 只保留 `SKILL.md`、`agents/openai.yaml` 与必要的 `scripts/`、`references/` 或 `assets/`。不在 Skill 目录添加 README、变更日志或过程总结。修改后检查脚本语法与无副作用路径，并复核凭证、绝对本机路径、缓存和生成产物未进入提交。

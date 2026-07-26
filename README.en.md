<div align="center">

# Akasha Grimoire

**Turn successful Agent collaboration into reusable team capabilities.**

[![Agent Skills](https://img.shields.io/badge/Agent_Skills-10-6C5CE7?style=flat-square)](#capability-catalog)
[![Languages](https://img.shields.io/badge/Languages-中文_·_English_·_日本語-2D9CDB?style=flat-square)](#)
[![Source of Truth](https://img.shields.io/badge/Source_of_Truth-Git-2EA44F?style=flat-square)](#design-principles)

[简体中文](README.md) · **English** · [日本語](README.ja.md)

</div>

---

Akasha Grimoire is a shared collection of Agent Skills. It packages task boundaries, verified tool contracts, deterministic scripts, low-noise waiting, and independent acceptance into installable capabilities—so Agents guess less, poll less, and complete real work with evidence.

## Design principles

- **Contract first:** define triggers, inputs, outputs, exclusions, and acceptance before execution.
- **Runtime facts win:** verify CLI versions, flags, endpoints, and limits against the current environment and reliable implementations.
- **Low-noise execution:** move mechanical polling into scripts and reserve model tokens for judgment and review.
- **Independent acceptance:** a worker's completion claim never replaces cumulative diff review, tests, artifact checks, or remote Git evidence.
- **One source of truth:** this repository owns the shared Skills; local installations should link back to it.

## Capability catalog

### Coordination and governance

| Skill | Best for | What it provides |
| --- | --- | --- |
| [`agent-task-supervisor`](skills/agent-task-supervisor/) | Supervising, coordinating, waiting for, and accepting multiple tasks | A compact task board; Codex App waits up to the current 120-second host limit, while external Agents use a 240-second silent script; drill-down only for blockers, drift, formal review, or P0–P2 risks |

### Image, game, and audio production

| Skill | Best for | What it provides |
| --- | --- | --- |
| [`game-asset-forge`](skills/game-asset-forge/) | Characters, scenes, UI, icons, tilesets, VFX, sprites, and animation frames | Asset contracts, smoke-before-batch, alpha/halo QA, character consistency, animation loops, 2×2 tile checks, engine import, and screenshot acceptance |
| [`gpt-image-generation`](skills/gpt-image-generation/) | GPT Image generation, reference-image editing, and endpoint diagnosis | OpenAI-compatible generations/edits, base URL normalization, safe result storage, protocol restrictions, and failure diagnosis |
| [`grok-media-generation`](skills/grok-media-generation/) | Grok image/video generation and editing | Call media endpoints through new-api, continue generated results with the current CPA `video.file_id` resolver, poll silently, and download real files safely |
| [`suno-music-generation`](skills/suno-music-generation/) | Creating music from a song description or custom lyrics | Submit asynchronous Suno jobs, check silently every five seconds, download every audio candidate plus covers and optional videos, then verify each result |
| [`fish-audio-speech`](skills/fish-audio-speech/) | Fish Audio voiceover, voice references, and transcription | new-api-backed TTS/STT with reference IDs, local reference audio, language and timestamp controls, and safe output handling |

### CLI development workers

All four CLI Skills follow the same loop: **the main Agent defines the contract → implementation runs in visible Terminal + tmux → lightweight status and delivery files → independent review by the main Agent → rework in the same session**. They do not collect worker reasoning or outsource product judgment to the CLI.

| Skill | Worker | Highlights |
| --- | --- | --- |
| [`grok-cli-development`](skills/grok-cli-development/) | Grok CLI | Development, image/video generation, Chinese planning, self-checks, and same-session rework |
| [`gemini-cli-development`](skills/gemini-cli-development/) | Gemini CLI | Development and delivery based on the locally verified CLI contract |
| [`claude-code-cli-development`](skills/claude-code-cli-development/) | Claude Code | Permission modes, session continuation, status delivery, and independent acceptance |
| [`codex-cli-development`](skills/codex-cli-development/) | Codex CLI | Implementation in a separate interactive TUI, kept distinct from Codex App task management |

## Quick installation

Clone the repository, then prefer symbolic links so the repository remains the single source of truth.

```bash
git clone git@github.com:lov-team/akasha-grimoire.git
cd akasha-grimoire
```

Install one Skill:

```bash
skill_name="suno-music-generation"
skills_home="${CODEX_HOME:-$HOME/.codex}/skills"
mkdir -p "$skills_home"
ln -s "$PWD/skills/$skill_name" "$skills_home/$skill_name"
```

Install all Skills while preserving existing targets:

```bash
skills_home="${CODEX_HOME:-$HOME/.codex}/skills"
mkdir -p "$skills_home"

for skill_dir in "$PWD"/skills/*; do
  skill_name="$(basename "$skill_dir")"
  target="$skills_home/$skill_name"
  if [ -e "$target" ] || [ -L "$target" ]; then
    echo "Keeping existing target: $target"
  else
    ln -s "$skill_dir" "$target"
  fi
done
```

Never force-overwrite an existing target. Audit differences first and preserve unknown content in a recoverable form.

## Example prompts

```text
Use $agent-task-supervisor to monitor these tasks lightly and independently accept their deliveries.

Use $game-asset-forge to create transparent character animation frames for a 2D game, starting with a smoke batch.

Use $grok-media-generation to generate or edit this image/video through new-api and verify the downloaded media file.

Use $suno-music-generation to create music from this song description and download every candidate.

Use $fish-audio-speech to synthesize this narration and verify the beginning, middle, and end.
```

## Credentials and runtime

| Capability | Configuration | Contract |
| --- | --- | --- |
| GPT Image | `IMAGE_PROXY_BASE_URL`, `IMAGE_PROXY_API_KEY`, or compatible OpenAI environment variables | Never place keys in command arguments, prompts, logs, or the repository |
| Grok media | `GROK_MEDIA_BASE_URL`, `GROK_MEDIA_API_KEY`, or compatible OpenAI environment variables | Real requests incur cost; start with one smoke task before scaling up |
| Suno / Fish Audio | `NEW_API_BASE_URL`, `NEW_API_API_KEY`, or compatible OpenAI environment variables | Real requests consume quota; base tests never call external generation services |
| CLI workers | The corresponding local CLI, macOS Terminal, and tmux | Re-check `--version` and `--help` on first use and after upgrades |

## Validation

Every Skill includes standard frontmatter and `agents/openai.yaml`. Run at least:

```bash
validator="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"
for skill_dir in skills/*; do
  python3 "$validator" "$skill_dir"
done

git diff --check
```

New scripts also require syntax checks and side-effect-free behavior tests. For image, music, speech, video, or external writes, start with a local fake service or a bounded smoke test. Always disclose capabilities that have not been verified end to end.

## Structure and maintenance

```text
skills/<skill-name>/
├── SKILL.md              # Trigger description and core working contract
├── agents/openai.yaml    # Agent UI metadata
├── scripts/              # Deterministic, repeatable execution logic (optional)
└── references/           # Tool facts and specialized contracts (optional)
```

- Keep `SKILL.md` concise and place complex facts one level down in `references/`.
- Do not add per-Skill READMEs, changelogs, caches, or process summaries.
- Re-verify real versions, help output, schemas, and reliable implementations whenever a CLI/API contract changes.
- Before release, review the cumulative diff and scan for TODOs, credentials, local absolute paths, caches, and generated artifacts.
- After push, verify the local SHA, remote SHA, and critical file contents.

---

<div align="center">

**Make Agent capability more than a single conversation: make it a verifiable, reusable, evolving work system.**

</div>

<div align="center">

# Akasha Grimoire

**Turn successful Agent collaboration into reusable team capabilities.**

[![Agent Skills](https://img.shields.io/badge/Agent_Skills-24-6C5CE7?style=flat-square)](#capability-catalog)
[![Best on Codex App](https://img.shields.io/badge/Best_on-Codex_App-111827?style=flat-square)](#graph-engineering)
[![Languages](https://img.shields.io/badge/Languages-中文_·_English_·_日本語-2D9CDB?style=flat-square)](#)
[![Source of Truth](https://img.shields.io/badge/Source_of_Truth-Git-2EA44F?style=flat-square)](#design-principles)
[![License: Apache 2.0 + Commercial](https://img.shields.io/badge/License-Apache_2.0_%2B_Commercial-F59E0B?style=flat-square)](LICENSE)

[简体中文](README.md) · **English** · [日本語](README.ja.md)

</div>

---

Akasha Grimoire is a shared collection of Agent Skills, designed to work best in **Codex App**. It packages task boundaries, verified tool contracts, deterministic scripts, low-noise waiting, and independent acceptance into installable capabilities—so Agents guess less, poll less, and complete real work with evidence. Individual Skills remain portable to compatible Agents and CLIs.

> **Want to generate images, video, speech, and music right away?** [Create a LovBrowser account](https://lovbrowser.com) and add credits. Akasha Grimoire defaults to `https://newapi.1234bot.com/v1`, so one new-api key can power GPT Image, Grok, Seedance, MiniMax H3, Kling, Fish Audio, and Suno without configuring a separate Base URL for every Skill.

## Get started in one minute

1. Ask Codex to run a media task with GPT Image, Grok, Seedance, MiniMax H3, Kling, Fish Audio, or Suno.
2. When no key exists, the Agent generates a LovBrowser device-authorization QR code plus a clickable link and short code.
3. Scan it, register or sign in, and confirm the matching code. The local client polls, stores the credential, and validates it through `/v1/models`.
4. After validation, the original media action continues once. The real key never passes through chat, clipboard, or command arguments.

You can also run `python3 shared/akasha_credentials.py status|start|finish|cancel|rollback`. Credentials default to `~/.config/akasha/credentials.env`. Existing environment variables remain compatible; priority is capability-specific variable > `NEW_API_API_KEY` > user credential > `OPENAI_API_KEY`.

## Design principles

- **Contract first:** define triggers, inputs, outputs, exclusions, and acceptance before execution.
- **Runtime facts win:** verify CLI versions, flags, endpoints, and limits against the current environment and reliable implementations.
- **Low-noise execution:** move mechanical polling into scripts and reserve model tokens for judgment and review.
- **Independent acceptance:** a worker's completion claim never replaces cumulative diff review, tests, artifact checks, or remote Git evidence.
- **One source of truth:** this repository owns the shared Skills; local installations should link back to it.

## Graph Engineering

Graph Engineering models delivery as a traceable work graph instead of a sequence of temporary prompts:

`Spec → Epic → Issue → Agent Task → Evidence`

| Layer | Responsibility |
| --- | --- |
| **Spec** | Defines the outcome, boundaries, non-goals, key decisions, and final acceptance as the root contract |
| **Epic** | Decomposes the Spec into a milestone subgraph with cross-Issue dependencies and roll-up acceptance |
| **Issue** | The smallest executable node, with an owner, scope, dependencies, outputs, and validation |
| **Agent Task** | A runtime instance of an Issue in Codex App or an external worker; it never replaces the Issue record |
| **Evidence** | Closes Issues with diffs, tests, artifacts, Review, and remote SHAs, then rolls completion up to Epics and Specs |

Every implementation and acceptance task is Issue-driven. Each task maps to an Issue; dependencies are explicit `depends_on`, `blocks`, `produces`, and `validates` edges; only ready nodes run in parallel. Direction changes update the Spec/Epic/Issue graph first, while Evidence rolls completion up from the leaves. Codex App is the preferred control plane because it exposes tasks, isolated worktrees, bounded long waits, and the acceptance loop.

## Capability catalog

### Coordination and governance

| Skill | Best for | What it provides |
| --- | --- | --- |
| [`agent-task-supervisor`](skills/agent-task-supervisor/) | Supervising, coordinating, and accepting tasks through a Spec/Epic/Issue graph | Issue-defined plans and acceptance matrices, difficulty-based Sol Codex implementation, and direct-parent monitoring |
| [`codex-app-development`](skills/codex-app-development/) | Having an independent Issue planning/acceptance task create a Codex App developer | Epic supervisor → Issue planning/acceptance → Sol developer with difficulty-based thinking, isolated worktrees, and independent diff review |

### Content production

| Skill | Best for | What it provides |
| --- | --- | --- |
| [`content-pipeline`](skills/content-pipeline/) | Turning Chinese ideas, articles, sources, or paused work into Xiaohongshu-style image-post packages | Content contracts, sourced research, source fidelity, copy, content maps, HTML/CSS cards, optional image generation, and mobile QA |

A standalone `content-pipeline` install covers text-only HTML/CSS cards. Install `gpt-image-generation` and `akasha-key-setup` as well when the workflow needs generated photos or illustrations.

### Video production

| Skill | Best for | What it provides |
| --- | --- | --- |
| [`video-production`](skills/video-production/) | Producing a complete video from an idea, article, script, or existing media | Stage-gated direction → sourcing/generation → EDL editing → technical and creative QA |
| [`h3-kling-video-generation`](skills/h3-kling-video-generation/) | Generating directed shots with H3 and Kling | Prompt orchestration, model-aware validation, async polling, and safe MP4 downloads for MiniMax H3 and Kling 3.0 / 2.5 |
| [`video-director`](skills/video-director/) | Writing, directing, storyboards, shot lists, and pre-generation planning | Narrative beats, coverage, cinematography, motion, continuity bible, and generation plan |
| [`video-source-research`](skills/video-source-research/) | Finding, downloading, and organizing B-roll, video, image, or audio assets | Per-shot queries, yt-dlp/direct downloads, ffprobe, SHA-256, and traceable `sources.json` |
| [`video-editing`](skills/video-editing/) | General rough/fine cuts, B-roll, audio, subtitles, and delivery | Reviewable `edl.json`, deterministic FFmpeg rendering, missing-audio handling, and output verification |
| [`video-qc`](skills/video-qc/) | Accepting generated clips, previews, and final exports | Full decode, black/freeze/silence/loudness/subtitle checks, representative frames, and narrative continuity review |
| [`article-to-short-video`](skills/article-to-short-video/) | Turning Chinese essays, profiles, or arguments into 60–120 second vertical videos | Evidence boundaries, Fish voiceover, Suno music, and vertical-video checks on top of the general production loop |
| [`multi-platform-video-publishing`](skills/multi-platform-video-publishing/) | Publishing animation, talking-head, or knowledge videos to Douyin, Xiaohongshu, Bilibili, and WeChat Channels in parallel | Parallel account checks/uploads, per-platform logs and ledgers, SHA confirmation, duplicate prevention, and remote status verification |

For complete production, install all seven general video skills. When no model is specified, `video-production` tries the first capable direct-video provider in this order: MiniMax H3 → Grok → Seedance 2.0. Kling, Gemini Omni, and other specialized capabilities are selected when the user requests them or a shot has incompatible hard requirements. Static visuals, narration, and music continue to route to GPT Image, Fish Audio, and Suno respectively. Web video downloads additionally require yt-dlp; deterministic editing and QA require FFmpeg/ffprobe; live distribution requires an already signed-in `mpau` runtime.

### Image, game, and audio production

| Skill | Best for | What it provides |
| --- | --- | --- |
| [`game-asset-forge`](skills/game-asset-forge/) | Characters, scenes, UI, icons, tilesets, VFX, sprites, and animation frames | Asset contracts, smoke-before-batch, alpha/halo QA, character consistency, animation loops, 2×2 tile checks, engine import, and screenshot acceptance |
| [`gpt-image-generation`](skills/gpt-image-generation/) | GPT Image generation, reference-image editing, and endpoint diagnosis | OpenAI-compatible generations/edits, base URL normalization, safe result storage, protocol restrictions, and failure diagnosis |
| [`grok-media-generation`](skills/grok-media-generation/) | Grok image/video generation and editing | Call OpenAI-compatible media endpoints, continue generated results with the current CPA `video.file_id` resolver, poll silently, and download real files safely |
| [`suno-music-generation`](skills/suno-music-generation/) | Creating music from a song description or custom lyrics | Submit asynchronous Suno jobs, check silently every five seconds, download every audio candidate plus covers and optional videos, then verify each result |
| [`fish-audio-speech`](skills/fish-audio-speech/) | Fish Audio voiceover, voice references, and transcription | OpenAI-compatible TTS/STT with reference IDs, local reference audio, language and timestamp controls, and safe output handling |

### App tasks and CLI development workers

Development uses a three-layer loop: **the Epic supervisor finds a ready Issue → an independent Issue App defines the implementation plan and acceptance matrix → a Codex worker running GPT-5.6 Sol with difficulty-based `thinking` implements → the Issue App independently reviews and sends P0–P2 back to the same worker → the Issue writes Evidence for the Epic to read**. All code development now defaults directly to an isolated Codex App task/worktree, without switching workers by frontend/backend category or task size. Pure media generation still uses the corresponding media skill. An explicit user choice may replace only the bottom worker. The Issue App never writes business code. After each one-way dispatch, the direct parent starts one monitor for up to 20 minutes, scanning status and handoff files every 20 seconds.

| Skill | Worker | Highlights |
| --- | --- | --- |
| [`gemini-cli-development`](skills/gemini-cli-development/) | Gemini CLI | Used when the user explicitly selects Gemini CLI |
| [`grok-cli-development`](skills/grok-cli-development/) | Grok CLI | Used when the user explicitly selects Grok CLI; built-in media work remains available separately |
| [`codex-app-development`](skills/codex-app-development/) | Codex App developer | Default for all code development; GPT-5.6 Sol with difficulty-based `thinking` |
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

Use $agent-task-supervisor to turn this Spec into an Epic/Issue dependency graph, start only ready Issues in Codex App, and close the graph bottom-up with evidence.

Use $codex-app-development from the Issue task to define the implementation plan and acceptance matrix, then create a separate Codex App worker running GPT-5.6 Sol with difficulty-based `thinking`; the developer only implements, while the Issue task independently reviews and returns P0–P2 to the same worker.

Use $content-pipeline to turn this Chinese article into a Xiaohongshu image post, preserve its argument, confirm the cover direction first, and deliver a recoverable local package.

Use $video-production to turn this product idea into a 30-second vertical video: finish the director package and shot list, source or generate media, produce an EDL, render, and run complete final QA.

Use $video-source-research to find B-roll for this shot list, download selected assets, and write sources.json with ffprobe metadata and SHA-256 hashes.

Use $game-asset-forge to create transparent character animation frames for a 2D game, starting with a smoke batch.

Use $grok-media-generation to generate or edit this image/video and verify the downloaded media file.

Use $suno-music-generation to create music from this song description and download every candidate.

Use $fish-audio-speech to synthesize this narration and verify the beginning, middle, and end.
```

## Credentials and runtime

| Capability | Configuration | Contract |
| --- | --- | --- |
| Default new-api | `https://newapi.1234bot.com/v1` | No Base URL setup required; use `NEW_API_BASE_URL` or `--base-url` only for a private deployment |
| GPT Image | `IMAGE_PROXY_API_KEY`, `NEW_API_API_KEY`, or `OPENAI_API_KEY` | Never place keys in command arguments, prompts, logs, or the repository |
| Grok / Seedance | A capability-specific key, `NEW_API_API_KEY`, or `OPENAI_API_KEY` | Real requests incur cost, so start with one smoke task before scaling up |
| Suno / Fish Audio | `NEW_API_API_KEY` or `OPENAI_API_KEY` | Real requests consume quota; base tests never call external generation services |
| Official proactive/quota recharge | Run `python3 shared/akasha_recharge.py` to create checkout; choose the amount on the LovBrowser page | Proactive recharge does not require a quota failure; Agent offers only the clickable `publicPageUrl`, without a QR code; never leak keys/tickets |
| Three-layer Codex App tasks | Epic supervisor, Issue planning/acceptance task, and Sol developer task/worktree with difficulty-based thinking | Dispatch flows Epic→Issue→developer; Issue plans before delegation and independently reviews the full diff |
| CLI workers | The corresponding local CLI, macOS Terminal, and tmux | Re-check `--version` and `--help` on first use and after upgrades |
| Video editing and sourcing | FFmpeg/ffprobe; yt-dlp for web downloads | On macOS use `brew install ffmpeg yt-dlp`; every download still requires media probing, provenance, and hashing |

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
├── references/           # Tool facts and specialized contracts (optional)
└── assets/               # Templates and resources copied into deliverables (optional)
```

- Keep `SKILL.md` concise and place complex facts one level down in `references/`.
- Do not add per-Skill READMEs, changelogs, caches, or process summaries.
- Re-verify real versions, help output, schemas, and reliable implementations whenever a CLI/API contract changes.
- Before release, review the cumulative diff and scan for TODOs, credentials, local absolute paths, caches, and generated artifacts.
- After push, verify the local SHA, remote SHA, and critical file contents.

## License

The current release uses the [Apache License 2.0 with Additional Commercial Conditions](LICENSE). Uses other than Commercial Payment Use follow the Apache 2.0 terms. Commercial Payment Use is free up to USD 1,000,000 in cumulative payment volume and requires a written commercial license before exceeding that threshold. This combined license is not the unmodified Apache License 2.0. See [Licensing](LICENSING.md) for details.

Releases previously distributed under GPLv3 remain under their original license.

---

<div align="center">

**Make Agent capability more than a single conversation: make it a verifiable, reusable, evolving work system.**

</div>

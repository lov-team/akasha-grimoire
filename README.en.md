<div align="center">

# Akasha Grimoire

**Turn successful Agent collaboration into reusable team capabilities.**

[![Agent Skills](https://img.shields.io/badge/Agent_Skills-10-6C5CE7?style=flat-square)](#capability-catalog)
[![Best on Codex App](https://img.shields.io/badge/Best_on-Codex_App-111827?style=flat-square)](#graph-engineering)
[![Languages](https://img.shields.io/badge/Languages-中文_·_English_·_日本語-2D9CDB?style=flat-square)](#)
[![Source of Truth](https://img.shields.io/badge/Source_of_Truth-Git-2EA44F?style=flat-square)](#design-principles)
[![License: GPL v3](https://img.shields.io/badge/License-GPL_v3-blue?style=flat-square)](LICENSE)

[简体中文](README.md) · **English** · [日本語](README.ja.md)

</div>

---

Akasha Grimoire is a shared collection of Agent Skills, designed to work best in **Codex App**. It packages task boundaries, verified tool contracts, deterministic scripts, low-noise waiting, and independent acceptance into installable capabilities—so Agents guess less, poll less, and complete real work with evidence. Individual Skills remain portable to compatible Agents and CLIs.

> **Want to generate images, video, speech, and music right away?** [Create a LovBrowser account](https://lovbrowser.com) and add credits. Akasha Grimoire defaults to `https://newapi.1234bot.com/v1`, so one new-api key can power GPT Image, Grok, Seedance, Fish Audio, and Suno without configuring a separate Base URL for every Skill.

## Get started in one minute

1. Open [lovbrowser.com](https://lovbrowser.com), then register or sign in.
2. Choose a plan or top up your balance and complete payment as instructed on the site.
3. Open API Key management, create a new-api key, and copy it.
4. Store the key through an environment variable or credential manager:

   ```bash
   export NEW_API_API_KEY="<your-new-api-key>"
   ```

5. Ask Codex to generate an image with GPT Image, a video with Grok or Seedance, speech with Fish Audio, or music with Suno. The matching Skill uses the default endpoint automatically.

Never put the key in prompts, command arguments, logs, or the repository. Set `NEW_API_BASE_URL` or pass `--base-url` only for a private deployment.

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
| [`agent-task-supervisor`](skills/agent-task-supervisor/) | Supervising, coordinating, and accepting tasks through a Spec/Epic/Issue graph | Graph nodes, relationship edges, and a compact task board; Codex App waits up to the current 120-second host limit, external Agents use a 240-second silent script, and drill-down occurs only for blockers, drift, formal review, or P0–P2 risks |

### Image, game, and audio production

| Skill | Best for | What it provides |
| --- | --- | --- |
| [`game-asset-forge`](skills/game-asset-forge/) | Characters, scenes, UI, icons, tilesets, VFX, sprites, and animation frames | Asset contracts, smoke-before-batch, alpha/halo QA, character consistency, animation loops, 2×2 tile checks, engine import, and screenshot acceptance |
| [`gpt-image-generation`](skills/gpt-image-generation/) | GPT Image generation, reference-image editing, and endpoint diagnosis | OpenAI-compatible generations/edits, base URL normalization, safe result storage, protocol restrictions, and failure diagnosis |
| [`grok-media-generation`](skills/grok-media-generation/) | Grok image/video generation and editing | Call OpenAI-compatible media endpoints, continue generated results with the current CPA `video.file_id` resolver, poll silently, and download real files safely |
| [`article-to-short-video`](skills/article-to-short-video/) | Turning Chinese essays, profiles, or arguments into 60–120 second vertical videos | Evidence boundaries, Fish reference voices, Suno music, voice-derived timing, FFmpeg composition, and loudness/black-frame/subtitle acceptance |
| [`suno-music-generation`](skills/suno-music-generation/) | Creating music from a song description or custom lyrics | Submit asynchronous Suno jobs, check silently every five seconds, download every audio candidate plus covers and optional videos, then verify each result |
| [`fish-audio-speech`](skills/fish-audio-speech/) | Fish Audio voiceover, voice references, and transcription | OpenAI-compatible TTS/STT with reference IDs, local reference audio, language and timestamp controls, and safe output handling |

### CLI development workers

All four CLI Skills follow the same loop: **the main Agent defines the contract → implementation runs in visible Terminal + tmux → lightweight status and delivery files → independent review by the main Agent → rework in the same session**. They do not collect worker reasoning or outsource product judgment to the CLI.

| Skill | Worker | Highlights |
| --- | --- | --- |
| [`grok-cli-development`](skills/grok-cli-development/) | Grok CLI | Development, image/video generation, Chinese planning, self-checks, and same-session rework |
| [`gemini-cli-development`](skills/gemini-cli-development/) | Gemini CLI | Development and delivery based on the locally verified CLI contract |
| [`claude-code-cli-development`](skills/claude-code-cli-development/) | Claude Code | Permission modes, session continuation, status delivery, and independent acceptance |
| [`codex-cli-development`](skills/codex-cli-development/) | Codex CLI | Implementation in a separate interactive TUI, kept distinct from Codex App task management |

## Real example: Amazon slipper product media

This end-to-end example created a visual package for a fictional pair of mist-blue ergonomic EVA slides. The Agent locked the color, strap grooves, and rocker sole; generated an Amazon-style white-background hero image, a bathroom lifestyle image, and a material-detail image; then generated separate five-second product videos with Grok and Seedance and verified their decoding, metadata, and representative frames.

![Amazon slipper hero image](docs/assets/amazon-slippers-main.jpg)

| Deliverable | Capability | Verified result |
| --- | --- | --- |
| Hero, lifestyle, and detail images | `gpt-image-generation` / `gpt-image-2` | 1536 px product images; all hero-image corners are pure white |
| Studio product video | `grok-media-generation` / `grok-imagine-video` | 5.04 seconds, 848 × 480, 24 fps |
| Rotating product video | `seedance-video-generation` / `doubao-seedance-2-0-260128` | 5.04 seconds, 1280 × 720, 24 fps |

![Grok frames above and Seedance frames below](docs/assets/amazon-slippers-video-comparison.jpg)

The example also shows the production boundary: text-to-video is fast for direction finding, but product color, grooves, and outsole geometry may drift. For a real listing, use approved product photography as image-to-video references and substantiate claims such as slip resistance, water resistance, or cushioning with real evidence.

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

## License

This project is open source under the [GNU General Public License v3.0](LICENSE).

---

<div align="center">

**Make Agent capability more than a single conversation: make it a verifiable, reusable, evolving work system.**

</div>

# Upstream snapshot

- Source: https://github.com/Vincentwei1021/video-shotcraft.git
- Commit: `41ee360d82f4c491ba9d88a24a4add7d8ff1cf8b`
- License: Apache-2.0; see `LICENSE`.
- Included: all 153 shot Markdown files (152 Library cards plus the attribution document), 202 TSX demos plus fixtures/neutral textures, Library index, shared components, the 13-file `template/src/aifl/` source subset referenced by 9 cards, six workflow/review references, sequence recipes, and a URL/SHA-256 manifest for 24 SFX. `final-review.md` has an Akasha path/non-product preamble; its upstream checklist body is preserved.
- Adapted: `ai-stream-response` keeps its exact upstream TSX as `.txt`, while the runnable TSX replaces the excluded Linear background image with a neutral SVG.
- Excluded: Gallery application, generated preview media, complete template project, brand assets, SFX binaries, and BGM.

Upgrade only through an explicit task following `references/upstream-integration.md`.

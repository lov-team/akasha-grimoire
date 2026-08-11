# video-shotcraft 上游集成

## 固定版本

- Repository: https://github.com/Vincentwei1021/video-shotcraft.git
- Commit: `41ee360d82f4c491ba9d88a24a4add7d8ff1cf8b`
- License: Apache-2.0

本 Skill 使用仓库内快照，生产时不从上游 `main` 拉取文件。

## 路径映射

| 上游 | 本 Skill |
|---|---|
| `references/shots/` | `references/video-shotcraft/shots/` |
| `references/{pipeline,guided-free-creation,sound-design,aesthetic-rules,music-beat-sync,final-review}.md` | `references/video-shotcraft/` |
| `references/sequences/` | `references/video-shotcraft/sequences/` |
| `gallery/api/library.json` | `assets/video-shotcraft/library.json` |
| `demos/` | `assets/video-shotcraft/demos/` |
| 9 张卡引用的 `template/src/aifl/` | `assets/video-shotcraft/template-source/aifl/` |
| `assets/lib/` | `assets/video-shotcraft/lib/` |
| 精选 `assets/audio/sfx/` 的来源与 SHA-256 | `assets/video-shotcraft/audio/sfx/SFX_MANIFEST.json` |

Gallery 页面、在线样片、完整 `template/` 工程、品牌资产、SFX 二进制和 BGM 排除在快照之外。模板引用卡只保留 Apache-2.0 源码子集。`ai-stream-response` 的原始 Linear 背景图已排除；原始 TSX 以文本留档，默认 Demo 改用中性 SVG 背景。

## 显式升级

升级任务必须：选择新 commit；比较卡片、索引、Demo、组件、音频与许可证；更新快照和 `UPSTREAM.md`；重新核对卡片数与 Demo 数；运行单测、Skill validator 和真实 Remotion smoke；在 PR 中记录差异。普通视频生产任务保持当前固定版本。

# 本地内容包合同

## 位置与命名

输出根目录优先级：当前项目既有约定 > 用户指定路径 > `content-packages/`。默认目录名为 `YYYY-MM-DD-<slug>/`；批量任务一篇一目录。

首次创建时，从本 Skill 的 `assets/post-package/` 复制完整模板。先解析当前 `SKILL.md` 所在目录，不假设执行目录就是 Skill 目录。继续任务时先读 `manifest.md`，保留已成功文件，并从 `Next action` 恢复。

```text
content-packages/YYYY-MM-DD-<slug>/
├── brief.md
├── manifest.md
├── sources/
├── research.md
├── copy.md
├── content-map.md
├── cards/
│   ├── plan.md
│   ├── html/
│   └── output/
├── generation-log.md
└── qa.md
```

## 状态

`manifest.md` 只使用：`planning`、`researching`、`writing`、`designing`、`reviewing`、`ready`、`partial`、`blocked`。

- `partial`：已有可交付结果，但数量、阶段或 QA 未完整。
- `blocked`：缺少关键输入、凭证、模型能力或用户决定，当前阶段停止。
- `ready`：必需文件齐全、内容合同一致、每张最终图片已实际查看，且本地路径可读取。

## 文件职责

- `brief.md`：冻结受众、目标、观点、语气、边界、内容类型和交付结构。
- `sources/`：来源摘录、链接、素材说明；私人来源不因模板存在而自动复制。
- `research.md`：事实、引用、观点、推断和来源映射。
- `copy.md`：标题候选、最终标题、正文、可选标签和 CTA。
- `content-map.md`：原始素材到核心点、卡片和配文的映射。
- `cards/plan.md`：封面 Hook、逐页核心信息、证据和版式。
- `cards/html/`：HTML/CSS 路线的可复现源文件。
- `cards/output/`：最终图片及 `preview-grid.png`、`preview-mobile.png`。
- `generation-log.md`：渲染器、模型调用、输入输出文件和验收时间。
- `qa.md`：来源、文案、合同、视觉和文件完整性检查。

## 文件与隐私

- 最终图片使用 `xhs-01-cover.png`、`xhs-02-<slug>.png` 等零填充名称。
- 临时候选、接口响应、base64、缓存和淘汰稿放在包外暂存区，不混入正式交付。
- 原始输入记录在 `sources/original.md`；记录输入指纹和采用文件，不把敏感正文或本机私有路径写入 manifest。
- 密钥、Token、Cookie、未经允许复制的私人来源和未获许可素材不进入内容包、日志或回复。
- Git 跟踪、Issue 和 PR 由当前项目规则决定；它们不是本 Skill 默认 `ready` 门禁。

### 原始输入与隐私

- 公开来源：记录 URL、访问时间、输入指纹和必要摘录。
- 用户自有且明确允许随包保存的稿件：可将全文写入 `sources/original.md`，并记录授权范围。
- 私人或敏感稿件：`sources/original.md` 只记录输入指纹、脱敏摘要和“恢复时重新提供”，不记录本机绝对路径；正文保留在用户控制的位置。
- 未明确时采用“只记录指纹，恢复时重新提供”，不默认复制全文。

批量生产结束后，从 `assets/batch-qa.md` 在批次根目录创建 `batch-qa.md`，至少检查跨帖标题、Hook、模板和观点是否机械重复；单篇失败不抹掉其他成功结果。

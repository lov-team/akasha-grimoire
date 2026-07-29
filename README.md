# Akasha Grimoire（阿卡夏秘典）

团队共享的 Agent Skill 合集。仓库是通用 Skill 的唯一事实源。

> **想直接体验图片和视频生成？** 前往 [LovBrowser](https://lovbrowser.com) 注册账号并开通额度。阿卡夏秘典默认连接 `https://newapi.1234bot.com/v1`，通常只需要一把 `NEW_API_API_KEY`，无需逐个配置 Base URL。

## 一分钟开通

1. 打开 [lovbrowser.com](https://lovbrowser.com)，注册并登录。
2. 选择套餐或充值额度，按页面提示完成付费。
3. 在 API Key 管理页面创建并复制 new-api Key。
4. 通过环境变量或凭证管理器安全配置：

   ```bash
   export NEW_API_API_KEY="<your-new-api-key>"
   ```

5. 在 Codex 中直接点名相应 Skill。脚本会自动使用默认 new-api 入口。

不要把 Key 写进 prompt、命令参数、日志或仓库。只有连接私有部署时才设置 `NEW_API_BASE_URL` 或传入 `--base-url`。

## Skills

- `agent-task-supervisor`：轻量监工多个任务并独立验收。
- `game-asset-forge`：生成并验收可直接导入引擎的游戏资产。
- `gpt-image-generation`：通过 OpenAI-compatible GPT Image 端点生图、改图和诊断。
- `grok-media-generation`：通过 new-api 生成和编辑 Grok 图片与视频。
- `seedance-video-generation`：通过 new-api 生成 Seedance 文生视频与参考素材视频。
- `grok-cli-development`：在可见 Terminal + tmux 中驱动 Grok CLI。
- `gemini-cli-development`：在可见 Terminal + tmux 中驱动 Gemini CLI。
- `claude-code-cli-development`：在可见 Terminal + tmux 中驱动 Claude Code。
- `codex-cli-development`：在可见 Terminal + tmux 中驱动 Codex CLI。

## 实战案例：亚马逊拖鞋商品视觉

下面是一套真实调用完成的跨境电商样例：先用 GPT Image 生成雾蓝色 EVA 拖鞋的白底主图、浴室上脚图和材质细节图，再分别调用 Grok 与 Seedance 生成 5 秒商品视频，并检查文件签名、时长、分辨率和代表帧。

![亚马逊拖鞋白底主图](docs/assets/amazon-slippers-main.jpg)

| 交付物 | 模型 | 验证结果 |
| --- | --- | --- |
| 白底主图、场景图、细节图 | `gpt-image-2` | 1536 px 商品图；主图四角纯白 |
| 商品棚拍视频 | `grok-imagine-video` | 5.04 秒，848 × 480，24 fps |
| 商品旋转视频 | `doubao-seedance-2-0-260128` | 5.04 秒，1280 × 720，24 fps |

![Grok 与 Seedance 视频抽帧对比：上方为 Grok，下方为 Seedance](docs/assets/amazon-slippers-video-comparison.jpg)

纯文生视频适合快速验证创意方向，但商品颜色、鞋面凹槽和鞋底结构仍可能漂移。正式上架应使用真实样品图进行图生视频，并为“防滑”“防水”“缓震”等卖点准备真实证据。

## 安装

推荐把所需目录符号链接到 Codex Skills 目录，使本仓库保持唯一事实源：

```bash
ln -s "$(pwd)/skills/<skill-name>" "${CODEX_HOME:-$HOME/.codex}/skills/<skill-name>"
```

安装前先审计同名目标；不要覆盖未知内容。更新仓库后重新运行对应 Skill 的 `quick_validate.py`。

## 维护

每个 Skill 只保留 `SKILL.md`、`agents/openai.yaml` 与必要的 `scripts/`、`references/` 或 `assets/`。不在 Skill 目录添加 README、变更日志或过程总结。修改后检查脚本语法与无副作用路径，并复核凭证、绝对本机路径、缓存和生成产物未进入提交。

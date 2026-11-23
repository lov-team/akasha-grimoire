---
name: minimax-h3-op-remix
description: 使用本地 ComfyUI + MiniMax H3 Reference-to-Video（Ref2VA）完成番剧/动画 OP·MV 全片角色与文字替换（「OP改」/二创换人）的端到端生产与质检规范。用户要求做动画 OP 改、MV 角色替换、用 MiniMax H3 Ref2VA 批量替换番剧人物、编写 H3 六段式视频编辑提示词、处理多人同框级联替换或导出视频号竖屏上下对比成片时使用。
---

# MiniMax H3 动画 OP 角色替换（「OP改」）生产规范

本 Skill 总结自 90 秒（2,161 帧）番剧 OP 全员 AI 娘化重制的完整实测闭环（本地双 24 GB 显卡 + 128 GB 内存 + ComfyUI + `MiniMaxH3ReferenceToVideo`）。必须严格执行每一个关卡——跳过任一环节都会引发切镜穿帮、后排漏换、水印残影或画风劣化。

配套资源与协同 Skill：
- 阶段 0 源视频 24fps 归一化、切点真实帧拼图与设定卡去字补白脚本：[`scripts/prep_op_project.py`](scripts/prep_op_project.py)
- 单镜 / 双轮级联渲染与 4 帧对比图质检脚本：[`scripts/run_ref2va_shot.py`](scripts/run_ref2va_shot.py)
- 阶段 4 全片拼接、OpenCV MAD 未替换穿帮帧自动扫描与视频号 `9:16` 竖屏导出脚本：[`scripts/assemble_audit_export.py`](scripts/assemble_audit_export.py)
- ComfyUI `MiniMaxH3ReferenceToVideo` API 工作流模板：[`assets/h3_ref2va_comfy_workflow.json`](assets/h3_ref2va_comfy_workflow.json)
- **底层引擎与上下游协同**：
  - 本地双卡运行时、5% 极端趴姿死角首帧 I2V（`h3_i2v_first_frame.json`）、泳装设定卡预生成（`moss-sheet`）及 1080p/2K 终版高清超分（`regen2k`）统一调用 [`comfyui-minimax-h3`](../comfyui-minimax-h3/)；
  - 无本地 24GB 显卡时，本 Skill 的分镜拆解、Cast 映射、6 段式提示词与双轮级联策略可直接路由至云端 [`h3-kling-video-generation`](../h3-kling-video-generation/)；
  - 成片验收后可交由 [`multi-platform-video-publishing`](../multi-platform-video-publishing/) 一键四平台分发。

---

## 1. 本地硬件、ComfyUI 启动契约与双实例锁页内存上限

1. **ComfyUI 必选启动参数（24 GB 显存 + 128 GB 内存，Windows）**：
   - 启动前必须设置 `PYTHONUTF8=1` 与 `PYTHONIOENCODING=utf-8`（防止 Windows GBK 控制台在 `logging.error` 中抛出 `UnicodeEncodeError` 导致队列永久挂死）。
   - 推荐单实例命令（绑定满速 PCIe 4.0 x16 主卡 GPU 0）：
     ```powershell
     $env:PYTHONUTF8="1"; $env:PYTHONIOENCODING="utf-8"
     python main.py --listen 0.0.0.0 --port 8188 --lowvram --reserve-vram 4 --cache-ram 8 48 --cuda-device 0
     ```
   - **为什么必须加 `--reserve-vram 4`**：`qwen3vl_32b_minimax_h3_int8_convrot`（约 22.8 GiB）叠加 2–4 张参考图与视频视觉 Token 时，若不预留 4 GB 显存余量，会在 `llama.py` MLP 层直接 OOM。
   - PyTorch `2.9.1+cu130` 环境下若未重编译对应版本的 `sageattention._fused`，**切勿传 `--use-sage-attention`**，直接使用原生 PyTorch SDPA。
   - 多镜头连续跑批时，每镜间隔检查 `nvidia-smi` 温度，任一 GPU 超过 `79°C` 时暂停冷却。

2. **Windows WDDM 64 GB 锁页内存墙（为什么 128 GB 内存不能双开满血 `H3 Ref2VA`）**：
   - Windows WDDM 对全系统 CUDA 锁页内存（Page-Locked / Pinned Memory）有 **50% 物理内存硬上限（128 GB 机器上全系统共 64 GB）**，而 ComfyUI 默认按 `MAX_PINNED_MEMORY = ram * 0.40`（单进程 `52.3 GB`）申请。
   - 单路满血 `MiniMaxH3ReferenceToVideo`（`qwen3vl_32b` 全量加载 + `minimax_h3` DynamicVRAM）在文本编码器切向 DiT 阶段峰值占用约 `36–40 GB` 锁页内存。若在 128 GB Windows 上**同时并发跑两路 `H3 Ref2VA`**（合计 `~80 GB > 64 GB`），副实例必触发 `[WARNING] Pin error` 并在 `comfy_aimdo` 抛出 `RuntimeError: hostbuf_file_reader_read failed`。
   - **准则**：重度 `H3 Ref2VA` 跑批固定单跑 **GPU 0（PCIe 4.0 x16，56 帧约 5.5 分钟/镜）**；双实例（`:8188` + `:8189`）仅用于「一重一轻」异构并发（或 `>= 192 GB` 内存主机），且隔离实例内 `SelectCLIPDevice`/`SelectVAEDevice` 必须设为 `"default"`。

3. **角色设定卡预处理规范**：
   - **1–2 人镜头**：优先使用纯白底（`#FFFFFF`）**正/侧/背三视图设定卡**，宽度统一缩放到 `960px`（如 `960×540`），既降低约 64% 的 Qwen3-VL 视觉 Token 显存，又能保证侧颜（如宇宙地球俯卧侧影）、转身与背影高度一致。
   - **3–4 人同框镜头**：使用纯白底紧凑全身正面立绘（`448×672`），高帽、兽耳、呆毛顶部必须额外留足白边，防止生成画面削顶。
   - **严禁带文字标签**：送入 `MiniMaxH3ReferenceToVideo` 前必须裁掉设定图上的角色名、色卡、边框与分辨率小字，否则 H3 会把文字幻觉印进动画背景。

---

## 2. 阶段一：全局角色映射表（Cast Bible）与帧级精准切镜（零盲切、零穿帮）

0. **开工前先锁定全局角色映射合同（`cast_bible.json`）**：
   - 长篇 OP 含 40–60 个镜头，动笔写任何 Prompt 前必须建立固定的「原片角色 → 目标角色设定卡」一一映射表（例如固定 `Gudako → DeepSeek`、`Mash → Claude`、`Artoria → GPT`、`Jalter → GLM`、`Osakabehime → Qwen`），严禁同一原片角色在前后镜头随机变成不同目标角色。
   - 先用 `scripts/prep_op_project.py prep-refs --top-pad-px 120` 批量去除三视图标题边框并在高帽/兽耳上方补足纯白边距，生成 `*_3view.png`（`960px` 宽）与 `*_sm.png`（`448×736`）。

1. **先做唯一基准源视频**：
   - 先导出帧率恒定的 `source_24fps.mp4`（`fps=24,setsar=1`），所有分镜严格用整数帧区间 **`[start_frame, end_frame)`** 记录，严禁用浮点秒数切镜。

2. **写提示词前必须肉眼核验带真实帧号的抽帧图**：
   - FFmpeg `-vf` 链中，`drawtext=text='F=%{n}'` **必须写在 `select=...` 之前**（写在 `select` 之后会把 `%{n}` 重置为 `0, 1, 2...`，导致严重错位！），逐镜目检 `[start, mid, end]` 及切点前后 4 帧（如末尾 4 帧突然跳入吉祥物猫或转场字幕）。

3. **三条铁律（源自全片穿帮复盘）**：
   - **铁律 A — 严禁合并连续超短闪切分镜（如 `3帧 + 3帧`）**：
     遇到连续两个 3 帧漫画闪切（如 `[1452, 1455)` `祭?` 与 `[1455, 1458)` `祭だ`），**绝对不能合并成一个 6 帧 `pad` 片段**！`tpad=stop_mode=clone` 只会把后一个分镜定格延长 50 帧，前一个 3 帧分镜占比过小会被 H3 原样复制漏换。必须拆成**两个独立的 `[s, e)` `pad` 任务**（各自 `3f -> 56f -> 裁回前 3f`）。
   - **铁律 B — 前景吉祥物擦除转场若身后露人，严禁透传 `orig`**：
     当猫群/烟雾等前景元素走过并在末尾几帧露出后方人群时，若将该过渡段标为 `orig` 直通，会在猫缝间露出原片角色，甚至在切镜前留下 1–2 帧完全未替换的原片帧。**必须把前景擦除段与后方群像合并为一个连续 `H3 Ref2VA` 镜头一步重绘**。
   - **铁律 C — 纯白闪屏帧不用原片直通**：
     带右上角水印/滚动字幕的片源中，2 帧白闪切镜直接用纯净 `#FFFFFF` 白帧替代，避免白屏上闪出原片水印。

4. **H3 帧数网格映射（`17k + 5`：56, 73, 90...）与还原**：
   - **常规镜头（`24–95` 帧）**：`setpts` 均匀拉伸到最近的 `17k+5` 网格（`mode="stretch"`），生成后按 `floor(i*(g-1)/(n-1)+0.5)` 均匀抽回精确帧数。
   - **短切镜头（`3–23` 帧）**：`tpad=stop_mode=clone` 定格尾帧补齐到 `56` 帧（`mode="pad"`），提示词写明前 `N` 帧动作后保持稳定，生成后裁剪前 `N` 帧。
   - **长慢镜/宇宙推轨镜头（`96–135` 帧，如 `127` 帧地球大镜头）**：在 24 GB 显存上不要向上对齐到 `141` 帧；先用 `setpts` 平滑压缩到安全的 **`90` 帧（`5*17+5`）** 生成，再用 `setpts=(PTS-STARTPTS)*((orig_n-1)/(gen_n-1)),fps=24`（配合 `-frames:v orig_n`）平滑还原为精确 `127` 帧。**切勿在 `gen_n < orig_n` 时使用 Python `{set}` 去重抽帧**（会导致输出帧数被截断为 `90` 帧！）。

---

## 3. 阶段二：镜头路由策略（为什么坚持纯 H3 Ref2VA）

> **核心经验教训：严禁用图像编辑模型（如 `moss_image_edit`）或 OpenCV 修补直接重绘动画视频帧！**
> 实测用图像编辑模型直接改动画帧会把干净的赛璐璐 TV 动画线条劣化成塑料厚涂感、裁切边缘文字，并在原水印位置幻觉出乱码字母。**坚持使用 `MiniMaxH3ReferenceToVideo` + 官方三视图/立绘设定卡**，无论是单色漫画分镜还是宇宙巨像侧影，都能保持纯正番剧画风与光影动态。图像编辑模型**仅限**在服装严重冲突（如泳装回 vs 礼服设定卡）时预先生成纯白底新服装参考卡。

| 镜头类型 | 典型场景 | 实测最优路由 |
|---|---|---|
| **A. 1–4 人常规 / 漫画闪切 / 巨像镜头** | 单人指镜头、3 帧冰蓝漫画 `祭?`、地球宇宙巨女侧影 | **单轮 H3 Ref2VA**：传 1–2 张 `960px` 三视图或最多 4 张 `448×672` 紧凑立绘 |
| **B. 5–10+ 人密集同框特写 / 群像** | 6 人贴脸欢呼、10 人全员同框大特写 | **双轮（2-Pass）H3 Ref2VA 级联替换**：<br>• **Pass 1**：基于原片替换前排最显眼的 4 人；<br>• **Pass 2**：以 `final_pass1.mp4` 作为 `<Video 1>`，传入另外 1–4 张新角色卡，在提示词中明确标注前排已替换角色 `KEEP UNCHANGED`，集中算力把侧边/后排剩余原片角色全部替换干净！ |
| **C. 特殊服装冲突镜头**（泳装/睡衣 vs 礼服卡） | 海滩比基尼群像 | **Step 1**：先生成头顶留白充足的纯白底泳装立绘卡；<br>**Step 2**：将泳装立绘卡送入 **H3 Ref2VA** |
| **D. 纯图形 / 无人物过场** | 厂牌几何 Logo、纯机械激光炮、纯猫猫出拳 | 无水印时直接透传 `orig`，有大字标题时用 H3 做同字体替换 |

---

## 4. 阶段三：手写 6 段式 Context-IR 提示词（严禁模板拼接）

本地 ComfyUI 没有云端 Prompt 改写器，模板拼接字符串极易退化为原片复制粘贴或白底立绘硬贴。每个镜头必须在核验真实抽帧后手写以下 **6 段式结构**：

1. **`subject_definitions:`**
   - 具体描述 `<Video 1>` 的景别、背景、光影变化、前景吉祥物及每个原片人物的方位与特征。
   - **二轮级联（Pass 2）镜头**：逐一列出已替换好的 AI 角色并注明 `KEEP UNCHANGED`，再对剩余未替换原片角色注明 `REPLACE THIS GIRL COMPLETELY`。
   - 为每个 `<Subject k>` 写明空间方位（`LEFT` / `CENTER` / `RIGHT`）与 **新旧外观强对比句**，显式点名要消除的原片特征（如 `NO glasses`、`NO oni horns`、`NO mummy bandages`、`NO grey knight armor`）。
   - 末尾固定声明：`Reference pictures are identity and costume references ONLY, never standing pose or white-background references.`
2. **`summary:`**
   - 固定以 `[video editing + reference generation] The target video is an edited version of <Video 1>.` 开头，1–2 句话概括全部角色替换、保留动作光影以及去水印指令。
3. **`text_replacements:`**
   - 漫画气泡与搞笑木牌（`祭?`、`祭だ`、`馬のえさ`、`金`、`権力`）：点名精确日文字符串与位置要求 **完整保留**。
   - 标题卡与白板字（如 `緊急ジャンヌ会議` → `緊急AI会議`）：写明原文字、目标文字与笔触风格。
   - 电视台/BD 宣发角标与底部滚动字幕：明确要求在**所有帧（特别是末尾跳猫帧与白色木牌右上角）彻底清除**。
4. **`retention_analysis:`**
   - 明确各 `<Subject k>` 发色配饰互不串色、前景吉祥物保留、暗场/逆光环境光影保留（防止暗色宇宙镜头漏出白底棚拍光）。
5. **`detailed_description:`**
   - 以 `[Shot 1]` 按时间顺序写出从第 0 帧到尾帧的动作与光影推进（例如前 2/3 深空暗蓝轮廓光 → 后 1/3 地球日出粉金逆光渐亮；短镜头注明 `pad` 定格说明）。
6. **`overall_soundscape:` & `non_diegetic_music:`**
   - 固定写 `None.` 与 `N/A`（成片阶段逐帧回封原片母带音轨）。

---

## 5. 阶段四：逐镜 4 帧对比质检、全片穿帮扫描与视频号竖屏导出

1. **逐镜 4 帧对比图强制门禁**：
   - 每渲染完 1–3 个镜头，自动导出上原片（`ORIG`）、下生成片（`GEN`）的 4 帧对比条（取 `0%, 33%, 66%, 95%`，3 帧短切取 `0, 1, 2`）并目检。
   - 只要出现漏换人物（含后排或猫后）、眼镜/鬼角/绷带残留、头顶裁切、文字乱码或末尾帧水印复现，立即用单句微调或 Pass-2 级联返修。

2. **成片拼接前全时间线零缝隙与穿帮复核**：
   - 校验 `[0 .. total_frames)` 帧区间连续无缺帧、无重叠，并用 `ffprobe` 校验成片总帧数。
   - 抽检所有切点 `[cut-2, cut-1, cut, cut+1]` 与全片帧差（MAD），确保零原片残帧漏网。

3. **微信视频号（`9:16`）上下对比版导出规范**：
   - 除横屏成片与左右 SBS 外，发微信视频号优先导出 **`1080×1920`（`9:16`，H.264 + `-movflags +faststart`）上下对比竖屏版**：
     - 以生成片放大模糊压暗（`gblur=sigma=24,eq=brightness=-0.38`）作为 `1080×1920` 动态柔焦底图；
     - 将上原片（`1080×608`）+ `4px` 分隔线 + 下重制版（`1080×608`）整体**上移排布在 `y = 236..1456` 黄金可视区**；
     - 底部预留 **`464px`（`y = 1456..1920`）安全区**，完美避开视频号底部的账号名、描述文案、进度条及点赞转发按钮遮挡！

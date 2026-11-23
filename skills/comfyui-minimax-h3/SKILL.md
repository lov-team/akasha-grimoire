---
name: comfyui-minimax-h3
description: 本地 ComfyUI + MiniMax H3 视频生成/参考编辑/2K 生成式超分 + MOSS-Image 设定卡生成底层引擎规范与统一脚本。涵盖双卡显存/锁页内存护栏、FastH3 8+4 步二采有声文生视频（T2V）、多参考图/视频编辑（Ref2VA）、首帧图生视频（I2V）、Regenerate-2K 潜空间超分以及白底服装设定卡生成。用户要求在本地 ComfyUI 跑 MiniMax H3、排障 OOM/卡死/锁页内存报错、生成参考视频或做 H3 2K 视频超分时使用。
---

# 本地 ComfyUI + MiniMax H3 多模态视频引擎规范

本 Skill 沉淀自本地双 24 GB 显卡 + 128 GB 内存环境下对 MiniMax H3 全家桶（`FastH3 T2V`、`Hybrid Ref2VA`、`First-Frame I2V`、`Regenerate-2K`）与 `MOSS-Image` 的完整基准实测与踩坑结论，提供开箱即用的 API 工作流模板与统一 CLI 执行器。

配套资源：
- 统一 CLI 执行器（支持 `t2v` / `ref2va` / `i2v` / `regen2k` / `moss-sheet` / `free`）：[`scripts/comfy_h3_engine.py`](scripts/comfy_h3_engine.py)
- 双卡 WDDM 锁页内存安全启动器：[`scripts/launch_comfy_wddm_safe.py`](scripts/launch_comfy_wddm_safe.py)
- 标准 API 工作流模板：
  - [`assets/h3_fp8_2pass_clean.json`](assets/h3_fp8_2pass_clean.json) — 8+4 步 FastH3 有声文生视频（`1344×768`，15 秒约 10 分钟）
  - [`assets/h3_ref2va.json`](assets/h3_ref2va.json) — `MiniMaxH3ReferenceToVideo` 多图 + 视频参考编辑
  - [`assets/h3_i2v_first_frame.json`](assets/h3_i2v_first_frame.json) — `MiniMaxH3ImageToVideo` 首帧图生视频
  - [`assets/h3_regen2k.json`](assets/h3_regen2k.json) — `MinimaxH3LatentUpscaler3D` + `Regenerate-2K` 3 步生成式高清超分（`1920×1080` / `2560×1440`）
  - [`assets/moss_costume_edit.json`](assets/moss_costume_edit.json) — 单图 `TextEncodeQwenImageEdit` 纯白底服装设定卡/首帧精修

---

## 1. 运行时铁律与硬件排障契约（必读，禁止回退）

1. **UTF-8 控制台环境变量（防死锁第一铁律）**：
   - Windows 默认 GBK 控制台下，只要任意自定义节点在 `logging.error` 输出非 GBK 字符就会抛 `UnicodeEncodeError`，导致 ComfyUI Prompt 队列**永久假死挂起**。启动前必须设置：
     ```powershell
     $env:PYTHONUTF8="1"; $env:PYTHONIOENCODING="utf-8"
     python main.py --listen 0.0.0.0 --port 8188 --lowvram --reserve-vram 4 --cache-ram 8 48 --cuda-device 0
     ```
2. **`--reserve-vram 4` 显存余量铁律（24 GB 显卡必加）**：
   - `qwen3vl_32b_minimax_h3_int8_convrot`（约 22.8 GiB）在编码多张参考图 + 视频帧时，若不加 `--reserve-vram 4`，必在 `llama.py` MLP 层触发 CUDA OOM。
   - 严禁在 `--cuda-device all` 模式下强行把 32B CLIP 的 `SelectCLIPDevice` 绑死到小显存副卡；统一设 `"device": "default"` 交由原生 DynamicVRAM 调度。
3. **Windows WDDM 64 GB 锁页内存墙（双开 ComfyUI 核心边界）**：
   - Windows WDDM 对全系统 CUDA 锁页内存（Pinned Memory）有 **50% 物理内存硬上限**（128 GB 机器全系统共 `64 GB`），而 ComfyUI 默认单进程申请 `MAX_PINNED_MEMORY = ram * 0.40`（`52.3 GB`）。
   - 单路满血 `MiniMaxH3ReferenceToVideo`（`qwen3vl_32b` 全量 + `minimax_h3` DynamicVRAM）峰值需 `36–40 GB` 锁页内存。**在 128 GB Windows 上严禁双开两路满血 `H3 Ref2VA`**（合计 `~80 GB > 64 GB`），否则副实例必报 `[WARNING] Pin error` 并触发 `comfy_aimdo` 的 `RuntimeError: hostbuf_file_reader_read failed`。
   - **正确做法**：重度 `H3 Ref2VA` 固定单跑主卡（CPU 直连 PCIe 4.0 x16，`~25 GB/s`）；双实例（`:8188` + `:8189`）仅用于「一重一轻」异构并发（如 `:8188` 跑 H3 视频 + `:8189` 跑 MOSS 生图或轻量任务），并使用 `scripts/launch_comfy_wddm_safe.py` 将两实例 `MAX_PINNED_MEMORY` 限制在 `22 GB + 18 GB = 40 GB`。
4. **跨模型切换显存清理与温控**：
   - 在 `MiniMax H3` 与 `MOSS-Image` / `Regen-2K` 之间切换前，必须先调 `POST /free`（`{"unload_models": true, "free_memory": true}`）。
   - 批量队列每镜间隔检查 `nvidia-smi` 温度，任一 GPU `> 79°C` 时暂停冷却 20 秒。

---

## 2. 五大生成模式与实测避坑指南

### 模式 A：高速有声文生视频（`h3_fp8_2pass_clean.json`）
- **模型组合**：`fastvideo_fasth3_trim_8step_fp8.safetensors`（`int8_qk` + `fused_modulation` + `chunk_ff` 全开）+ `minimax_h3_latent_upscaler_3d_fp16.safetensors` + 视频/音频双 VAE。
- **两阶段采样黄金参数**：
  - **一采（`672×384`，8 步 Euler/simple）**：可挂 `MiniMaxH3TeaCache`（`rel_l1_thresh=0.15, start_step=2, end_step=-2`），3s 约 54s。
  - **3D 潜空间上采样（`2.0x` → `1344×768`）+ 二采（4 步 Beta `denoise=0.55`）**：**绝对禁止在二采开启 TeaCache！** 实测二采开 `0.15` 画面明显模糊磨平，开 `0.08` 零命中等于白挂。
- **实测负优化黑名单（切勿启用）**：
  - ❌ **RTX 30 系（SM86）禁用 Veda 稀疏注意力**：predictor 开销 4.77s/步，比原生慢。
  - ❌ **禁用 `H3ChunkedPass2` 分块二采**：帧间闪烁严重。
  - ❌ **禁用 `int8_tensorwise` FastH3**：全黑输出。

### 模式 B：多图 / 视频参考编辑（`h3_ref2va.json`）
- **模型组合**：`minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safetensors` + `qwen3vl_32b_minimax_h3_int8_convrot.safetensors`。
- **API 节点动态键名契约**：
  - Autogrow 输入必须使用**带点号扁平键**：`"ref_images.ref_image_0"`, `"ref_images.ref_image_1"` ... 以及 `"ref_videos.ref_video_0"`。
  - `LoadVideo` 输出为 `VIDEO` 对象，必须先接 `GetVideoComponents` 拆出 `IMAGE(0)` 才能连入 `ref_videos.ref_video_0`。
  - Prompt 中的标签为 **1-based**：`<Picture 1>` 对应 `ref_image_0`，`<Video 1>` 对应 `ref_video_0`。
- **帧数与注意力复杂度规律**：
  - `length` 必须严格满足 **`17k + 5`**（`56, 73, 90, 107, 124...`）。
  - 参考视频/音频 Token 全量参与每步自注意力（平方级复杂度）：单镜控制在 `56–90` 帧（2.3–3.8s）性价比最高（3090 Ti 单镜约 `5.5–11 分钟`）；切勿一次性塞入 15s（362f）参考视频（单镜耗时高达 45 分钟）。

### 模式 C：首帧图生视频（`h3_i2v_first_frame.json`）
- **适用场景**：纯静态插画动效化，或 `Ref2VA` 无法识别人体结构的极端趴地/被炉遮挡死角镜头（先精修首帧再做无 `<Video 1>` 的纯首帧 I2V）。

### 模式 D：Regenerate-2K 生成式高清超分（`h3_regen2k.json`）
- **模型组合**：`MinimaxH3LatentUpscaler3D` + `minimax_h3_fl2va_pruned_w6a8.safetensors` + `minimax_h3_open_regenerate_2k_r128.safetensors`（LoRA `strength=1.0`）。
- **API 必踩坑提示**：
  - `MinimaxH3LatentUpscaler3D` 的目标尺寸**必须用扁平键**：
    `"mode": "target dimensions"`, `"mode.width": 1920`（或 `2560`）, `"mode.height": 1080`（或 `1440`）——传嵌套字典会直接报错 `execute() missing 'mode'`！
  - 固定采用 `ManualSigmas`：`"0.909375, 0.857143, 0.666667, 0.0"`（3 步 Euler），56 帧升 2K 约 10 分钟，可将 `1024×576` 草稿片段重绘为锐利的 `1080p` / `2K` 终版母带。

### 模式 E：MOSS-Image 纯白底服装设定卡与单图精修（`moss_costume_edit.json`）
- **模型组合**：`moss_image_sft_bf16` + `moss_image_edit_lora_rank_64_bf16` + `qwen3.5_9b_bf16` + `flux2-vae`（1024² 约 20 秒）。
- **使用边界与防削顶铁律**：
  - **严禁直接重绘番剧正片多人物帧**（会退化为厚涂塑料感并产生水印乱码）；专门用于把正式礼服设定卡改绘成**纯白底（`#FFFFFF`）泳装/常服参考卡**供 `H3 Ref2VA` 使用。
  - 送入单图 `TextEncodeQwenImageEdit` 前，**必须在原立绘顶部额外补 `220–260px` 纯白边距**（输出 `768×1280`），否则极易削掉发冠、高帽与兽耳尖！

---

## 3. 快速命令行调用示例

```bash
# 1. 释放 ComfyUI 显存与缓存模型
python skills/comfyui-minimax-h3/scripts/comfy_h3_engine.py free --comfy-url http://127.0.0.1:8188

# 2. FastH3 8+4 步有声文生视频 (1344x768)
python skills/comfyui-minimax-h3/scripts/comfy_h3_engine.py t2v \
  --prompt "2D anime ocean sunrise, silver-haired girl standing on cliff, wind blowing cloak" \
  --frames 73 --seed 42 \
  --comfy-output E:/ComfyUI-app/output --out ./out_t2v.mp4

# 3. 角色服装设定卡生成（自动顶部补白 240px 防削顶）
python skills/comfyui-minimax-h3/scripts/comfy_h3_engine.py moss-sheet \
  --image ./clean_refs/claude_front.png \
  --prompt "Keep exact anime girl identity and full hair crown with generous white space above head; change dress into crimson-orange two-piece bikini on pure solid white background" \
  --comfy-input E:/ComfyUI-app/input --comfy-output E:/ComfyUI-app/output \
  --out ./cast/claude_swimsuit.png

# 4. 将 576p/768p 分镜通过 Regenerate-2K 超分至 1920x1080 (或 2560x1440)
python skills/comfyui-minimax-h3/scripts/comfy_h3_engine.py regen2k \
  --video ./renders/shot_001/final_001.mp4 \
  --prompt "Crisp 2D television anime cel-shaded linework, vibrant colors, sharp eyes and hair details" \
  --width 1920 --height 1080 --frames 56 \
  --comfy-input E:/ComfyUI-app/input --comfy-output E:/ComfyUI-app/output \
  --out ./renders/shot_001/final_001_1080p.mp4
```

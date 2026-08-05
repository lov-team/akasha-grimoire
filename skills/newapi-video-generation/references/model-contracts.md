# 模型契约

## MiniMax H3 Text-to-Video

- 模型：`minimax-h3/text-to-video`
- `prompt`：1–7000 字符。
- `duration`：整数 4–15，默认 6。
- `aspect_ratio`：`21:9`、`16:9`、`4:3`、`1:1`、`3:4`、`9:16`，必填。
- `resolution`：`768P` 或 `2K`，默认 `2K`。
- 仅文生视频；参考图使用其他 H3 SKU，不能传给本模型。

## Kling 2.5 Turbo Text-to-Video Pro

- 模型：`kling/v2-5-turbo-text-to-video-pro`
- `prompt`：最多 2500 字符。
- `duration`：字符串 `5` 或 `10`。
- `aspect_ratio`：`16:9`、`9:16` 或 `1:1`。
- `negative_prompt`：最多 2500 字符。
- `cfg_scale`：0–1，步长 0.1。
- 仅文生视频。

## Kling 3.0

- 模型：`kling-3.0/video`
- `duration`：字符串整数 3–15。
- `aspect_ratio`：`16:9`、`9:16` 或 `1:1`；传参考图时上游可自适应，但脚本仍显式发送请求值。
- `mode`：`std`、`pro` 或 `4K`。
- `sound`：布尔值。
- 单镜头：`multi_shots=false`，使用 `prompt`；`image_urls` 最多两张，依次为首帧和尾帧。
- 多镜头：`multi_shots=true`，使用 `multi_prompt`；每镜头含 `prompt` 和 1–12 秒 `duration`，总时长仍为 3–15 秒。
- 元素引用：在 `kling_elements` 定义名称，并在 prompt 中用 `@名称` 引用。复杂结构通过 `--metadata-json` 传入。

这些字段来自对应 KIE 模型的 `/api/v1/jobs/createTask` 契约；new-api 将 `metadata` 原样映射到上游 `input`。

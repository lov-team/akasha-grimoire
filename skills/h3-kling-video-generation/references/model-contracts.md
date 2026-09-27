# 模型契约

## MiniMax H3 Max

- 模型：`h3-max`（兼容端点按参考素材选择 text/image/reference；也可显式使用下列 SKU：`minimax/h3-max/text-to-video`、`minimax/h3-max/image-to-video`、`minimax/h3-max/reference-to-video`）。脚本对通用 `h3-max` 的路由：无图保持文生视频；一张图为首帧图生视频；带参考视频或音频时改用 reference SKU；两张及以上图片无法区分首尾帧与参考图，拒绝提交。
- `prompt`：1–50000 字符。模型只按官方 Context-IR 格式理解 Prompt，写法见 [`h3-context-ir-prompting.md`](h3-context-ir-prompting.md)。
- `prompt_expansion_mode`：`disabled` 原样使用；`balanced`（上游默认）和 `quality` 由官方扩写器改写成 Context-IR，改写结果在任务结果的 `expanded_prompt`。脚本 `--prompt-expansion auto`（默认）对 Context-IR Prompt 发送 `disabled`，普通文字不发送该字段；显式值原样发送。
- `seed`：可选整数；省略时上游随机，固定后便于 A/B 复现。
- `duration`：整数 5–15，默认 5；24 fps。
- `resolution`：`480P`、`768P` 或 `1080P`，默认 `768P`。`768P` 是原生生成分辨率，`1080P` 是在 768P 结果上的潜空间精修；`1080P` 来自 fal 官方契约，网关透传需实测确认。
- `aspect_ratio`：文生视频支持 `21:9`、`16:9`、`4:3`、`1:1`、`3:4`、`9:16`，默认 `16:9`，不支持 `adaptive`；参考生视频另支持 `adaptive` 且默认 `adaptive`；图生视频由首帧图片决定画幅，不发送该字段。
- 图生视频：使用 `h3-max-i2v`，`--image` 一张为首帧，两张依次为首帧和尾帧，最多两张。
- 参考生视频：图片、`reference_video_urls` 和 `reference_audio_urls` 合计最多 12 个文件；视频每段 2–15 秒、合计不超过 15 秒，音频同样。fal 的 H3 总览页另写明图片最多 9 张、视频和音频各最多 3 段、音频必须搭配至少一张图片或一段视频；H3 Max 按同样限制准备素材，脚本对只有音频的参考请求给出警告。显式 reference SKU 可在只有一个参考文件时保持参考模式。
- H3 Max 的图片必须通过顶层 `images` 传入，以便 new-api 在兼容端点分类；显式 image SKU 的 `image_url`/`end_image_url` 仍写入 metadata。

## MiniMax H3 Text-to-Video

- 模型：`minimax-h3/text-to-video`
- `prompt`：1–7000 字符。
- `duration`：整数 4–15，默认 6。
- `aspect_ratio`：`21:9`、`16:9`、`4:3`、`1:1`、`3:4`、`9:16`，必填。
- `resolution`：`768P` 或 `2K`，默认 `2K`。
- 仅文生视频；参考图使用其他 H3 SKU，不能传给本模型。

## MiniMax H3 Image-to-Video

- 模型：`minimax-h3/image-to-video`；CLI 别名：`h3-i2v`、`minimax-h3-i2v`。
- `prompt`：1–7000 字符。
- `duration`：整数 4–15，默认 6。
- `resolution`：`768P` 或 `2K`，默认 `2K`。
- `image_url`：首帧图片 URL；`end_image_url`：尾帧图片 URL。至少提供一个，也可同时提供。
- CLI 中第一项 `--image` 映射 `image_url`，第二项映射 `end_image_url`，最多两项；同时写入请求顶层 `images`，使兼容端点在提交前识别为图生视频并处理参考素材。
- 图片不超过 30 MB，边长 256–5760 像素，宽高比 0.4–2.5。视频沿用参考帧比例，不传 `aspect_ratio`。
- 参考图片必须是无需 Cookie 或 Authorization 即可读取的稳定公共 HTTPS URL。
- 顶层 `images` 是兼容端点的请求分类信号，metadata 中的 `image_url` / `end_image_url` 是 KIE 原生输入；两层必须同时存在，不能互相替代。
- 实测 `2K` 输出为 1440×1920、24 fps；实际尺寸仍由参考帧比例决定，3:4 输入不会自动扩展为 9:16。
- 结果可能包含 AAC 音轨。正式旁白或配乐项目应只取视频流，避免模型原音轨混入。
- 首尾参考帧构图差异过大时，上游可能直接切镜或产生场景突变；应改为 A/B 两镜或拆成独立片段，不把切换当作连续运镜。

### 公共参考图验收

- 只使用任务全周期内可匿名访问的公共 HTTPS URL。
- 上传后重新下载，核对本地与远端的 SHA-256、字节数、MIME 和像素尺寸；返回 HTML、挑战页或状态异常即判失败并更换端点。
- 临时托管服务只作为可替换传输层，不写成固定依赖。本次生产中曾遇到 HTTP 412、HTTP 503 和“成功响应但内容是 HTML”，说明只检查 URL 或状态码不足以确认素材可用。

### 已验证故障与恢复

1. 仅在 metadata 中传 `image_url` / `end_image_url` 时，兼容端点可能将请求误判为文生视频，并返回：

   ```text
   HTTP 400: kie createTask failed (code 422): aspect_ratio is required for text-to-video
   ```

   恢复：把相同参考图同时写入顶层 `images`，保持 metadata 中的 KIE 原生字段，然后重新提交。

2. 不要为绕过上述误判而补发 `aspect_ratio`。该请求可能进入任务后失败：

   ```text
   video task failure: generate playground failed, task id is blank
   ```

   恢复：删除图生视频的 `aspect_ratio`，修正顶层 `images` 分类信号，再提交一次正确请求。

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

这些字段来自对应 KIE 模型的 `/api/v1/jobs/createTask` 契约；兼容端点将 `metadata` 映射到上游 `input`。H3 图生视频的原生字段为 `image_url` 和 `end_image_url`，不要混用海螺官方渠道的 `first_frame_image`。

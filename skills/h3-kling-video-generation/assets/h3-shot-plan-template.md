# 镜头制作单：{{SHOT_ID}}

本文件只留在本地，不发送给模型。模型只接收第 4 节指向的英文 Context-IR 文件。

## 1. 镜头定位

- 成片位置：{{PREVIOUS_SHOT}} → 本镜 → {{NEXT_SHOT}}
- 唯一核心事件：{{ONE_VISIBLE_EVENT}}
- 起始可见状态：{{START_STATE}}
- 结束可见状态：{{END_STATE}}

- 风格圣经：{{STYLE_BIBLE_FILE_OR_NONE}}（剧情序列每个单元逐字复用，见写作规范第 12 节）
- 中文四字段草稿（剧情镜头填写，再按第 12.3 节句序改写成英文）：
  - 场景环境：{{LOCATION_REFERENCE_SPACE_PRACTICAL_LIGHT_AMBIENCE}}
  - 镜头设计：{{SHOT_SIZE_ANGLE_COMPOSITION_FOCAL_LENGTH_DISTANCE_RESULT_FOCUS}}
  - 可见动作：{{MICRO_ACTION_CHAIN_AND_LINES}}
  - 光影布光：{{KEY_SOURCE_DIRECTION_FACE_SPLIT_RIM_BACKGROUND}}

## 2. 请求参数（写进 CLI，不写进 Prompt）

- 模式与模型：{{T2VA_I2VA_FL2VA_OR_REF2VA}} / {{MODEL}}
- 时长：{{SECONDS}} 秒 = 建立 {{S}} + 动作 {{S}} + 台词 {{S}} + 结束保持 {{S}}
- 画幅与分辨率：{{ASPECT_RATIO}} / {{RESOLUTION}}
- 素材顺序：`--image` 1 = {{FIRST_FRAME_OR_SUBJECT}}；`--image` 2 = {{LAST_FRAME_OR_NONE}}；`--reference-video` = {{NONE_OR_ROLE}}；`--reference-audio` = {{NONE_OR_ROLE}}
- seed：{{SEED_OR_NONE}}；提示词扩写：auto（Context-IR 自动发送 disabled）

## 3. 后期与剪辑（不写进 Prompt）

- 预计采用区间：{{EDIT_IN}}–{{EDIT_OUT}} 秒
- 字幕、标题、UI 与精确 MG：{{POST_ITEMS_OR_NONE}}
- 模型音轨：{{KEEP_OR_REPLACE}}
- 转场与交棒：{{TRANSITION_NOTES}}

## 4. 模型 Prompt

- 文件：{{PROMPT_FILE}}（由 `assets/h3-prompt-<mode>.txt` 复制填写）
- lint：`python3 skills/h3-kling-video-generation/scripts/video_generation.py lint --prompt-file {{PROMPT_FILE}} --model {{MODEL}} --duration {{SECONDS}} --images {{N}}` → {{LINT_RESULT}}

## 5. 验收

- [ ] 任务成功；`MEDIA` 行的时长、分辨率、fps 和音轨符合请求
- [ ] 首、中、尾帧的身份、服装、构图和起止状态正确
- [ ] 核心事件完成且可读；没有多余切镜、突变或肢体错误
- [ ] 台词清晰、嘴型同步；声音层次符合 soundscape
- [ ] 结论：{{PASS_OR_ONE_CHANGE_FOR_THE_NEXT_RUN}}

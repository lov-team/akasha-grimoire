# 视频生产合同

## 推荐目录

```text
video-project/
├── brief.md
├── script.md
├── continuity.yaml
├── shot-list.csv
├── storyboard.md
├── generation-plan.json
├── sources.json
├── edl.json
├── subtitles.srt
├── render/
│   ├── commands.txt
│   └── final.mp4
└── qa/
    ├── technical.json
    ├── frames/
    └── review.md
```

大型源文件和生成结果可位于仓库外 staging；清单中的路径必须是可解析的绝对路径或相对项目根目录的路径。

## 阶段门

| 阶段 | 必需输入 | 必需输出 | 通过条件 |
| --- | --- | --- | --- |
| 合同 | 用户目标、已有素材 | `brief.md` | 平台、画幅、时长、受众、核心信息明确 |
| 编导 | brief | 脚本、连续性、镜头表、分镜 | 每个关键 beat 有覆盖且可执行 |
| 素材 | 镜头表 | `sources.json`、采用素材 | 每个采用项可打开、可探测、可追溯 |
| 生成 | generation plan | 片段和任务映射 | 代表镜头先验收，采用片段与 shot id 对齐，供应商与路由原因有记录 |
| 剪辑 | 素材、声音、字幕 | `edl.json`、成片 | EDL 可复现，导出无缺轨或临时占位 |
| QA | 成片、脚本、镜头表、来源清单 | 技术报告、代表帧、审阅记录 | 技术与创作检查均通过 |

## 默认合同

- 未指定时，社交短视频采用 9:16、1080×1920、30 fps、H.264/AAC。
- 未指定时，横版叙事或演示采用 16:9、1920×1080、30 fps、H.264/AAC。
- 旁白项目先完成声音定时，再锁定镜头长度。
- AI 视频以 3—8 秒单一主要动作镜头为默认单元；复杂动作拆镜头。
- 所有计费生成先完成单镜头 smoke，不把提交成功当成画面通过。

## 可追溯标识

对全流程保持稳定标识：`shot_id`、`asset_id`、`source_id`、`generation_task_id`、`edl_clip_id`。QA 问题必须引用这些标识之一，避免仅写“第二段不对”。

生成入口选定后，在对应镜头填写 `provider`、`model` 和 `routing_reason`。使用默认第一顺位时说明其满足的镜头约束；发生降级时记录前一入口不兼容、不可用或验收失败的具体原因。

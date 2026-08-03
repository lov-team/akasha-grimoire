# EDL JSON

最小格式：

```json
{
  "version": 1,
  "timeline": {
    "width": 1280,
    "height": 720,
    "fps": 30,
    "sample_rate": 48000,
    "background": "black"
  },
  "clips": [
    {
      "clip_id": "C001",
      "shot_id": "S001",
      "path": "/absolute/path/source.mp4",
      "source_in": 1.25,
      "source_out": 4.75,
      "fit": "cover",
      "volume": 1.0
    }
  ]
}
```

## 字段

- `source_in` 包含，`source_out` 不包含；两者单位为秒。
- `fit` 使用 `cover` 或 `contain`。`cover` 居中裁切填满，`contain` 保持完整画面并补背景。
- `volume` 是片段原音比例；`0` 静音，负数无效。
- `path` 可以相对 EDL 所在目录，也可以是绝对路径。
- clips 按数组顺序顺接；基础渲染器暂不表达叠加轨、转场或速度变化。

渲染器拒绝未知顶层版本、重复 `clip_id`、不存在的路径、越界入出点、非正时长和不支持的 fit。

# 素材清单格式

`sources.json` 是一个对象：

```json
{
  "version": 1,
  "assets": [
    {
      "asset_id": "A-S003-001",
      "shot_id": "S003",
      "status": "candidate",
      "source_url": "https://example.test/watch/123",
      "source_page": "https://example.test/watch/123",
      "creator": "",
      "license": "",
      "retrieved_at": "2026-08-03T12:00:00Z",
      "local_path": "/absolute/path/clip.mp4",
      "sha256": "...",
      "bytes": 12345,
      "media": {
        "duration": 12.4,
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "video_codec": "h264",
        "audio_codec": "aac"
      },
      "notes": "开门动作，保留动作前后各 1 秒"
    }
  ]
}
```

## 规则

- `asset_id` 唯一；更新同一项时保留第一次 `retrieved_at`。
- `source_url` 用于实际取得文件，`source_page` 用于人工回看来源页面；两者可以相同。
- 清单可保留候选和弃用项，`status` 使用 `candidate`、`selected` 或 `rejected`。
- `local_path` 指向经过验证的真实文件；派生代理另设新 `asset_id` 并在 `notes` 写明父项。
- 对 URL 日志和最终展示移除敏感查询参数，但本地私有清单可在确有需要时保留可重现地址。

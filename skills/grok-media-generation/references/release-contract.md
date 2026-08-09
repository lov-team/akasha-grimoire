# Grok CPA/new-api 发布合同

核对日期：2026-08-10。

## 固定来源版本

- CPA：`v7.2.126`，commit `aed6d3861238a4415b8b2bf9f721e0f5fe2e3b23`。
- new-api：commit `c5cc612aae4c2b4e355d95d7ce09aa7b510730c9`。
- Grok Build 权威 checkout：`/Volumes/外接硬盘/user/yesone/project/grok-build`，commit `8a14c91d88875a831a38b3a066b1683116bcb31c`。
- 上述 Grok Build checkout 根目录 `SOURCE_REV`：`27b3c66635e2c0bf213429a36ab916f25d59df20`。
- 相对上一审阅版本 `6e386420825bd44ae648c63e7c8cba12fcec9401`，模型目录及 Image/Edit/Video wire 契约未变；相关 builder 变化仅涉及证书和描述清洗，因此现有模型及媒体 payload 无需追加修改。
- 1.5 稳定模型及本合同中的新图片 payload 已通过生产 smoke；仓库测试仍以本地假服务为默认，不重复产生费用。

## 上游源码审阅规则

1. 使用 Akasha 仓库之外的权威 checkout `/Volumes/外接硬盘/user/yesone/project/grok-build`；不要复制或 vendor 到 Skill 目录。
2. 每次调查 Grok 协议、模型目录、认证头、图片、视频或 STT 时，先更新或重新核对该 checkout，并在审阅记录中同时写下完整 Git commit 与根目录 `SOURCE_REV`。
3. 图片/视频 wire 契约以 `crates/codegen/xai-grok-tools/src/implementations/grok_build/` 下的真实 request builder 为审阅入口；可选文本模型还需用已认证 Grok CLI 的 `/v1/models` 响应确认，不能只依据源码中的版本门控注释。
4. 修改 CPA/new-api 适配器前重新读取该来源。采用的 wire 变更先在 CPA 落地，再以精确 payload 测试镜像到 new-api；新增 CPA 媒体模型还必须同时完成分类、路由、默认价格和目录同步测试。
5. CPA 目录同步必须同时读取 `internal/registry/models/models.json` 与 `internal/registry/model_definitions.go` 的硬编码 ID，避免手工 fallback 掩盖目录漂移。

## 能力与默认价格

以下数值是该 new-api release 的 `defaultModelPrice` 固定价格表值；部署侧配置和分组倍率可以覆盖最终计费：

| 模型 | 能力 | 默认价格表值 |
|---|---|---:|
| `grok-imagine-image` | 图片生成、单图/多图编辑 | `0.02` |
| `grok-imagine-image-quality` | 高质量图片生成、单图/多图编辑 | `0.05` |
| `grok-imagine-video` | 视频生成、视频编辑 | `0.05` |
| `grok-imagine-video-1.5` | 1.5 稳定版视频生成、视频编辑 | `0.08` |
| `grok-imagine-video-1.5-preview` | 1.5 Preview 视频生成、视频编辑 | `0.08` |

图片生成默认 `aspect_ratio=auto`。单图编辑不发送 `aspect_ratio`；多图编辑没有显式值时发送 `auto`。当前 canonical 画幅为 `1:1`、`16:9`、`9:16`、`4:3`、`3:4`、`3:2`、`2:3`、`2:1`、`1:2`、`19.5:9`、`9:19.5`、`20:9`、`9:20`、`auto`。发往 xAI 图片 API 的引用对象为裸 `{"url":"..."}`。

## 部署后的模型目录缓存窗口

滚动部署期间，不同 CPA/new-api 进程的模型注册表和渠道内存缓存可能短暂不同步。健康探针成功只说明进程可服务，不保证每个实例的 `/v1/models` 已同时暴露新模型。

发布验证按以下顺序执行：

1. 先确认服务健康、目标镜像/版本和 CPA release 均正确。
2. 使用预期用户组和 token 对已认证 `/v1/models` 做有界重试，直到每个目标实例都出现 `grok-imagine-video-1.5`；同时观察 CPA 模型注册/刷新与 new-api `channels synced from database` 日志。
3. 等待至少一个部署配置的模型/渠道同步周期。new-api 的 `SYNC_FREQUENCY` 默认是 60 秒；应使用实际配置值并留少量调度余量，而不是在首次缺失时判定发布失败。
4. 目录收敛后再执行单个最小生成 smoke，分别验证模型可路由和真实 payload；不要只以目录出现代替请求验证。
5. 只有等待窗口结束后仍持续缺失，或健康、版本、注册日志、最小请求出现确定性错误时，才进入部署故障/回滚判定。记录每次检查的时间、实例、模型目录结果和最终 smoke 结果。

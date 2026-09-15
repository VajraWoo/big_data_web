# 基础设施说明

本目录保留 T001–T005 正式使用过的 Spark、MongoDB、Silver 清洗和连接器基础设施。它用于说明前期大规模清洗与关联的可复现环境，不是当前 Web 应用的启动入口，也不包含最终语义模型服务。

## 保留内容

- `compose.yaml`：Spark Master、两个 Worker、MongoDB 及基础验收容器。
- `compose.silver.yaml`：Silver 清洗阶段的挂载和作业配置。
- `compose.connector.yaml`：Spark–MongoDB 连接器验收配置。
- `spark/`：固定 Spark 运行环境和连接器依赖校验。
- `tests/`：上述基础设施的静态配置与 smoke test。

这些内容对应正式数据链的前期阶段：Spark 4.1.2 完成原始评论与商品数据的清洗、校验和关联。后续 T010 聚合使用 DuckDB，不使用 Spark。

## 不属于本目录的正式能力

- T007 与 T011：Qwen3.5-4B、vLLM、NVIDIA/Linux 离线运行。
- T008 与 T009：离线 taxonomy 构建、审核和确定性映射。
- T010：DuckDB 确定性聚合。
- 正式后端：`backend_generated/backend/`。
- 正式前端：`frontend_story_dashboard/frontend/`。

第一周未采用的本地 CPU NLP 环境和旧 Web 环境配置已移至 `historical_experiments/`，不参与正式结果，也不应作为当前启动说明使用。

## 当前边界

T001–T011 已全部完成。本目录中的基础设施代码用于保留真实实现与提交记录，不要求在最终交付阶段重跑。正式架构、技术选型和各阶段结果见：

- `specs/001-merchant-review-insights/plan.md`
- `specs/001-merchant-review-insights/technical-selection.md`
- `pipelines/README.md`

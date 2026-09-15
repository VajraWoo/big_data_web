# Technical Selection: Merchant Review Insights

**Status**: T007–T011 completed; backend/frontend integrated
**Updated**: 2026-09-09

## 1. Final technology map

| Capability | Selected technology | Runtime | Final evidence |
|---|---|---|---|
| Raw cleaning and joins | Spark 4.1.2, Parquet | Docker, CPU | 2,128,605 reviews and 94,327 products processed |
| Formal product scope | DuckDB over Parquet | Windows, CPU | 139 products, 13 categories, 116,728 reviews |
| Full-review insight extraction | Qwen3.5-4B, vLLM structured output | NVIDIA Linux, RTX 4090 | T007 complete, 350,656 valid insights |
| Category community discovery | all-MiniLM-L6-v2, Fast Community Detection | Offline batch | 4,992 first-level clusters |
| Taxonomy consolidation | Category grouping plus human review | Offline review | 887 category-level themes |
| Insight mapping | Deterministic Python join | Local CPU | 230,278 mapped; 85,122 unmapped |
| Theme aggregation | DuckDB | Local CPU | T010 formal Gold complete |
| Improvement generation | Qwen3.5-4B, vLLM structured output | NVIDIA Linux, RTX 4090 | 7,747 groups generated; 7,734 corrected suggestions |
| API | FastAPI, GoldInsightsRepository | Local Web | T010/T011/override integrated |
| UI | Vue 3, TypeScript, Vite, ECharts | Browser | Positive/negative dashboard and detail drawer integrated |

Spark 的正式作用是前期大规模清洗和关联。正式 T010 使用 DuckDB；这两点不冲突。

## 2. T007 frozen configuration and result

- Model: `Qwen/Qwen3.5-4B`
- Revision: `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`
- Backend: NVIDIA/Linux vLLM 0.28.0 continuous batching
- Prompt: `t007-context-insight-v2.1`
- Maximum generation: 1024 tokens
- Input/output: 116,728 / 116,728 rows, unique review_id exact-once
- Status: success 116,571; failed 157
- Valid insights: 350,656
- Inference time: 13,238.895 seconds
- End-to-end time: 13,308.124 seconds
- Throughput: 8.81705 reviews/s during inference
- Frozen production source: `prototypes/t007_context_insight_v2_1`

旧 sentence-level ABSA、NLI attribution、Qwen 2B 和 Transformers 串行 runner 只保留为历史 baseline，不再参与正式结果。

## 3. T008 and T009 decisions

T008 采用按 category 的高置信度 community discovery，而不是全局强制分类。一级 cluster 经人工审核后汇总为 887 个正式 theme。community membership 只覆盖 230,278 条 candidate；未入 community 的 85,122 条保留为 `unmapped_no_cluster`。

T009 通过 candidate/cluster/taxonomy 确定性 join 建立映射，不使用 nearest theme、相似度阈值或 low-confidence 强塞。该决策保护 taxonomy 统计不受稀有表达和噪声污染。

## 4. T010 formal aggregation

正式 T010 使用 `pipelines/theme_aggregation_duckdb_job.py`。输出目录为 `data/gold/t010-aggregation-20260908-v1-duckdb`。

最终规模：

- products: 139
- product facets: 417
- themes: 15,852
- theme timeseries: 116,328
- theme reviews: 222,069
- validation errors: 0

主题数以 887 个 taxonomy theme 为准；15,852 是不同商品、taxonomy 和 sentiment 的聚合组合。

## 5. T011 formal generation

T011 不是在线 AI 服务，而是独立离线批处理。输入来自 T009 `mapped_by_cluster`，按 `parent_asin + taxonomy_id` 聚合。negative insight 触发，mixed insight 只作辅助；普通组单次生成，只有超出固定上下文预算的组才按固定顺序分块。

复用 T007 已验证的 Qwen3.5-4B revision、vLLM continuous batching、原生 structured JSON、checkpoint/resume 和失败隔离。没有新增 embedding、聚类、reranking、阈值实验、队列服务或在线推理 API。

7,747 个 trigger group 已全部生成。全量质量检查发现 13 个组是 positive 假负面，因此 corrected 正式结果为 7,734 条：

- `data/gold/t011-final-corrected-20260909-v1.ndjson`
- `data/gold/t010-polarity-overrides-20260909-v1.json`

## 6. Polarity override policy

13 个 correction 不回写冻结的 T009/T010。`GoldInsightsRepository` 加载版本化 override，并执行：

- negative 列表排除 correction；
- positive 列表以 positive 呈现；
- 如果同一 taxonomy 已有原生 positive 行，避免重复展示纠正前的 negative 行；
- improvement API 排除 correction；
- theme detail 返回 effective sentiment。

## 7. Application selection

正式后端为 `backend_generated/backend`，正式前端为 `frontend_story_dashboard/frontend`。前端请求 FastAPI，FastAPI 只读 Gold 文件。改进建议位于负面主题详情，不建立独立顶层 tab，也不在页面打开时调用模型。

## 8. Rejected paths

以下路线不再进入当前范围：旧 ABSA/NLI attribution、Qwen 2B、T010 Spark 重做、未聚类 insight 强制映射、新 embedding/clustering/reranking、batch benchmark、在线模型服务、Redis/Celery/向量数据库和重新运行 T007–T011。

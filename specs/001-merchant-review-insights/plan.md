# Implementation Plan: Merchant Review Insights

**Status**: Implemented through T011 and Web integration
**Updated**: 2026-09-09

## 1. Final architecture

```text
Amazon review/product source
  → Spark Silver cleaning and joins
  → formal scope: 139 products / 116,728 reviews
  → T007 Qwen3.5-4B full-review insight extraction
  → T008 category community discovery + human-reviewed taxonomy
  → T009 deterministic insight-to-taxonomy mapping
  → T010 DuckDB product/theme/sentiment aggregation
  → T011 offline product-theme improvement generation
  → polarity override for 13 verified false-negative groups
  → GoldInsightsRepository
  → FastAPI
  → Vue dashboard
```

## 2. Runtime boundaries

- Spark 4.1.2 负责原始评论/商品清洗、关联和 Silver 生产；它是正式前期数据处理技术。
- T007 和 T011 在 NVIDIA/Linux 上使用 Qwen3.5-4B、vLLM continuous batching 和 RTX 4090 离线运行。
- T008/T009 使用 Python 完成候选、taxonomy 审核产物和确定性 join。
- 正式 T010 使用 DuckDB，不依赖 Spark。
- FastAPI 和 Vue 只读取已经生成的 Gold；请求路径不运行模型或数据 pipeline。

## 3. Stage decisions

### T007

强制读取完整 `text_raw`，一次评论可产生零到多个 grounded insight。模型为 `Qwen/Qwen3.5-4B` revision `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`；输出保留 success、partial_success、failed、rejected insight 和程序计算的 evidence offsets。最终 116,728 条输出 exact-once，350,656 条有效 insight。

### T008

只使用 `target_scope=current_product`。先按 category 做 MiniLM + Fast Community Detection 高置信度社区发现，再由人工审核合并为正式 taxonomy。未成社区的稀有或不稳定 insight 不强制进入主题。最终为 4,992 一级 cluster、887 taxonomy theme。

### T009

通过 `candidate_id` 把 T007/T008 candidate 与一级 cluster、cluster-to-taxonomy 连接。230,278 条 `mapped_by_cluster` 进入 canonical theme；85,122 条 `unmapped_no_cluster` 原样保留但不参与 T010 canonical-theme 聚合。

### T010

DuckDB 按商品、taxonomy、唯一 review 和月份完成确定性聚合。正式输出包括 products、product facets、themes、theme timeseries 和 theme reviews。mixed 规则和 ratio 分母固定在 data model 中。

### T011

从 T009 mapped insight 按 `parent_asin + taxonomy_id` 聚合。negative 触发生成，mixed 只作补充。Qwen 离线生成一段产品级、主题级修改建议，支持 structured JSON、continuous batching、checkpoint/resume 和超长组顺序分块。初始 7,747 个触发组全部运行完成。

质量检查确认其中 13 组属于假负面。最终 corrected 文件含 7,734 条建议；13 组通过独立 override 文件在 API 展示层视为 positive，不重写 T009/T010。

## 4. Application integration

正式后端位于 `backend_generated/backend`，使用 `GoldInsightsRepository` 读取 T010 Gold、T011 corrected NDJSON 和 polarity override。已有 improvements route 返回离线建议。

正式前端位于 `frontend_story_dashboard/frontend`。顶层仅保留正面和负面；负面主题抽屉依次呈现趋势、T011 建议和真实评论，正面抽屉不呈现建议。

## 5. Verification strategy

- 数据阶段：行数、主键唯一性、exact-once、状态合计、taxonomy 引用完整性和 JSON/Parquet 可读性。
- T011：触发键覆盖、success/failed、空 suggestion、support review 去重和人工质量检查。
- override：固定 13 个键，仅允许 negative→positive，negative/positive/improvement API 行为一致。
- 后端：真实 Gold API tests 和 smoke test。
- 前端：类型检查、生产 build 和关键交互联调。

## 6. Remaining work

不再安排数据 pipeline 任务。剩余工作只包括前端视觉微调、后端接口小修、联调、README/PPT/汇报材料和最终验收。

# Tasks: Merchant Review Insights

**Status**: T001–T011 and Web integration completed
**Updated**: 2026-09-09

## Data foundation

- [x] **T001–T005** 使用 Spark 清洗、验证并关联 2,128,605 条评论和 94,327 条商品元数据，产出正式 Silver。
- [x] **T006** 确定前端正式范围：139 个整机商品、13 个类别、116,728 条评论。

## Formal insight pipeline

- [x] **T007** 使用完整评论上下文和 Qwen3.5-4B 生成 structured insight。
  - 116,728 条输入/输出，review_id exact-once。
  - 350,656 条有效 insight；保留 success、partial_success、failed 和 rejected insight。
  - 模型 revision、prompt version、evidence offsets 和失败记录均可审计。
  - 已完成 fresh 200 条语义验收并冻结，不再重跑。

- [x] **T008** 按 category 构建并人工审核 taxonomy。
  - 输入 315,400 条 `current_product` candidate。
  - 4,992 个一级 cluster exact-once 映射到 887 个 category-level taxonomy theme。
  - taxonomy 已冻结，不执行全局直接发布或强制覆盖孤立 insight。

- [x] **T009** 生成全量 insight-taxonomy 映射。
  - 230,278 条 `mapped_by_cluster`。
  - 85,122 条 `unmapped_no_cluster`。
  - candidate_id exact-once，无孤儿或 category 错配；不做 nearest mapping。

- [x] **T010** 使用 DuckDB 生成商品级主题聚合。
  - 139 products。
  - 15,852 条 `product × taxonomy × sentiment` theme 记录。
  - 116,328 条 theme timeseries。
  - 222,069 条 theme-review evidence。
  - ratio 分母、review 去重和 mixed 规则已固定并验证。

- [x] **T011** 生成 product-theme improvement suggestion。
  - 生成键：`parent_asin + taxonomy_id`。
  - 原始 trigger group 7,747；Qwen3.5-4B + vLLM + RTX 4090 离线全量完成。
  - 已完成全量质量检查和局部清洗。
  - 13 个假负面组从 improvement 结果剔除，正式 corrected 结果为 7,734 条。
  - 正式文件：`t011-final-corrected-20260909-v1.ndjson`。

- [x] **T011-CORRECTION** 建立 13 个 polarity override。
  - 正式文件：`t010-polarity-overrides-20260909-v1.json`。
  - API 层 negative 剔除、positive 纳入、improvement 不显示。
  - 未修改或重跑 T009/T010。

## Application integration

- [x] **WEB-BE** 正式 FastAPI 后端接入 `GoldInsightsRepository`。
  - products、categories、overview、positive/negative themes、theme detail、trend 和 review evidence 已接入。
  - improvements endpoint 已读取 T011 corrected 数据。
  - 13 个 polarity override 已应用到主题列表、详情和 improvements。

- [x] **WEB-FE** 正式 Vue 前端完成数据接入和主要 UI 调整。
  - 顶层仅保留正面/负面。
  - 负面主题详情显示趋势、改进建议和评论证据；正面主题不显示建议。
  - 排行默认前 8，支持查看全部/收起。
  - 商品标题简化展示，评论详情与 KPI 样式已优化。

## Current acceptance work

- [ ] **A001** 完成最终前后端联调和边界场景检查。
- [ ] **A002** 完成必要的视觉微调。
- [ ] **A003** 完成 README、PPT 和汇报材料。
- [ ] **A004** 执行最终验收并记录结果。

## Frozen constraints

- 不重跑 T007、T008、T009、T010 或 T011。
- 不再配置 GPU/AutoDL。
- 不把 T010 改为 Spark。
- 不新增 embedding、clustering、reranking、nearest-theme 或 threshold tuning。
- 不在 API 请求中运行任何离线计算或模型推理。

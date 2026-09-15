# 正式数据流水线说明

本文是 T001–T011 的统一代码索引。各阶段均已完成；这里记录实际采用的实现、边界和正式结果，不表示最终交付时需要重新运行。

## 总体流程

```text
T001–T005 Spark 清洗、校验与关联
  → T006 确定 139 个商品和 116,728 条评论的正式范围
  → T007 Qwen3.5-4B 完整评论 insight 提取
  → T008 category-level 聚类与人工审核 taxonomy
  → T009 candidate/cluster/taxonomy 确定性映射
  → T010 DuckDB 商品主题聚合
  → T011 Qwen3.5-4B 离线改进建议
  → GoldInsightsRepository → FastAPI → Vue
```

## T001–T006：数据基础与正式范围

T001–T005 使用 Spark 4.1.2 完成原始评论与商品元数据的校验、清洗、去重和关联，形成 Silver。主要代码为 `silver_job.py`、`cleaning.py`、`run_silver.ps1` 以及 `infra/` 下的 Spark 配置。

T006 确定 Web 使用的正式范围：139 个商品、13 个类别、116,728 条评论。相关范围过滤和输入整理代码位于 `scope_filter_job.py`、`product_group_job.py`、`nlp_input_v2_job.py` 等文件。

T001–T006 此前没有逐阶段 README，主要记录在 SDD 中；本文件现作为统一入口。

## T007：完整评论 insight 提取

- 正式源码：`prototypes/t007_context_insight_v2_1/`
- 模型：`Qwen/Qwen3.5-4B`
- revision：`851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`
- 运行环境：NVIDIA/Linux、vLLM continuous batching、RTX 4090
- 输入/输出：116,728 / 116,728 条评论，`review_id` exact-once
- 有效结果：350,656 条 insight

runner 读取完整 `text_raw`，使用 structured JSON 输出，并保留 evidence offsets、失败记录和 checkpoint/resume 状态。详细文件说明见 `prototypes/t007_context_insight_v2_1/README.md`。

## T008：category-level taxonomy

T008 仅处理 `target_scope=current_product` 的 315,400 条 candidate。先按商品类别执行 MiniLM + Fast Community Detection，形成 4,992 个一级 cluster，再经人工审核汇总为 887 个 category-level taxonomy theme。

正式合并与校验入口分布在：

- `t008_category_taxonomy_rewrite/`
- `t008_taxonomy_consolidation/`
- `t008_large_taxonomy_pipeline/`
- `t008_cluster_audit_export/`
- `t008_finish_bundle/`

这些目录保留各自 README。正式结果位于 `data/gold/t008-final-20260908-v1/`。

## T009：确定性 insight-taxonomy 映射

- 正式源码：`insight_taxonomy_mapping_job.py`
- 映射方式：通过 `candidate_id` 连接 candidate、一级 cluster 与审核后的 taxonomy
- 结果：230,278 条 `mapped_by_cluster`；85,122 条 `unmapped_no_cluster`
- 边界：不执行 nearest mapping，不把未聚类 insight 强制归类

Git 中保留正式校验和类别摘要：`data/gold/t009-insight-taxonomy-20260908-v1/`。

## T010：DuckDB 商品主题聚合

- 正式源码：`theme_aggregation_duckdb_job.py`
- 引擎：DuckDB，不使用 Spark
- 正式输出：`data/gold/t010-aggregation-20260908-v1-duckdb/`
- 规模：139 个商品、15,852 条 `product × taxonomy × sentiment`、116,328 条月度趋势、222,069 条评论证据

脚本对主键、taxonomy 引用、ratio 分母、评论去重和 mixed 规则进行确定性校验，验证结果记录在输出目录的 `validation.json`。

## T011：产品改进建议

- 输入准备：`prepare_t011_inputs.py`
- 正式生成：`run_t011_qwen.py`
- 生成键：`parent_asin + taxonomy_id`
- 模型与环境：与 T007 相同的 Qwen3.5-4B revision，NVIDIA/Linux、vLLM、RTX 4090
- 原始生成组：7,747
- 正式纠正结果：7,734 条建议

negative insight 触发生成，mixed 只作同组补充证据。全量检查确认 13 个组是假负面后，最终文件为：

- `data/gold/t011-final-corrected-20260909-v1.ndjson`
- `data/gold/t010-polarity-overrides-20260909-v1.json`

后端只读这些离线 Gold 文件；API 请求不会启动模型、Spark 或 DuckDB 聚合作业。

## 正式应用入口

- 后端：`backend_generated/backend/`
- 前端：`frontend_story_dashboard/frontend/`
- SDD：`specs/001-merchant-review-insights/`

第一周未采用的本地 CPU NLP 和旧 Web 环境已归档到 `historical_experiments/`，不属于本流程。

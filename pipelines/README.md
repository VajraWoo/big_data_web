# T001–T011 正式数据流水线

本目录按课程任务编号组织最终采用的代码。所有数据阶段均已完成，本文件用于代码审查和结果追溯，不要求重新运行流水线。

| 阶段 | 代码目录 | 作用 | 正式结果 |
|---|---|---|---|
| T001–T006 | [`foundation/`](foundation/) | Spark 清洗、关联、文本质量检查与正式商品范围 | 139 个商品、116,728 条评论 |
| T007 | [`t007/`](t007/) | Qwen3.5-4B 完整评论 insight 提取 | 350,656 条有效 insight |
| T008 | [`t008/`](t008/) | 类别内聚类、taxonomy 审核与最终汇总 | 4,992 个一级 cluster、887 个 theme |
| T009 | [`t009/`](t009/) | candidate/cluster/taxonomy 确定性连接 | 230,278 条 mapped、85,122 条 unmapped |
| T010 | [`t010/`](t010/) | DuckDB 商品主题聚合 | 15,852 条主题组合及趋势、证据 |
| T011 | [`t011/`](t011/) | Qwen3.5-4B 离线生成改进建议 | 7,734 条正式建议 |

正式后端位于 `backend_generated/backend/`，正式前端位于 `frontend_story_dashboard/frontend/`。二者只读取已生成的 Gold；API 请求不会运行模型、Spark 或 DuckDB 聚合作业。

未进入最终方案的 ABSA、NLI、旧主题生成和早期 prototype 已移至 `historical_experiments/legacy_semantic_pipeline/`。

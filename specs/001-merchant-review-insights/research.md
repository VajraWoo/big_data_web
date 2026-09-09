# Research Decisions: Merchant Review Insights

**Finalized**: 2026-09-09

## Accepted decisions

1. 完整评论级 grounded insight 比旧 sentence-level ABSA/NLI attribution 更适合作为正式语义来源；T007 使用 Qwen3.5-4B 和完整 `text_raw`。
2. taxonomy discovery 与全量分类是不同任务。T008 只用高置信度 community 发现稳定主题并按 category 人工审核；未入 cluster 的 insight 在 T009 保留为 unmapped，不强制分类。
3. T009 映射应是确定性 join，不新增 nearest-theme、embedding 或阈值校准。
4. T010 是中等规模、单机可完成的确定性聚合，DuckDB 比重新部署 Spark 聚合更直接。Spark 仍是前期全量清洗的正式技术。
5. 改进建议的业务单位应为商品×负面 taxonomy，而不是单条评论或全类别共用建议。
6. T011 应消费 T009 的高密度 insight，不重新读取 116,728 条评论做语义识别。
7. T011 必须离线预生成；FastAPI 只读结果，避免在线 GPU 成本和不稳定延迟。
8. 超长主题只按固定 insight 顺序分块，不抽样，不做代表性选择、聚类、reranking 或额外压缩算法。
9. 质量检查发现的少量 polarity 错误应使用独立、版本化 override 修正展示，不重跑或原地改写冻结 Gold。
10. 改进建议适合放在负面主题详情上下文中，而不是增加第三个顶层入口；这样建议、趋势和证据共享同一 product-theme 语境。

## Final evidence

- T007: 116,728 reviews, 350,656 valid insights.
- T008: 4,992 first-level clusters, 887 reviewed category themes.
- T009: 230,278 mapped, 85,122 unmapped.
- T010: 139 products, 15,852 product-theme-sentiment rows, 116,328 timeseries rows, 222,069 evidence rows.
- T011: 7,747 generated groups; 13 false-negative groups removed/reclassified; 7,734 corrected suggestions.

## Rejected approaches

旧 ABSA/NLI attribution、Qwen 2B、未聚类 insight 强制分类、T010 Spark 重做、在线推理 API、Redis/Celery、向量数据库、新 embedding/clustering/reranking 和 batch-size benchmark 均不进入当前实现。

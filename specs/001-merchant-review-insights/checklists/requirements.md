# Specification Quality Checklist：家电整机评论洞察

**Updated**: 2026-09-09

- [x] T007–T011 的正式完成状态、冻结边界和产物路径已记录。
- [x] T007 保留原评论、结构化 insight、evidence、polarity、scope 与逐评论状态。
- [x] T008 taxonomy 按 category 建立并经过人工审核，不把全局聚类直接作为正式 taxonomy。
- [x] T009 对全部 315,400 条 current-product candidate exact-once 对账，未聚类项保留为 `unmapped_no_cluster`。
- [x] T010 使用 DuckDB，按唯一 `review_id` 聚合，ratio 分母及 mixed 规则已固定。
- [x] T011 以 `parent_asin + taxonomy_id` 为生成单位，最终保留 7,734 条正式建议。
- [x] 13 个假负面组有显式 correction 文件；正负主题及建议接口使用同一修正规则。
- [x] 后端契约覆盖商品、分类、overview、主题、趋势、评论证据、改进建议和批次元数据。
- [x] 前端只保留正面/负面入口，改进建议仅在负面主题详情中展示。
- [x] Spark 只属于既有数据清洗阶段；T010 正式实现是 DuckDB。
- [x] 旧 sentence-level ABSA、NLI attribution、Qwen 2B、旧 TF-IDF/zero-shot 产物不再进入当前 Gold。
- [x] 正式数据、API、测试、构建和最终验收的责任边界可验证。

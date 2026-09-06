# Research Decisions：家电整机评论洞察

**Updated**: 2026-09-06

本文件只记录已批准结论；技术证据见[technical-selection.md](technical-selection.md)。

- 第一阶段对象为139个近期仍活跃、历史有效评论不少于300条的家电整机，共116,728条评论。
- 前端商品集合、完整NLP集合和正式Gold集合相同。
- VADER负责整体情感；ABSA负责属性及属性情感；两者不能相互替代。
- 明确建议由`cross-encoder/nli-MiniLM2-L6-H768`处理全部评论句子；`entailment > contradiction`即接受，不设置MiniLM召回入口，也不能由关键词认定。
- 隐式改进方向来自负面ABSA属性和对应原句。
- MiniLM与Fast Community Detection按商品合并相似表达。
- 主题名来自高频属性、中心观点短语和模板，失败时使用中心短语。
- Spark负责ETL与聚合，Transformer在Windows XPU运行。
- 第一阶段不包含零件、配件、预警、推荐、竞品分析、模型训练或模型竞赛。

旧TF-IDF主题和CPU Spark四标签DeBERTa zero-shot需求方案已否决，只保留历史结果，不作为新版设计依据。

# Research Decisions：家电整机评论洞察

**Updated**: 2026-09-06

本文件只记录已批准结论；技术证据见[technical-selection.md](technical-selection.md)。

- 第一阶段对象为139个近期仍活跃、历史有效评论不少于300条的家电整机，共116,728条评论。
- 前端商品集合、完整NLP集合和正式Gold集合相同。
- VADER负责整体情感；ABSA负责属性及属性情感；两者不能相互替代。
- 明确建议由`cross-encoder/nli-MiniLM2-L6-H768`处理全部评论句子；只有entailment同时高于neutral和contradiction时才接受，不设置MiniLM召回入口，也不能由关键词认定。
- 评价主题与改进需求是两条业务链：正负评价只来自对应ABSA；明确建议不作为负面评价。
- 隐式改进候选来自负面ABSA属性和对应原句；同一负面证据可同时服务负面评价和改进需求，且不视为重复污染。
- MiniLM与Fast Community Detection按商品及主题类型合并相似表达；固定相似度0.75、至少10条不同评论，无合格社区时返回已完成的空结果，不生成fallback。
- 主题名来自高频属性、中心观点短语和模板；无法可靠形成改进方向时使用中心问题或建议短语，不生成原文没有表达的方案。
- Spark负责ETL与聚合，Transformer在Windows XPU运行。
- 第一阶段不包含零件、配件、预警、推荐、竞品分析、模型训练或模型竞赛。

旧TF-IDF主题、CPU Spark四标签DeBERTa zero-shot需求方案、忽略neutral的旧NLI接收结果以及强制fallback主题均已否决，只保留历史结果，不作为新版设计依据。

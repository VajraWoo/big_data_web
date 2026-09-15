# T009：Insight–Taxonomy 映射

正式实现为 `insight_taxonomy_mapping_job.py`。它通过 `candidate_id` 确定性连接 T007 candidate、T008 一级 cluster 和审核后的 taxonomy，不执行 nearest mapping。

正式结果为 230,278 条 `mapped_by_cluster` 和 85,122 条 `unmapped_no_cluster`。Git 中的校验与类别摘要位于 `data/gold/t009-insight-taxonomy-20260908-v1/`。

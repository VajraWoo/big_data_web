# T001–T006：数据基础与正式范围

T001–T005 使用 Spark 4.1.2 完成原始评论和商品元数据的校验、清洗、去重与关联，形成 Silver。T006 从中确定 Web 使用的 139 个商品、13 个类别和 116,728 条评论。

主要代码：

- `silver_job.py`、`cleaning.py`、`run_silver.ps1`：Silver 清洗与回放校验；
- `text_profile_job.py`、`text_profile.py`：文本质量与语言检查；
- `scope_filter_job.py`、`nlp_input_v2_job.py`：正式商品范围和评论输入；
- `product_group_job.py`：商品类别候选分析；
- `tests/`：基础阶段单元测试。

基础设施位于 `infra/`。该阶段已完成，不需要在最终交付时重跑。

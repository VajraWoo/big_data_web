# T010：DuckDB Gold 聚合

正式实现为 `theme_aggregation_duckdb_job.py`，使用 DuckDB 对 T009 已映射 insight 按商品、taxonomy、sentiment、月份和唯一评论进行确定性聚合，不使用 Spark。

正式输出位于 `data/gold/t010-aggregation-20260908-v1-duckdb/`，包括 139 个商品、15,852 条主题组合、116,328 条月度趋势和 222,069 条评论证据。

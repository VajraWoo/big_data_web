# T008：Category-level Taxonomy

T008 将 315,400 条 `current_product` candidate 按商品类别处理，形成 4,992 个一级 cluster，并经人工审核合并为 887 个 category-level taxonomy theme。

子目录：

- `clustering/`：candidate 准备、MiniLM 编码和一级聚类；
- `taxonomy/`：审核 packet、taxonomy 决策校验与应用；
- `large_categories/`：大类别的分块处理；
- `audit/`：人工审核材料导出；
- `finalization/`：13 个类别的最终汇总与完整性校验；
- `review_decisions/`：已采用的人工审核决策记录。

正式结果位于 `data/gold/t008-final-20260908-v1/`。这些子目录属于同一个 T008，不是六个独立课程任务。

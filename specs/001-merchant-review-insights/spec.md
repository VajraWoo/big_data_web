# Feature Specification: Merchant Review Insights

**Status**: Data pipeline complete; backend/frontend integrated
**Authoritative date**: 2026-09-09

## 1. Objective

面向家电商品评论构建可追溯洞察系统。用户可以选择正式商品，分别查看正面与负面主题、数量、占比和时间趋势，下钻真实评论证据，并在负面主题详情中查看基于该商品真实问题生成的产品改进建议。

## 2. Completed scope

| Stage | Contract | Accepted result |
|---|---|---|
| T007 | 完整 `text_raw` → grounded insight | 116,728 条输入；350,656 条有效 insight；已验收并冻结 |
| T008 | `current_product` insight → category taxonomy | 315,400 candidates；4,992 一级 cluster；887 个审核后 category-level theme；已冻结 |
| T009 | candidate → cluster/taxonomy mapping | 230,278 mapped，85,122 unmapped；exact-once；已冻结 |
| T010 | mapped insight → product/theme aggregates | 139 products；15,852 themes rows；116,328 timeseries；222,069 evidence rows；已冻结 |
| T011 | product × negative taxonomy → suggestion | 7,747 trigger groups；纠正 13 个假负面后正式保留 7,734 条建议；已完成 |

`15,852` 表示 `product × taxonomy × sentiment` 聚合记录数，不能解释为 taxonomy 数量；taxonomy 总数为 887。

## 3. Functional requirements

- **FR-001** 系统只允许查询正式范围中的 139 个商品。
- **FR-002** T007 必须保留 `topic_raw`、`polarity`、`evidence`、evidence offsets、`target_scope`、处理状态和失败信息；下游只消费有效的 `current_product` insight。
- **FR-003** T008 taxonomy 必须按 category 构建并经过人工审核，不允许把全局语义聚类直接发布为正式 taxonomy。
- **FR-004** T009 必须为 315,400 条 candidate 保留 exact-once 映射状态。未进入 community 的记录标记为 `unmapped_no_cluster`，不得强制 nearest-theme 映射。
- **FR-005** T010 只聚合 `mapped_by_cluster`，按唯一 `review_id` 计算主题评论数、占比和月度趋势。
- **FR-006** T010 商品级 ratio 分母是该商品全部正式唯一评论；月度 ratio 分母是该商品当月全部正式唯一评论。
- **FR-007** 同一商品、taxonomy 和 review 同时存在正负观点，或存在原生 mixed 时，聚合 polarity 为 mixed；mixed 不重复计入 positive 或 negative。
- **FR-008** T011 的唯一生成键是 `parent_asin + taxonomy_id`。只有含 negative insight 的组触发；mixed 只能作为已触发组的补充证据。
- **FR-009** T011 必须是离线批处理。API 和前端不得实时调用 Qwen。
- **FR-010** 最终改进建议必须具体、可执行、由该组 evidence 支持，不得虚构问题或生成营销文案。
- **FR-011** 13 个已确认的假负面组通过版本化 polarity override 在展示/API 层改为 positive，不修改或重跑冻结的 T009/T010。
- **FR-012** negative 查询必须排除 13 个 override 组；positive 查询必须按 positive 返回；improvement API 不得返回这些组的建议。
- **FR-013** 前端只保留正面/负面两个顶层入口。改进建议显示在负面主题详情抽屉中，正面主题不显示建议。
- **FR-014** 主题详情必须同时支持趋势和真实评论证据；主题列表默认前 8 个并支持展开/收起。
- **FR-015** 单个分析维度无数据时返回明确空状态，不生成 fallback 主题。
- **FR-016** API 请求只读取已验证的本地 Gold，不启动 Spark、DuckDB 聚合作业或模型推理。

## 4. Non-functional requirements

- 数据和生成结果必须可追溯到 `review_id`、`candidate_id`、`taxonomy_id` 和正式批次。
- 所有离线阶段保留失败状态，不静默删除输入。
- 冻结批次不原地覆盖；修正使用独立版本文件或展示层 override。
- 后端接口面向只读查询，前端加载不依赖 GPU。
- 正式代码、文档和验证记录必须区分当前实现与历史 baseline。

## 5. Acceptance state

数据链 T007→T011 已完成；T011 已完成全量质量检查和局部清洗；`GoldInsightsRepository` 已接入 T010、T011 和 polarity override；Vue 前端已接入正负主题、趋势、证据和负面主题改进建议。当前剩余范围仅为联调、小修、视觉调整、汇报材料和最终验收。

## 6. Frozen boundaries

禁止重跑 T007–T011，禁止重新配置 GPU/AutoDL，禁止把正式 T010 改回 Spark，禁止新增 embedding、clustering、nearest mapping、reranking、threshold tuning 或在线推理服务。除非出现新的、可复现的正式数据缺陷并由项目负责人明确授权，否则不得突破上述边界。

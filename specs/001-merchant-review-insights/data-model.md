# Data Model: Amazon 商品需求洞察与质量问题预警

**Date**: 2026-09-02  
**Contract**: [contracts/openapi.yaml](contracts/openapi.yaml)

## 1. Modeling rules

- Bronze 永不原地修改；清洗结果只通过新 `processing_run_id` 生成。
- `source_line_number` 与数据发布标识共同构成原始记录身份。语义指纹只用于重复标记，
  不能替代原始身份，否则会错误删除真实的重复出现。
- `asin` 表示评论中的商品变体，`parent_asin` 表示父商品；两者始终同时保留。
- “品牌/店铺组合”只是公开历史元数据的分析维度，绝不表达当前用户拥有该组合。
- 所有比例同时保存 `numerator`、`denominator`、原始值和区间；不只保存舍入后的百分数。
- 所有 Gold 结论保存 `data_release_id`、`processing_run_id`、规则/参数/模型版本和 `as_of`。
- 缺失时间观察不填成零；`insufficient` 结果不进入正式排序或预警。

## 2. Layer flow

```text
RawDatasetRelease
  ├─ BronzeReview ───────────────┐
  └─ BronzeProductMetadata ──────┤
                                 ▼
                         SilverProductVariant
                                 │
                         SilverTrustedReview
                                 │
                  ┌──────────────┴──────────────┐
                  ▼                             ▼
          General Gold summaries       Selected ProductGroups
                                                │
                               Aspect/Demand model outputs
                                                │
                  ┌───────────┬──────────┬───────┴───────────┐
                  ▼           ▼          ▼                   ▼
             IssueSignal  DemandTopic QualityAlert RepresentativeEvidence
```

## 3. Bronze entities

### 3.1 RawDatasetRelease

| Field | Type | Rules |
|---|---|---|
| `data_release_id` | string | PK；例如 `amazon-reviews-2023-appliances-v1` |
| `dataset_name` | string | 固定来源名称，不伪装成实时 Amazon 数据 |
| `source_url` | URI | 官方数据页或文件 URL |
| `source_version` | string | 发布版本/截止时间；本数据截至 2023-09 |
| `downloaded_at` | UTC datetime | 必填 |
| `files[]` | object[] | 文件名、角色、字节数、行数、SHA-256 |
| `usage_terms_url` | URI/null | 使用条件记录 |
| `manifest_version` | string | 清单 schema 版本 |

Validation: 文件摘要在运行前重算并匹配；不匹配则本次运行进入 `failed`，不得继续生成 Gold。

### 3.2 BronzeReview / BronzeProductMetadata

原始 JSON 行按文件和行号登记，不重命名、不纠正值。最小审计字段：
`data_release_id`、`source_file`、`source_line_number`、`raw_json`、`ingested_at`、
`parse_status`、`parse_error_code`。成功和失败行数之和必须等于 manifest 行数。

## 4. Silver entities

### 4.1 SilverTrustedReview

| Field group | Fields | Validation / semantics |
|---|---|---|
| Identity | `review_id`, `data_release_id`, `source_file`, `source_line_number` | `review_id` 由发布+文件+行号确定；唯一且稳定 |
| Product | `asin`, `parent_asin`, `metadata_join_status` | `asin` 必填；父商品可因关联失败为空但不得静默丢行 |
| User | `user_id_hash` | 原 ID 不在 Web 输出；稳定哈希仅用于重复/独立性分析 |
| Content | `title_raw`, `text_raw`, `text_normalized`, `language`, `text_status` | 保留原文；标准化文本不得覆盖原文 |
| Rating | `rating`, `rating_valid`, `low_rating` | 合法范围 1–5；极端评分本身不是异常 |
| Context | `reviewed_at`, `review_month`, `verified_purchase`, `helpful_vote` | 时间统一 UTC/月；票数必须为非负整数或标记无效 |
| Quality | `exact_hash`, `near_duplicate_cluster_id`, `duplicate_scope`, `rating_text_mismatch`, `burst_flag` | 代理信号只作标记，不宣布虚假 |
| Eligibility | `eligible_rating_stats`, `eligible_text`, `eligible_nlp`, `exclusion_reasons[]` | 按任务分别决定；空正文仍可参加评分统计 |
| Lineage | `processing_run_id`, `silver_rule_version` | 必填 |

`text_status` 枚举：`usable`、`empty`、`too_short`、`non_english`、`non_linguistic`、
`parse_failed`。每条记录无论状态如何都保留并计入去向报告。

### 4.2 SilverProductVariant

| Field | Type | Rules |
|---|---|---|
| `asin` | string | PK |
| `parent_asin` | string | 父商品关系 |
| `title` | string/null | 公开元数据 |
| `brand` | string/null | 仅真实存在时可筛选 |
| `store` | string/null | 仅真实存在时可筛选 |
| `categories` | string[] | 保留原路径及标准化路径 |
| `features` / `details` | object | 保留可解释字段，不强制扁平化全部内容 |
| `price` | decimal/null | 缺失不填零，不作为核心分析依赖 |
| `metadata_status` | enum | `usable`、`partial`、`invalid` |
| `processing_run_id` | string | 血缘 |

### 4.3 TextSentence and ModelPrediction

`TextSentence` 保存 `sentence_id`、`review_id`、句序号、原文跨度、规范化文本、候选来源。
`ModelPrediction` 保存任务、模型版本、输入句/属性、预测标签、各类概率、推理后端、运行
批次。多属性评论以多行预测表示；绝不把多种属性压成一个总情感。

## 5. Scope and calibration entities

### 5.1 ProductPortfolio

| Field | Type | Rules |
|---|---|---|
| `portfolio_id` | string | PK；来源类型+标准化公开值的稳定 ID |
| `portfolio_type` | enum | `brand` 或 `store` |
| `display_name` | string | 原始公开名称 |
| `normalized_name` | string | 仅用于聚合，不覆盖展示值 |
| `parent_asins` | string[]/relation | 一个父商品可出现在品牌和店铺两个组合中 |
| `ownership_disclaimer` | string | API/UI 必须返回公开数据声明 |

### 5.2 ProductGroup

| Field | Type | Rules |
|---|---|---|
| `product_group_id` | string | PK |
| `name` | string | 可由运营人员理解的业务名称 |
| `category_rule` | object | 可复现的元数据选择规则 |
| `selection_state` | enum | `candidate`、`selected`、`rejected` |
| `review_count`, `product_count`, `eligible_product_count` | integer | 必须能从 Silver 复算 |
| `semantic_coherence` | object | 评价方法和结果 |
| `representativeness` | object | 对完整 Appliances 的覆盖/偏差说明 |
| `selection_reasons`, `rejection_reasons` | string[] | 至少记录一种 |
| `aspect_taxonomy_version` | string/null | 仅 selected 群组必填 |

状态转换：`candidate → selected|rejected`。只有生成版本化选择报告后允许转换；不得根据结果
是否“好看”反向选择。

### 5.3 CalibrationReport

| Field | Type | Rules |
|---|---|---|
| `calibration_id` | string | PK |
| `calibration_type` | enum | `eligibility`、`priority_weights`、`alert`、`inference_backend` |
| `scope` | object | 全局或商品群 |
| `candidates[]` | object[] | 至少 3 个候选；参数及所有评价指标 |
| `selection_rule` | object | 在查看最终结果前声明 |
| `selected_candidate_id` | string/null | 报告完成前为空 |
| `decision_reason` | string/null | 不接受“经验合适” |
| `status` | enum | `draft`、`evaluated`、`approved`、`superseded` |
| `processing_run_id` | string | 可复现批次 |

状态转换：`draft → evaluated → approved → superseded`。参数只有 `approved` 后才能控制正式
Gold；任何改变产生新报告而不是原地覆盖。

## 6. Gold serving collections

MongoDB 中每一集合都同时保留业务键和批次键；更新采用新批次构建、校验后切换 active
run，防止页面读到半成品。

### 6.1 `portfolio_summary`

每个组合/时间范围的商品数、评论量、平均评分、低评分率、正文可用率、商品群摘要、最新
批次、公开数据声明。索引：`{portfolio_id: 1, period_end: -1, processing_run_id: 1}`。

### 6.2 `product_group_summary`

群组选择依据、覆盖量、属性体系版本、组合内商品数、质量状态及时间范围。索引：
`{product_group_id: 1, portfolio_id: 1, processing_run_id: 1}`。

### 6.3 `product_summary`

父商品与变体、组合、基本统计、准入等级和原因。准入结构分别保存 `basic_stats`、
`issue_ranking`、`trend_alert` 的状态、观测值、所需值、参数版本。索引：
`{parent_asin: 1, processing_run_id: 1}`、`{portfolio_id: 1, product_group_id: 1}`。

### 6.4 `issue_rankings`

业务键为父商品/属性/时期，字段包括独立提及分子/分母、原始负面率、Wilson 区间、收缩
后验及区间、影响/严重度/变化/持续性分项、总分、排名稳定性、资格状态、参数/模型版本、
证据 ID。只有 `qualified` 可获得正式 `rank`。

### 6.5 `issue_timeseries`

父商品/属性/月粒度的计数、分母、原始率、区间和观测状态。缺失月不生成伪零文档；API
通过时间范围和 `observation_status` 明确空档。

### 6.6 `demand_topics`

主题 ID、规范名称、`demand_type`（`explicit` 或 `implicit_experimental`）、群组、关联商品、
成员簇、规模、趋势、稳定性、置信度、模型/聚类版本及证据。只有 explicit 可有
`official_rank`；实验性主题的该字段必须为空。

### 6.7 `quality_alerts`

预警对象、指标、状态、严重级别、基线/近期窗口、分子分母、原始差异、最小业务效应、
后验概率、FDR 调整值、持续窗口、触发原因和证据。状态转换：
`candidate → confirmed|suppressed`；演示数据不提供真实外部通知或处置闭环。

### 6.8 `evidence_reviews`

证据 ID、结论引用、角色（`support`/`counterexample`）、原 `review_id`、未改写原文、评分、
时间、验证购买、有用票、重复簇、选择算法/分数和模型标签。每个正式结论至少 3 条，且在
存在反例时至少一条反例。

### 6.9 `analysis_runs`, `calibration_reports`, `model_evaluations`

- `analysis_runs`: 输入摘要、文件 hash、代码提交、依赖锁 hash、随机种子、阶段状态、行数
  守恒、耗时、Spark application ID、输出位置、失败信息；
- `calibration_reports`: 第 5.3 节的 Web 投影；
- `model_evaluations`: 数据切分、标注一致性、基线/主模型指标、分层误差、吞吐、资源、模型
  卡和适用边界。

## 7. ProcessingRun state machine

```text
registered
  → profiling
  → silver_processing
  → general_gold_processing
  → fine_nlp_processing          # 仅 selected 商品群
  → validating
  → published

任一运行中状态 → failed
failed → registered              # 新 attempt_id，不覆盖原失败记录
published → superseded           # 新批次原子切换后
```

只有满足以下条件才能 `published`：manifest hash 匹配；原始行去向守恒；Silver/Gold schema
通过；关联失败、排除和重复数量已报告；所有正式参数已 approved；核心模型达到 spec 阈值；
MongoDB 文档数/抽样公式与 Parquet 对账通过。

## 8. API-visible common states

- `analysis_status`: `ready`、`processing`、`insufficient`、`failed`、`not_selected`
- `qualification`: `insufficient`、`exploratory`、`qualified`
- `confidence_label`: `low`、`medium`、`high`，同时返回数值区间，不只给标签
- `demand_type`: `explicit`、`implicit_experimental`
- `evidence_role`: `support`、`counterexample`

所有非 `ready/qualified` 响应仍使用成功 HTTP 状态返回业务状态和原因；资源不存在使用
404；批次内部错误使用统一 Problem Details 5xx。前端不得把 `processing` 或过期批次显示为
有效空图。

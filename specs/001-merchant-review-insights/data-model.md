# Data Model：家电整机评论洞察

**Updated**: 2026-09-08

## Silver（保留现状）

- `reviews`：`review_id`、`asin`、`parent_asin`、原文、规范化正文、评分、月份、重复状态和批次。
- `products`：`parent_asin`、标题、店铺、正式类目路径和原始元数据。
- `text_features`：语言、置信度、长度、token数和`eligible_nlp`。

## 新版Gold

T007当前输出是候选批次，不因全量运行完成自动成为Gold。人工Gold与模型输出必须分离。

### `review_insight_runs`（T007候选）

每条评论一条运行记录：`review_id`、`parent_asin`、`asin`、`model_id`、`revision`、`prompt_version`、`processing_status`、`insights`、可选的`rejected_insights`、错误摘要和run id。

- `processing_status`: `success|partial_success|failed`。
- `success`表示响应及全部insight通过结构和grounding校验，允许`insights=[]`。
- `partial_success`表示至少一个insight有效，同时一个或多个候选被拒绝；合法结果和拒绝原因都必须保留。
- `failed`表示该评论没有可交付结构化结果；失败记录仍写入输出，不得省略。

每个`insights`元素包含：`topic_raw`、`polarity`、`evidence`、`evidence_char_start`、`evidence_char_end`、`target_scope`。`evidence`必须是`text_raw`连续原始子串，offset由程序计算；多次命中必须显式消歧，不能默认取第一次。`target_scope`用于区分当前商品、其他/旧/比较商品及服务或购买背景。模型不得直接提供最终offset。

### `insight_taxonomy_mappings`（T009）

每个T008 `current_product` candidate恰好一条：`candidate_id`、`review_id`、`parent_asin`、`product_category`、`topic_raw`、`evidence`、`polarity`、`target_scope`、可空的`cluster_id/taxonomy_id/canonical_theme_name`、`mapping_status`和批次。

- `mapped_by_cluster`：candidate是一级cluster member，且可沿`cluster_id → taxonomy_id`唯一映射到审核后taxonomy。
- `unmapped_no_cluster`：candidate未进入任何一级community；保留原始insight，但不进入canonical-theme聚合。
- 不执行nearest-theme补映射，不设置相似度阈值，不创造`low_confidence`状态。

### `analysis_products`

139个正式商品：`parent_asin`、标题、整机种类、历史评论数、活跃月份数、最后评论月份、scope版本和状态。

### `review_sentiment`

复用VADER结果：`review_id`、`parent_asin`、月份、compound、`positive|neutral|negative`、方法版本。

### `review_aspects`

每个属性一条：`aspect_id`、`review_id`、`parent_asin`、属性文本、`positive|neutral|negative|unknown`、置信度、字符起止位置、原句、模型revision和批次。

无属性和失败不伪造成空属性，记录在评论处理状态中。

### `explicit_suggestions`

每个确认建议句一条：`suggestion_id`、`review_id`、`parent_asin`、原句、NLI的entailment、neutral与contradiction分数、确认标签、模型revision和批次。只有entailment同时高于neutral和contradiction时确认。

### `product_analysis_facets`

每个商品固定记录三个分析维度：正面评价、负面评价和改进需求。字段为`parent_asin`、`theme_type`、可空的`sentiment`、`status`、`theme_count`、可空的`reason`和批次。分析完成但没有合格社区时记录`status=ready`、`theme_count=0`、`reason=no_qualified_theme`。

### `themes`

每个商品主题一条：`theme_id`、`parent_asin`、`evaluation|improvement`主题类型、主题名称、可空的`positive|negative`情感、来源类型集合、中心短语、高频属性、命名方式、评论数、占比和批次。评价主题的情感不可为空；改进需求的情感为空。

- 正面评价来源为`absa_positive`，负面评价来源为`absa_negative`。
- 改进需求来源为`explicit_suggestion|implicit_problem`，可同时包含两者。
- 不存在`nearest_review_fallback`主题。

### `theme_reviews`

主题证据映射：`theme_id`、`review_id`、`parent_asin`、来源类型、原句、原文、评分、月份和到聚类中心的相似度。

### `theme_timeseries`

`theme_id`、`parent_asin`、月份、主题评论数、该商品当月正式评论分母和占比。无日期评论不进入该集合。

T010固定口径：商品级分母为该`parent_asin`全部正式唯一`review_id`；月度分母为该商品该月全部正式唯一`review_id`。先按`parent_asin + taxonomy_id + review_id`去重并归并polarity：同一评论同一主题同时含正负观点或含原生`mixed`时记为一次`mixed`；仅有neutral与单一方向时保留该方向；仅neutral时为`neutral`。mixed不重复计入positive或negative。

### `analysis_runs`

阶段、输入路径、输出路径、模型与revision、设备、参数、开始/结束时间、输入/成功/无结果/失败数量、状态和错误摘要。

## 状态约束

- `analysis_status`: `pending|processing|ready|failed`
- `empty_reason`: `no_qualified_theme|null`
- `aspect_sentiment`: `positive|neutral|negative|unknown`
- `theme_type`: `evaluation|improvement`
- `theme_sentiment`: `positive|negative|null`
- `theme_source`: `absa_positive|absa_negative|explicit_suggestion|implicit_problem`
- `naming_method`: `template|center_phrase`

只有所有阶段计数验证通过的同一批次才可发布为MongoDB活动Gold。

# Data Model：家电整机评论洞察

**Updated**: 2026-09-06

## Silver（保留现状）

- `reviews`：`review_id`、`asin`、`parent_asin`、原文、规范化正文、评分、月份、重复状态和批次。
- `products`：`parent_asin`、标题、店铺、正式类目路径和原始元数据。
- `text_features`：语言、置信度、长度、token数和`eligible_nlp`。

## 新版Gold

### `analysis_products`

139个正式商品：`parent_asin`、标题、整机种类、历史评论数、活跃月份数、最后评论月份、scope版本和状态。

### `review_sentiment`

复用VADER结果：`review_id`、`parent_asin`、月份、compound、`positive|neutral|negative`、方法版本。

### `review_aspects`

每个属性一条：`aspect_id`、`review_id`、`parent_asin`、属性文本、`positive|neutral|negative|unknown`、置信度、字符起止位置、原句、模型revision和批次。

无属性和失败不伪造成空属性，记录在评论处理状态中。

### `explicit_suggestions`

每个确认建议句一条：`suggestion_id`、`review_id`、`parent_asin`、原句、NLI的entailment与contradiction分数、确认标签、模型revision和批次。

### `themes`

每个商品主题一条：`theme_id`、`parent_asin`、主题名称、`positive|negative`、`praise|explicit_suggestion|implicit_problem`来源类型集合、中心短语、高频属性、命名方式、评论数、占比和批次。

### `theme_reviews`

主题证据映射：`theme_id`、`review_id`、`parent_asin`、来源类型、原句、原文、评分、月份和到聚类中心的相似度。

### `theme_timeseries`

`theme_id`、`parent_asin`、月份、主题评论数、该商品当月正式评论分母和占比。无日期评论不进入该集合。

### `analysis_runs`

阶段、输入路径、输出路径、模型与revision、设备、参数、开始/结束时间、输入/成功/无结果/失败数量、状态和错误摘要。

## 状态约束

- `analysis_status`: `pending|processing|ready|failed`
- `aspect_sentiment`: `positive|neutral|negative|unknown`
- `theme_sentiment`: `positive|negative`
- `theme_source`: `praise|explicit_suggestion|implicit_problem`
- `naming_method`: `template|center_phrase`

只有所有阶段计数验证通过的同一批次才可发布为MongoDB活动Gold。

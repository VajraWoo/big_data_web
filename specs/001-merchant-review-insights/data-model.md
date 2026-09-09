# Data Model: Merchant Review Insights

**Status**: Implemented through T011
**Updated**: 2026-09-09

## 1. Identity rules

- Review identity: `review_id`
- Insight identity: `candidate_id`
- Taxonomy identity: `taxonomy_id`
- Product-theme identity: `parent_asin + taxonomy_id`
- Product-theme-sentiment aggregate identity: `parent_asin + taxonomy_id + sentiment`
- T011 generation identity: `input_id`, deterministically derived from `parent_asin + taxonomy_id`

## 2. T007 review insight record

每条输入评论保留一条处理记录：

```text
review_id, parent_asin, asin,
model_id, revision, prompt_version,
processing_status,
insights[], rejected_insights[],
error_type?, error_message?, raw_output?
```

每个有效 insight：

```text
topic_raw, polarity, evidence,
evidence_char_start, evidence_char_end,
target_scope
```

`evidence` 是 `text_raw` 的连续原始子串；offset 由程序计算。`processing_status` 为 `success | partial_success | failed`，失败不得静默删除。

## 3. T008 taxonomy model

### Candidate

从有效 `current_product` insight 形成：

```text
candidate_id, review_id, parent_asin,
product_title, product_category,
polarity, topic_raw, evidence, candidate_text
```

### First-level cluster

```text
cluster_id, product_category,
member candidate_ids, center/label metadata
```

### Reviewed taxonomy

```text
taxonomy_id, product_category,
canonical_theme_name
```

每个一级 cluster 在 `cluster-to-taxonomy` 中 exact-once；taxonomy 不跨 category 发布。

## 4. T009 insight-taxonomy mapping

315,400 条 candidate 各保留一条：

```text
candidate_id, review_id, parent_asin,
product_title, product_category,
polarity, target_scope,
topic_raw, evidence, candidate_text,
cluster_id?, taxonomy_id?, canonical_theme_name?,
mapping_status
```

`mapping_status`：

- `mapped_by_cluster`: 通过一级 cluster 确定性映射到 taxonomy；
- `unmapped_no_cluster`: 未进入 community，保留但不进入 canonical-theme 聚合。

## 5. T010 aggregate model

### products

一行一个 `parent_asin`，包含 title、category、正式 review_count、active_month_count、last_review_month 和 analysis_status。

### product_facets

一行一个商品分析维度：`positive_evaluation | negative_evaluation | improvement`。字段包含 facet、status、theme_count、empty_reason 和 error_summary。后端可根据 effective sentiment 和 T011 结果刷新展示计数。

### themes

唯一键为 `theme_id`，业务聚合键为 `parent_asin + taxonomy_id + sentiment`：

```text
theme_id, parent_asin, taxonomy_id,
name, sentiment, review_count,
ratio_value, ratio_status, ratio_definition_id
```

### theme_timeseries

```text
theme_id, month, review_count,
ratio_value, ratio_status, ratio_definition_id
```

### theme_reviews

```text
theme_id, review_id, text, evidence_text,
rating, review_date, review_month
```

### Ratio and mixed rules

商品级分母为该 `parent_asin` 全部正式唯一 `review_id`；月度分母为该商品该月全部正式唯一 `review_id`。先按 `parent_asin + taxonomy_id + review_id` 去重：同时存在 positive/negative 或原生 mixed 时记一次 mixed；mixed 不重复进入 positive/negative。

## 6. T011 improvement record

正式 corrected 文件一行一个 `parent_asin + taxonomy_id`：

```text
input_id,
parent_asin, product_title, product_category,
taxonomy_id, canonical_theme_name,
support_insight_count, support_review_count,
negative_insight_count, mixed_insight_count,
improvement_suggestion,
model_id, revision, prompt_version,
generation_mode, chunk_count,
input_tokens, output_tokens,
generation_status
```

`support_review_count` 使用唯一 review_id；`generation_mode` 为 `direct | chunked`。正式 corrected 文件含 7,734 条 success 记录。

## 7. Polarity override record

`t010-polarity-overrides-20260909-v1.json` 是版本化展示/API 修正：

```text
version, correction_count, policy,
corrections[] {
  parent_asin,
  taxonomy_id,
  from_sentiment,
  to_sentiment
}
```

当前 13 条 correction 均为 negative→positive。override 不改变冻结的 T009/T010 文件，只改变 effective sentiment 和 improvement 可见性。

## 8. API projection

`GoldInsightsRepository` 将 T010、T011 和 override 投影为：products、categories、product overview、positive/negative themes、theme detail/trend/reviews 和 product improvements。API 不暴露在线生成状态，也不启动离线作业。

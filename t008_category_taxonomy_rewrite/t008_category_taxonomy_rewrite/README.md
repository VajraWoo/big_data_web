# T008 category taxonomy candidate pipeline (rewrite)

This is a clean rewrite for the new T007 v2.1 output. It intentionally reuses the **method**
(MiniLM + Sentence-Transformers Fast Community Detection) rather than adapting the old,
product-level implementation line by line.

## What is frozen here

- Embedding model family: `all-MiniLM-L6-v2`
- Fast Community Detection
- default cosine threshold: `0.75`
- minimum: `10` distinct `review_id`
- only `target_scope=current_product` enters candidates by default
- grouping unit is `product_category`, not `parent_asin`

## What is NOT frozen here

- Final taxonomy names / IDs
- final merge/split decisions
- final positive/negative mixed-polarity semantics
- final ratio denominators
- final Gold publication schema

The output of `cluster_t008.py` is deliberately called **candidate clusters** and is marked
`needs_human_review`.

## Input expected

1. T007 final output:
   `t007_full_v2_1_1024_results.jsonl`

2. Canonical NLP input parquet:
   `data/gold/nlp-input-20260907-v2/review_inputs.parquet`

The parquet must contain:
- `parent_asin`
- `product_category`
and may contain `product_title`.

## Run on Windows PowerShell

From `D:\CS_Projects\big_data_web`:

```powershell
python .\t008_category_taxonomy_rewrite\prepare_t008_candidates.py `
  --t007 .\cloud\t007_full_v2_1_1024_results.jsonl `
  --metadata .\data\gold\nlp-input-20260907-v2\review_inputs.parquet `
  --output .\data\gold\t008-candidates-20260908-v1
```

Encode with MiniLM. `--device auto` prefers XPU, then CUDA, then CPU.

```powershell
python .\t008_category_taxonomy_rewrite\encode_t008.py `
  --input-dir .\data\gold\t008-candidates-20260908-v1 `
  --output .\data\gold\t008-embeddings-20260908-v1 `
  --model-path sentence-transformers/all-MiniLM-L6-v2 `
  --device auto
```

If your model is already cached/local and the machine has no network, point `--model-path`
at the local model directory and add `--local-files-only`.

Cluster:

```powershell
python .\t008_category_taxonomy_rewrite\cluster_t008.py `
  --input-dir .\data\gold\t008-candidates-20260908-v1 `
  --embedding-dir .\data\gold\t008-embeddings-20260908-v1 `
  --output .\data\gold\t008-clusters-20260908-v1 `
  --threshold 0.75 `
  --min-community-size 10
```

Export the candidate clusters for human review:

```powershell
python .\t008_category_taxonomy_rewrite\export_human_review.py `
  --clusters .\data\gold\t008-clusters-20260908-v1 `
  --output .\data\gold\t008-taxonomy-review-20260908-v1.csv
```

## Why polarity is separated by default

The current specs explicitly leave mixed-polarity semantics for later T008-T010 decisions.
Therefore the first candidate discovery run groups `positive`, `negative`, and `neutral`
separately. This avoids silently freezing a cross-polarity merge rule.

After seeing the first candidate clusters, `--ignore-polarity` can be tested deliberately,
but it should not be treated as the production rule without review.

## Candidate text

Default MiniLM text:

`topic_raw: evidence`

This gives short free-form T007 topics enough sentence context to disambiguate terms like
"noise", "installation", "fit", and "ice production". You can compare with `--text-mode topic`
later if cluster quality suggests evidence is adding too much surface variation.

## Recommended first run

Do **not** tune 0.75 immediately. Run the existing approved baseline first, inspect a small
set of categories, then decide whether a threshold change is justified by actual cluster
quality.

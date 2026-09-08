# T008 taxonomy consolidation

This package replaces the second-level FCD merge as the final taxonomy mechanism.

The first-level MiniLM + Fast Community Detection result remains intact:
~315k insights -> 4,992 high-precision local clusters.

The consolidation stage treats those first-level clusters as atomic units and creates
a category-level business taxonomy.

## 1. Build compact packets

```powershell
python .\t008_taxonomy_consolidation\build_taxonomy_packets.py `
  --input-dir .\data\gold\t008-clusters-20260908-v2 `
  --output .\data\gold\t008-taxonomy-packets-20260908-v1
```

This creates one JSON packet per product category plus `taxonomy_review_seed.csv`.

## 2. Generate a prompt for one category

Example:

```powershell
python .\t008_taxonomy_consolidation\make_taxonomy_prompt.py `
  --packet .\data\gold\t008-taxonomy-packets-20260908-v1\packets\cooktops.json `
  --output .\data\gold\t008-taxonomy-packets-20260908-v1\prompts\cooktops.txt
```

The prompt requires:
- every first-level cluster to be assigned exactly once;
- polarity not to define taxonomy;
- distinct analytical dimensions to remain separate;
- JSON-only output.

## 3. Validate and apply a taxonomy decision JSON

After an LLM or human produces a decision file:

```powershell
python .\t008_taxonomy_consolidation\validate_apply_taxonomy.py `
  --packet .\data\gold\t008-taxonomy-packets-20260908-v1\packets\cooktops.json `
  --decisions .\data\gold\t008-taxonomy-decisions\cooktops.json `
  --output .\data\gold\t008-taxonomy-final\cooktops
```

The validator rejects:
- missing first-level cluster IDs;
- duplicate assignments;
- invented IDs;
- empty theme names;
- category mismatches.

Only after validation does it materialize taxonomy IDs and the
`first_level_cluster_id -> taxonomy_id` mapping.

# T008 large-category taxonomy pipeline

Use this only for:
- Ice Makers
- Portable Washers
- Range Hoods

## Why this pipeline

The first-level MiniLM + FCD result is useful, but a single LLM request for 495-2342
clusters is too large. The category is therefore partitioned only for workload management.

Crucially:
- KMeans blocks are NOT taxonomy nodes.
- Every first-level cluster belongs to exactly one prompt block.
- Each block is consolidated locally.
- Local themes from all blocks are then globally consolidated once.
- Final validation expands the global decisions back to every original first-level cluster
  and verifies exact-once coverage.

This is what prevents duplicate themes caused by block boundaries.

## 1. Build semantic blocks

Example for Ice Makers:

```powershell
.\ml\xpu\.venv\Scripts\python.exe `
  .\pipelines\t008\large_categories\build_semantic_blocks.py `
  --packet .\data\gold\t008-taxonomy-packets-20260908-v1\packets\ice-makers.json `
  --output .\data\gold\t008-large-work\ice-makers `
  --model-path "D:\CS_Projects\big_data_web\data\models\minilm-local" `
  --device auto `
  --local-files-only `
  --target-block-size 100
```

## 2. Generate local prompts

```powershell
python .\pipelines\t008\large_categories\make_block_prompts.py `
  --block-dir .\data\gold\t008-large-work\ice-makers\blocks `
  --output .\data\gold\t008-large-work\ice-makers\prompts
```

Process each prompt with an LLM/human and save JSON decisions as:
`decisions/block-000.json`, `decisions/block-001.json`, ...

## 3. Validate local decisions

```powershell
python .\pipelines\t008\large_categories\validate_local_decisions.py `
  --block-dir .\data\gold\t008-large-work\ice-makers\blocks `
  --decision-dir .\data\gold\t008-large-work\ice-makers\decisions `
  --output .\data\gold\t008-large-work\ice-makers\local-validated
```

## 4. Generate global cross-block consolidation prompt

```powershell
python .\pipelines\t008\large_categories\make_global_prompt.py `
  --catalog .\data\gold\t008-large-work\ice-makers\local-validated\local-theme-catalog.json `
  --output .\data\gold\t008-large-work\ice-makers\global-prompt.txt
```

Process that prompt and save the JSON as:
`global-decision.json`

## 5. Finalize and validate exact-once mapping

```powershell
python .\pipelines\t008\large_categories\finalize_global_taxonomy.py `
  --catalog .\data\gold\t008-large-work\ice-makers\local-validated\local-theme-catalog.json `
  --decision .\data\gold\t008-large-work\ice-makers\global-decision.json `
  --output .\data\gold\t008-taxonomy-final\ice-makers
```

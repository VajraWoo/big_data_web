# T008 cluster audit export

Exports a compact CSV for semantic inspection of the second-level merge.

Per product category, the default sample includes:
- 10 largest merged taxonomy candidates
- 10 largest-review singleton candidates
- 5 reproducible random singleton candidates

Run from the project root:

```powershell
python .\t008_cluster_audit_export\export_t008_cluster_audit.py `
  --taxonomy .\data\gold\t008-second-level-20260908-v1\taxonomy-candidates.ndjson `
  --mapping .\data\gold\t008-second-level-20260908-v1\cluster-to-taxonomy.ndjson `
  --first-level-dir .\data\gold\t008-clusters-20260908-v2 `
  --output .\data\gold\t008-second-level-audit-20260908-v1.csv
```

The CSV preserves taxonomy-level information plus representative first-level labels, topics,
and center evidence for human review.

$ErrorActionPreference = 'Stop'

$candidateRoot = 'data/gold/theme-candidates-20260906-v2'
$embeddingRoot = 'data/gold/theme-embeddings-20260906-v2'
$clusterRoot = 'data/gold/theme-clusters-20260906-v4'
$finalRoot = 'data/gold/themes-final-20260906-v4'
$modelPath = 'C:/Users/31407/.cache/huggingface/hub/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/1110a243fdf4706b3f48f1d95db1a4f5529b4d41'

if (-not (Test-Path -LiteralPath "$candidateRoot/manifest.json")) {
    python -m pipelines.prepare_theme_candidates_job `
        --absa-root data/gold/absa-final-20260906-v1 `
        --nli-root data/gold/nli-final-20260906-v2 `
        --output $candidateRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
& ml/xpu/.venv/Scripts/python.exe ml/xpu/encode_theme_candidates.py `
    --input-dir $candidateRoot --output $embeddingRoot --model-path $modelPath `
    --batch-size 128 --max-length 256
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& ml/xpu/.venv/Scripts/python.exe ml/xpu/cluster_themes.py `
    --input-dir $candidateRoot --embedding-dir $embeddingRoot --output $clusterRoot `
    --threshold 0.75 --min-community-size 10 --community-batch-size 1024
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Test-Path -LiteralPath $finalRoot)) {
    python -m pipelines.finalize_themes_job --cluster-root $clusterRoot --output $finalRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$ErrorActionPreference = 'Stop'

$inputRoot = 'data/gold/product-attribution-input-20260906-v1'
$shardRoot = 'data/gold/product-attribution-xpu-20260906-v1'
$finalRoot = 'data/gold/qualified-negative-absa-20260906-v1'
$modelPath = 'C:/Users/31407/.cache/huggingface/hub/models--cross-encoder--nli-MiniLM2-L6-H768/snapshots/b95119ce93d3e065de6214e38cd4a97b0f2f2c6d'

if (-not (Test-Path -LiteralPath "$inputRoot/manifest.json")) {
    python -m pipelines.prepare_product_attribution_job `
        --absa-root data/gold/absa-final-20260906-v1 `
        --products data/gold/scope-filter-20260906-v3/selected_products.parquet `
        --output $inputRoot --shard-count 24
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
& ml/xpu/.venv/Scripts/python.exe ml/xpu/run_product_attribution.py `
    --input-dir $inputRoot --output $shardRoot --model-path $modelPath `
    --batch-size 32 --evidence-batch-size 256 --max-length 256 --stride 32
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Test-Path -LiteralPath $finalRoot)) {
    python -m pipelines.finalize_product_attribution_job `
        --input-root $inputRoot --shard-root $shardRoot `
        --absa-root data/gold/absa-final-20260906-v1 --output $finalRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

param([string]$Destination = 'data/models')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$lock = Get-Content -LiteralPath 'pipelines/language-model-lock.json' -Raw | ConvertFrom-Json
$model = $lock.fasttext_lid_176
$target = Join-Path $Destination $model.filename
$targetDirectory = Split-Path -Parent $target
New-Item -ItemType Directory -Force -Path $targetDirectory | Out-Null

if (Test-Path -LiteralPath $target) {
    $actualHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    $actualSize = (Get-Item -LiteralPath $target).Length
    if ($actualHash -eq $model.sha256 -and $actualSize -eq $model.bytes) {
        Write-Output "LANGUAGE_MODEL_READY=$target SHA256=$actualHash"
        return
    }
    throw "Existing language model failed integrity validation: $target"
}

$temporary = "$target.download"
try {
    & curl.exe -L --fail --retry 3 --output $temporary $model.url
    if ($LASTEXITCODE -ne 0) { throw "Language model download failed with exit code $LASTEXITCODE" }
    $actualHash = (Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash.ToLowerInvariant()
    $actualSize = (Get-Item -LiteralPath $temporary).Length
    if ($actualHash -ne $model.sha256 -or $actualSize -ne $model.bytes) {
        throw "Downloaded language model failed integrity validation"
    }
    Move-Item -LiteralPath $temporary -Destination $target
    Write-Output "LANGUAGE_MODEL_READY=$target SHA256=$actualHash"
} finally {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary }
}

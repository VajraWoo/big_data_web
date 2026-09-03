param(
    [ValidateSet('sample','full','fixture','replay')][string]$Mode = 'sample',
    [string]$RunId = '',
    [switch]$SkipStart,
    [string]$LeftRunId = '',
    [string]$RightRunId = '',
    [switch]$Subset
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    $env:PATH = 'C:\Users\31407\AppData\Local\Programs\DockerDesktop\resources\bin;' + $env:PATH
}
if (-not $RunId) { $RunId = 'silver-' + $Mode + '-' + (Get-Date -Format 'yyyyMMddTHHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8) }
if ($RunId -notmatch '^[A-Za-z0-9_-]+$') { throw 'RunId must be a plain batch identifier' }
if (Test-Path -LiteralPath (Join-Path 'data/silver' $RunId)) { throw 'Batch already exists; choose a new RunId' }
New-Item -ItemType Directory -Force data/silver/events,docs/runs/evidence | Out-Null
$composeArgs = @('compose','-f','infra/compose.yaml','-f','infra/compose.web.yaml','-f','infra/compose.silver.yaml','--profile','tools')
if (-not $SkipStart) {
    & docker @composeArgs up -d --no-build --wait --wait-timeout 120 spark-master spark-worker-1 spark-worker-2
    if ($LASTEXITCODE -ne 0) { throw 'Spark mount update/start failed' }
}
$submitArgs = @('--master','spark://spark-master:7077','--deploy-mode','client','--driver-memory','2g',
    '--executor-memory','3g','--conf','spark.driver.host=spark-driver','--conf','spark.driver.bindAddress=0.0.0.0',
    '--conf','spark.executor.cores=2','--conf','spark.cores.max=4',
    '--conf','spark.sql.shuffle.partitions=16','--conf','spark.sql.session.timeZone=UTC',
    '--conf','spark.eventLog.enabled=true','--conf','spark.eventLog.dir=file:///data/silver/events',
    '--conf','spark.eventLog.compress=false',
    '--py-files','/pipelines/cleaning.py,/pipelines/silver_job.py')
if ($Mode -eq 'fixture') {
    $submitArgs += '/pipelines/fixture_spark.py'
} elseif ($Mode -eq 'replay') {
    if ($LeftRunId -notmatch '^[A-Za-z0-9_-]+$' -or $RightRunId -notmatch '^[A-Za-z0-9_-]+$') { throw 'Replay requires two plain batch identifiers' }
    $submitArgs += @('/pipelines/replay_check.py','--left',"/data/silver/$LeftRunId",'--right',"/data/silver/$RightRunId",'--output',"/data/silver/$RunId.json")
    if ($Subset) { $submitArgs += '--subset' }
} else {
    $submitArgs += @('/pipelines/silver_job.py','--mode',$Mode,'--run-id',$RunId)
}
$logPath = "docs/runs/evidence/$RunId.log"
Write-Output "RUN_ID=$RunId LOG=$logPath"
$submission = @{
    run_id = $RunId
    powershell_version = $PSVersionTable.PSVersion.ToString()
    docker_arguments = $composeArgs + @('run','--rm','--no-deps','spark-driver') + $submitArgs
    file_sha256 = @{}
}
foreach ($sourcePath in @('infra/compose.yaml','infra/compose.web.yaml','infra/compose.silver.yaml','pipelines/run_silver.ps1','infra/spark/connector-jars.sha256')) {
    $submission.file_sha256[$sourcePath] = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash
}
$submission | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 "docs/runs/evidence/$RunId-submission.json"
# Spark logs on stderr. Windows PowerShell 5 must not turn ordinary WARN lines into a terminating error.
$savedErrorPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = 'Continue'
    & docker @composeArgs run --rm --no-deps spark-driver @submitArgs 2>&1 | Tee-Object -FilePath $logPath
    $runExit = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $savedErrorPreference
}
if ($runExit -ne 0) { throw "Silver batch failed (exit $runExit); see $logPath" }

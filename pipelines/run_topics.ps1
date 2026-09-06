param([string]$RunId=('themes-'+(Get-Date -Format 'yyyyMMddTHHmmss')))
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$dockerPath='C:\Users\31407\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe'
if (Get-Command docker -ErrorAction SilentlyContinue) { $dockerPath=(Get-Command docker).Source }
$sentiment=Get-ChildItem -LiteralPath 'data/gold' -Directory -Filter 'sentiment-*' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $sentiment) { throw 'No completed sentiment output found' }
$sentimentPath='/data/gold/'+$sentiment.Name+'/sentiment/reviews'
$composeArgs=@('compose','-f','infra/compose.yaml','-f','infra/compose.silver.yaml','--profile','tools')
& $dockerPath @composeArgs up -d --no-build --wait spark-master spark-worker-1 spark-worker-2
if ($LASTEXITCODE -ne 0) { throw 'Spark start failed' }
$driverName=$RunId+'-driver'
$ErrorActionPreference='Continue'
& $dockerPath @composeArgs run --rm --name $driverName --no-deps spark-driver --master spark://spark-master:7077 --deploy-mode client --driver-memory 3g --executor-memory 3g --conf "spark.driver.host=$driverName" --conf spark.driver.bindAddress=0.0.0.0 --conf spark.executor.cores=2 --conf spark.cores.max=4 /pipelines/topic_job.py --run-id $RunId --sentiment-path $sentimentPath 2>&1 | Tee-Object -FilePath "docs/runs/evidence/$RunId.log"
if ($LASTEXITCODE -ne 0) { throw "Theme generation failed: $RunId" }
Write-Output "THEME_RUN=$RunId"

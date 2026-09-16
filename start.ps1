[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendRoot = Join-Path $projectRoot "backend_generated"
$backendAppRoot = Join-Path $backendRoot "backend"
$frontendRoot = Join-Path $projectRoot "frontend_story_dashboard\frontend"
$pythonPath = Join-Path $backendRoot ".venv\Scripts\python.exe"
$requirementsPath = Join-Path $backendAppRoot "requirements.txt"
$runtimeDir = Join-Path $projectRoot ".tmp\runtime"
$goldRoot = Join-Path $projectRoot "data\gold"

$requiredGoldFiles = @(
    "t010-aggregation-20260908-v1-duckdb\products.parquet",
    "t010-aggregation-20260908-v1-duckdb\product_facets.parquet",
    "t010-aggregation-20260908-v1-duckdb\themes.parquet",
    "t010-aggregation-20260908-v1-duckdb\theme_timeseries.parquet",
    "t010-aggregation-20260908-v1-duckdb\theme_reviews.parquet",
    "t010-aggregation-20260908-v1-duckdb\batch.json",
    "t010-aggregation-20260908-v1-duckdb\validation.json",
    "t011-final-corrected-20260909-v1.ndjson",
    "t010-polarity-overrides-20260909-v1.json"
)

function Test-LocalPortInUse([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $client.Connect("127.0.0.1", $Port)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Stop-ProcessTree($Process) {
    if ($null -ne $Process -and -not $Process.HasExited) {
        & taskkill.exe /PID $Process.Id /T /F 2>$null | Out-Null
    }
}

foreach ($relativePath in $requiredGoldFiles) {
    $fullPath = Join-Path $goldRoot $relativePath
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        throw "Missing required Gold file: $fullPath"
    }
}

if (Test-LocalPortInUse 8000) {
    throw "Port 8000 is already in use. Stop the other process and retry."
}
if (Test-LocalPortInUse 5173) {
    throw "Port 5173 is already in use. Stop the other process and retry."
}

$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npm) {
    throw "npm.cmd was not found. Install Node.js 24.x first."
}

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    if ($SkipInstall) {
        throw "Backend virtual environment was not found: $pythonPath"
    }
    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if (-not $python) {
        throw "python.exe was not found. Install Python 3.12 first."
    }
    Write-Host "Creating the backend virtual environment..."
    & $python.Source -m venv (Join-Path $backendRoot ".venv")
}

if (-not $SkipInstall) {
    Write-Host "Installing backend dependencies..."
    & $pythonPath -m pip install -r $requirementsPath
    if (-not (Test-Path -LiteralPath (Join-Path $frontendRoot "node_modules") -PathType Container)) {
        Write-Host "Installing frontend dependencies..."
        & $npm.Source ci --prefix $frontendRoot
    }
}

New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
$backendOut = Join-Path $runtimeDir "backend.stdout.log"
$backendErr = Join-Path $runtimeDir "backend.stderr.log"
$frontendOut = Join-Path $runtimeDir "frontend.stdout.log"
$frontendErr = Join-Path $runtimeDir "frontend.stderr.log"

$backendProcess = $null
$frontendProcess = $null

try {
    $backendProcess = Start-Process -FilePath $pythonPath `
        -ArgumentList @("-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000") `
        -WorkingDirectory $backendRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $backendOut -RedirectStandardError $backendErr

    $frontendProcess = Start-Process -FilePath $npm.Source `
        -ArgumentList @("run", "dev") -WorkingDirectory $frontendRoot `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $frontendOut -RedirectStandardError $frontendErr

    $deadline = (Get-Date).AddSeconds(45)
    $backendReady = $false
    $frontendReady = $false
    while ((Get-Date) -lt $deadline) {
        if ($backendProcess.HasExited) {
            throw "Backend startup failed. See $backendErr"
        }
        if ($frontendProcess.HasExited) {
            throw "Frontend startup failed. See $frontendErr"
        }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health" -TimeoutSec 2
            $backendReady = $health.meta.is_gold -eq $true
        }
        catch {
            $backendReady = $false
        }
        try {
            $page = Invoke-WebRequest -Uri "http://127.0.0.1:5173" -TimeoutSec 2 -UseBasicParsing
            $frontendReady = $page.StatusCode -eq 200
        }
        catch {
            $frontendReady = $false
        }
        if ($backendReady -and $frontendReady) {
            break
        }
        Start-Sleep -Milliseconds 500
    }

    if (-not $backendReady -or -not $frontendReady) {
        throw "The system was not ready within 45 seconds. See logs in $runtimeDir"
    }

    Write-Host "System ready: http://127.0.0.1:5173"
    Write-Host "Press Ctrl+C to stop the frontend and backend."
    if (-not $NoBrowser) {
        Start-Process "http://127.0.0.1:5173"
    }

    while (-not $backendProcess.HasExited -and -not $frontendProcess.HasExited) {
        Start-Sleep -Seconds 1
    }
    throw "A service exited unexpectedly. See logs in $runtimeDir"
}
finally {
    Stop-ProcessTree $frontendProcess
    Stop-ProcessTree $backendProcess
}

param(
    [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$server = Join-Path $ProjectRoot "scripts\serve_web.py"
$logDir = Join-Path $ProjectRoot "logs"
$log = Join-Path $logDir "web.log"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python virtual environment not found: $python"
}
if (-not (Test-Path -LiteralPath $server)) {
    throw "Web server entry point not found: $server"
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Location -LiteralPath $ProjectRoot

# Keep this process attached to the task so Task Scheduler can restart it.
& $python -u $server *>> $log
exit $LASTEXITCODE

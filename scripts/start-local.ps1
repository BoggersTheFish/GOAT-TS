$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $root "docker\docker-compose.yml"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is not installed or not on PATH. Start Docker Desktop and verify 'docker --version' works."
}

Write-Host "Starting local TS services from $composeFile"
$composeOutput = & cmd.exe /d /c "docker compose -f ""$composeFile"" up -d 2>&1"
$exitCode = $LASTEXITCODE

if ($LASTEXITCODE -ne 0) {
    throw "docker compose failed. Review the output above for the failing service or image."
}

Write-Host ""
Write-Host "Expected local ports:"
Write-Host "  NebulaGraph graphd: 9669"
Write-Host "  NebulaGraph metad: 9559"
Write-Host "  NebulaGraph storaged: 9779"
Write-Host "  Redis: 6379"
Write-Host "  Spark UI: 8080"

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ComposeFile = Join-Path $RepoRoot "compose.postgres.yml"
$EnvFile = Join-Path $RepoRoot ".env.postgres.local"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI não encontrado."
}
if (-not (Test-Path $ComposeFile)) { throw "compose.postgres.yml não encontrado." }
if (-not (Test-Path $EnvFile)) {
    Write-Host "Nenhuma configuração PostgreSQL local encontrada; nada a parar."
    exit 0
}

Push-Location $RepoRoot
try {
    & docker compose --env-file $EnvFile -f $ComposeFile down
    if ($LASTEXITCODE -ne 0) { throw "docker compose down falhou." }
    Write-Host "PostgreSQL local parado."
    Write-Host "Volume rasai_postgres_data: PRESERVED"
    Write-Host ".env.postgres.local: PRESERVED"
}
finally {
    Pop-Location
}

[CmdletBinding()]
param(
    [switch]$ConfirmReset
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $ConfirmReset) {
    throw "RESET DESTRUTIVO recusado. Execute novamente com -ConfirmReset para remover o volume rasai_postgres_data."
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ComposeFile = Join-Path $RepoRoot "compose.postgres.yml"
$EnvFile = Join-Path $RepoRoot ".env.postgres.local"
$StartScript = Join-Path $PSScriptRoot "start.ps1"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker CLI não encontrado." }
if (-not (Test-Path $ComposeFile)) { throw "compose.postgres.yml não encontrado." }
if (-not (Test-Path $EnvFile)) { throw ".env.postgres.local não existe; não há ambiente local conhecido para resetar." }

Write-Warning "A operação removerá definitivamente os dados do PostgreSQL local no volume rasai_postgres_data."
Write-Host "O arquivo .env.postgres.local será preservado para manter usuário/senha/porta locais."

Push-Location $RepoRoot
try {
    & docker compose --env-file $EnvFile -f $ComposeFile down -v
    if ($LASTEXITCODE -ne 0) { throw "docker compose down -v falhou." }
}
finally {
    Pop-Location
}

& $StartScript
if ($LASTEXITCODE -ne 0) { throw "PostgreSQL foi removido, mas a reinicialização falhou." }
Write-Host "PostgreSQL local resetado e recriado com volume vazio."

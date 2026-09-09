[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ComposeFile = Join-Path $RepoRoot "compose.postgres.yml"
$EnvFile = Join-Path $RepoRoot ".env.postgres.local"

function Get-EnvValue([string]$Name) {
    foreach ($line in [System.IO.File]::ReadAllLines($EnvFile)) {
        if ($line.StartsWith("$Name=")) { return $line.Substring($Name.Length + 1) }
    }
    return $null
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Docker CLI não encontrado." }
if (-not (Test-Path $ComposeFile)) { throw "compose.postgres.yml não encontrado." }
if (-not (Test-Path $EnvFile)) { throw ".env.postgres.local não existe. Execute scripts/postgres/start.ps1 primeiro." }

$db = Get-EnvValue "POSTGRES_DB"
$user = Get-EnvValue "POSTGRES_USER"
$hostPort = Get-EnvValue "POSTGRES_HOST_PORT"
if ([string]::IsNullOrWhiteSpace($db) -or [string]::IsNullOrWhiteSpace($user)) {
    throw "POSTGRES_DB/POSTGRES_USER ausentes em .env.postgres.local"
}

Push-Location $RepoRoot
try {
    & docker compose --env-file $EnvFile -f $ComposeFile ps
    if ($LASTEXITCODE -ne 0) { throw "docker compose ps falhou." }

    $health = (& docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' rasai-postgres-dev 2>$null).Trim()
    Write-Host "Container health: $health"
    Write-Host "Endpoint local: 127.0.0.1:$hostPort"

    if ($health -ne "healthy") { throw "PostgreSQL local não está healthy." }

    & docker exec rasai-postgres-dev pg_isready -U $user -d $db
    if ($LASTEXITCODE -ne 0) { throw "pg_isready falhou." }

    $query = "SELECT version(); SELECT current_database(); SELECT current_user; SHOW server_encoding; SHOW timezone;"
    & docker exec rasai-postgres-dev psql -X -v ON_ERROR_STOP=1 -U $user -d $db -c $query
    if ($LASTEXITCODE -ne 0) { throw "Validação psql falhou." }

    $contract = (& docker exec rasai-postgres-dev psql -X -At -v ON_ERROR_STOP=1 -U $user -d $db -c "SELECT current_setting('server_encoding') || '|' || current_setting('TimeZone');").Trim()
    $parts = $contract.Split('|')
    if ($parts.Count -ne 2 -or $parts[0].ToUpperInvariant() -ne "UTF8" -or $parts[1].ToUpperInvariant() -notin @("UTC", "ETC/UTC")) {
        throw "Contrato PostgreSQL inválido: esperado UTF8 e UTC."
    }

    Write-Host "PostgreSQL server contract: PASS (UTF8 / UTC)"
    Write-Host "Nenhuma credencial foi exibida."
}
finally {
    Pop-Location
}

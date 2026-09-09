[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ComposeFile = Join-Path $RepoRoot "compose.postgres.yml"
$EnvFile = Join-Path $RepoRoot ".env.postgres.local"

function Assert-DockerReady {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker CLI não encontrado. Instale/inicie o Docker Desktop antes de iniciar o PostgreSQL local."
    }
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Desktop/daemon não está disponível. Inicie o Docker Desktop e tente novamente."
    }
}

function Test-LocalPortAvailable([int]$Port) {
    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        return $true
    }
    catch {
        return $false
    }
    finally {
        if ($null -ne $listener) {
            try { $listener.Stop() } catch { }
        }
    }
}

function New-StrongPassword {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    $value = [Convert]::ToBase64String($bytes)
    return $value.TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Write-LocalEnvironment {
    $port = if (Test-LocalPortAvailable 5432) { 5432 } elseif (Test-LocalPortAvailable 5433) { 5433 } else {
        throw "As portas locais 5432 e 5433 já estão em uso. Libere uma delas; o script não interrompe serviços existentes."
    }
    $password = New-StrongPassword
    $lines = @(
        "POSTGRES_DB=rasai_control_plane",
        "POSTGRES_USER=rasai_app",
        "POSTGRES_PASSWORD=$password",
        "POSTGRES_HOST_PORT=$port"
    )
    [System.IO.File]::WriteAllLines($EnvFile, $lines, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Configuração local criada em .env.postgres.local (senha não exibida)."
    Write-Host "Porta PostgreSQL local selecionada: $port"
}

function Get-EnvValue([string]$Name) {
    foreach ($line in [System.IO.File]::ReadAllLines($EnvFile)) {
        if ($line.StartsWith("$Name=")) { return $line.Substring($Name.Length + 1) }
    }
    return $null
}

Assert-DockerReady
if (-not (Test-Path $ComposeFile)) { throw "Arquivo compose.postgres.yml não encontrado em $RepoRoot" }
if (-not (Test-Path $EnvFile)) { Write-LocalEnvironment }

$hostPort = Get-EnvValue "POSTGRES_HOST_PORT"
if ([string]::IsNullOrWhiteSpace($hostPort)) { throw "POSTGRES_HOST_PORT ausente em .env.postgres.local" }

Push-Location $RepoRoot
try {
    & docker compose --env-file $EnvFile -f $ComposeFile up -d
    if ($LASTEXITCODE -ne 0) { throw "docker compose up falhou." }

    $healthy = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        $health = (& docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' rasai-postgres-dev 2>$null).Trim()
        if ($health -eq "healthy") { $healthy = $true; break }
        if ($health -eq "unhealthy" -or $health -eq "exited" -or $health -eq "dead") {
            throw "Container rasai-postgres-dev terminou em estado $health. Consulte 'docker logs rasai-postgres-dev'."
        }
        Start-Sleep -Seconds 2
    }
    if (-not $healthy) { throw "PostgreSQL iniciou, mas não ficou healthy dentro da janela de validação." }

    Write-Host "PostgreSQL local via Docker: READY"
    Write-Host "Container: rasai-postgres-dev"
    Write-Host "Endpoint: 127.0.0.1:$hostPort"
    Write-Host "Banco: rasai_control_plane"
    Write-Host "Usuário: rasai_app"
    Write-Host "Volume persistente: rasai_postgres_data"
    Write-Host "SQLite default do RASAI: PRESERVED"
}
finally {
    Pop-Location
}

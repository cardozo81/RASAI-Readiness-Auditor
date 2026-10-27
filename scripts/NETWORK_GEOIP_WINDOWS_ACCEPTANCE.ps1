# RASAi - teste humano focal de rede (#666)
# Sem -AuthorizeTrace: somente leitura, nenhuma sondagem é iniciada.
param(
    [Parameter(Mandatory=$true)][string]$Workspace,
    [Parameter(Mandatory=$true)][string]$AuditId,
    [string]$TargetHost,
    [switch]$AuthorizeTrace,
    [switch]$ReplayExisting,
    [string]$SeriesId,
    [string]$CityDB,
    [string]$AsnDB
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'Ambiente RASAi .venv nao encontrado. Execute abrir-rasai-console.cmd.'
}
if ($AuditId -notmatch '^[A-Za-z0-9_-]{1,128}$') {
    throw 'AuditId invalido.'
}
if ($AuthorizeTrace -and $ReplayExisting) {
    throw 'Nao e permitido autorizar nova sonda no mesmo passo do replay.'
}
if (($AuthorizeTrace -or $ReplayExisting) -and [string]::IsNullOrWhiteSpace($TargetHost)) {
    throw 'Informe -TargetHost para sonda ativa ou replay.'
}
if ($TargetHost -and ($TargetHost -match '[/:\\@\s]' -or $TargetHost -notmatch '^[A-Za-z0-9.-]+$')) {
    throw 'Use apenas hostname publico, sem esquema, porta ou URL.'
}
$Root = (Resolve-Path -LiteralPath $Workspace).Path
$Db = Join-Path $Root 'audit.db'
if (-not (Test-Path -LiteralPath $Db -PathType Leaf)) {
    throw 'audit.db nao encontrado.'
}
$Before = (Get-FileHash -LiteralPath $Db -Algorithm SHA256).Hash
$ArgsList = @('-m','rasai.network_acceptance','--workspace',$Root,'--audit-id',$AuditId)
if ($TargetHost) { $ArgsList += @('--host',$TargetHost) }
if ($SeriesId) { $ArgsList += @('--series-id',$SeriesId) }
if ($CityDB) { $ArgsList += @('--city-db',$CityDB) }
if ($AsnDB) { $ArgsList += @('--asn-db',$AsnDB) }
if ($AuthorizeTrace) {
    $ArgsList += @('--permit-exact-host',$TargetHost,'--authorize-active-network','--include-traceroute')
} elseif ($ReplayExisting) {
    $ArgsList += '--replay-existing'
}
$Raw = & $Python @ArgsList
$ExitCode = $LASTEXITCODE
$After = (Get-FileHash -LiteralPath $Db -Algorithm SHA256).Hash
if ($Before -ne $After) {
    throw 'FALHA CRITICA: audit.db alterado durante a avaliacao. Interrompa a homologacao.'
}
Write-Host ('audit.db inalterado (SHA256): ' + $After)
$Raw | Out-Host
if ($ExitCode -ne 0) {
    Write-Warning ('Avaliacao retornou codigo ' + $ExitCode + '. Analise o JSON acima.')
}
$NetworkHtml = Join-Path $Root 'report-catalog\network.html'
if (Test-Path -LiteralPath $NetworkHtml -PathType Leaf) {
    Write-Host ('Relatorio de rede: ' + $NetworkHtml)
} else {
    Write-Host 'network.html indisponivel nesta AUD.'
}

param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedSha,
    [Parameter(Mandatory=$true)][string]$AuditDir,
    [Parameter(Mandatory=$true)][string]$OutputDir,
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9/_-]{1,100}$')]
    [string]$Branch = 'feature/finalize-contextual-geo-timezone-690-692'
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repo
if ((git status --porcelain)) { throw 'Checkout precisa estar limpo.' }
if ((git branch --show-current) -ne $Branch) { throw 'Branch exclusiva necessária.' }
if ((git rev-parse HEAD) -ne $ExpectedSha) { throw 'HEAD divergente do commit homologável.' }
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Python local .venv indisponível; não instalar pela rede.' }
if (Test-Path -LiteralPath $OutputDir) { throw 'Saída deve ser nova.' }

$env:RASAI_TEMPORAL_AUD = $AuditDir
$env:RASAI_TEMPORAL_OUTPUT = $OutputDir
& $python -c @'
import os
from pathlib import Path
from rasai.document_advisory import _plain, _snapshots
root = _plain(Path(os.environ['RASAI_TEMPORAL_AUD']))
out = _plain(Path(os.environ['RASAI_TEMPORAL_OUTPUT']))
_snapshots(root)
if out.exists() or out.resolve().is_relative_to(root.resolve()) or root.resolve().is_relative_to(out.resolve()):
    raise ValueError('A saída deve ser nova e externa à AUD')
if any(p.name.startswith(('AUD-', 'RPR-', 'CONS-')) for p in (out, *out.parents)):
    raise ValueError('Caminho de histórico é proibido')
if out.parent.exists():
    raise ValueError('Utilize pai privado dedicado ainda inexistente')
out.parent.mkdir(mode=0o700, parents=True)
'@
if ($LASTEXITCODE -ne 0) { throw 'Pré-validação da AUD/destino falhou.' }
$privateParent = [IO.Path]::GetFullPath((Split-Path -Parent $OutputDir))
$operatorSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $privateParent '/inheritance:r' '/grant:r' "*$($operatorSid):(OI)(CI)F" | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'ACL privada não aplicada.' }
& $python -m rasai.temporal_acceptance --audit-dir $AuditDir --output-dir $OutputDir
if ($LASTEXITCODE -ne 0) { throw 'Falha na homologação de cópia privada; verificar temporal-acceptance.json' }

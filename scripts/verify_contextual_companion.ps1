param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedSha,
    [Parameter(Mandatory=$true)][string]$AuditDir,
    [Parameter(Mandatory=$true)][string]$OutputDir
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repo
if ((git status --porcelain)) { throw 'Checkout precisa estar limpo.' }
if ((git branch --show-current) -ne 'feature/contextual-geo-seo-evidence') { throw 'Branch exclusiva necessária.' }
git fetch origin refs/heads/feature/contextual-geo-seo-evidence
if ($LASTEXITCODE -ne 0) { throw 'Fetch falhou.' }
git merge --ff-only FETCH_HEAD
if ($LASTEXITCODE -ne 0) { throw 'Fast-forward recusado.' }
if ((git rev-parse HEAD) -ne $ExpectedSha) { throw 'HEAD diferente do SHA homologável.' }
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Python local preparado necessário; não instalar pela rede.' }
if (Test-Path -LiteralPath $OutputDir) { throw 'Saída deve ser nova.' }
# Validate every component before creating or ACLing a caller-provided parent.
$env:RASAI_CONTEXTUAL_AUD = $AuditDir
$env:RASAI_CONTEXTUAL_OUTPUT = $OutputDir
& $python -c @'
import os
from pathlib import Path
from rasai.document_advisory import _plain, _snapshots
root = _plain(Path(os.environ['RASAI_CONTEXTUAL_AUD']))
out = _plain(Path(os.environ['RASAI_CONTEXTUAL_OUTPUT']))
_snapshots(root)  # canonical physical identity, COMPLETED + accepted completion
if out.exists() or out.resolve().is_relative_to(root.resolve()) or root.resolve().is_relative_to(out.resolve()):
    raise ValueError('new external output required')
if any(p.name.startswith(('AUD-', 'RPR-', 'CONS-')) for p in (out, *out.parents)):
    raise ValueError('historical package output forbidden')
# Dedicated private parent only; never change an existing directory ACL.
if out.parent.exists():
    raise ValueError('choose a new dedicated private parent directory')
out.parent.mkdir(mode=0o700, parents=True)
'@
if ($LASTEXITCODE -ne 0) { throw 'Entrada, saída ou AUD terminal recusada.' }
$privateParent = [IO.Path]::GetFullPath((Split-Path -Parent $OutputDir))
$operatorSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls.exe $privateParent '/inheritance:r' '/grant:r' "*$($operatorSid):(OI)(CI)F" | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'ACL privada não aplicada.' }
& $python -c @'
import json, os
from pathlib import Path
from rasai.contextual_advisory import build_companion, summary_counts
from rasai.document_advisory import _inventory
from rasai.contextual_documents import digest
root, out = Path(os.environ['RASAI_CONTEXTUAL_AUD']), Path(os.environ['RASAI_CONTEXTUAL_OUTPUT'])
before = _inventory(root)
report = build_companion(root, out, ai='none')
assert before == _inventory(root) == report['source_inventory']
manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
assert all(digest((out / name).read_bytes()) == seal for name, seal in manifest['output_inventory'].items())
print(json.dumps(dict(source_files=len(before), **summary_counts(report))))
'@
if ($LASTEXITCODE -ne 0) { throw 'Homologação offline recusada; examinar apenas saída privada.' }

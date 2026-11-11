param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedSha,
    [Parameter(Mandatory=$true)][string]$AuditDir,
    [Parameter(Mandatory=$true)][string]$OutputDir,
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9/_-]{1,100}$')]
    [string]$Branch = 'feature/contextual-geo-seo-evidence',
    [switch]$RequireReverse
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repo
if ((git status --porcelain)) { throw 'Checkout precisa estar limpo.' }
if ((git branch --show-current) -ne $Branch) { throw 'Branch exclusiva necessária.' }
# Verification never changes Git refs or working files. Prepare this exact HEAD
# before invoking the acceptance script.
if ((git rev-parse HEAD) -ne $ExpectedSha) { throw 'HEAD diferente do SHA homologável.' }
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Python local preparado necessário; não instalar pela rede.' }
if (Test-Path -LiteralPath $OutputDir) { throw 'Saída deve ser nova.' }
# Validate every component before creating or ACLing a caller-provided parent.
$env:RASAI_CONTEXTUAL_AUD = $AuditDir
$env:RASAI_CONTEXTUAL_OUTPUT = $OutputDir
$env:RASAI_CONTEXTUAL_REQUIRE_REVERSE = if ($RequireReverse) { '1' } else { '0' }
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
proof = out.parent / 'acceptance.json'
proof.write_text(json.dumps(dict(status='N/D', source_inventory_before=before,
    human_review='N/D', temporal_21_pages='N/D'), indent=2), encoding='utf-8')
report = None
verified = False
try:
    report = build_companion(root, out, ai='none')
    assert report['network_requests'] == report['audit_writes'] == report['ai']['provider_calls'] == 0
    assert before == _inventory(root) == report['source_inventory']
    manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
    assert all(digest((out / name).read_bytes()) == seal for name, seal in manifest['output_inventory'].items())
    if os.environ.get('RASAI_CONTEXTUAL_REQUIRE_REVERSE') == '1':
        from rasai.contextual_faq_aria import CONTRACT as aria_contract
        from rasai.contextual_page_structure import CONTRACT as structure_contract
        from rasai.contextual_reverse_review import CONTRACT as reverse_contract
        assert report['faq_aria_v3']['contract'] == aria_contract
        assert report['content_structure_v3']['contract'] == structure_contract
        assert report['network_requests'] == report['audit_writes'] == report['ai']['provider_calls'] == 0
        assert (out / 'geo-content-review.html').is_file()
        assert manifest['faq_aria_contract'] == aria_contract
        assert manifest['page_structure_contract'] == structure_contract
        assert report['reverse_review']['contract'] == reverse_contract
        assert manifest['reverse_review_contract'] == reverse_contract
        assert all(task['validation'] and task['evidence_refs'] for task in report['reverse_review']['tasks'])
    verified = True
finally:
    after = _inventory(root)
    proof.write_text(json.dumps(dict(status='PASS' if verified and before == after else 'FAIL',
        source_inventory_before=before, source_inventory_after=after,
        presentation=report['presentation'] if report else None,
        captures_by_device={device: sum(c['device'] == device for c in report['captures'])
            for device in sorted({c['device'] for c in report['captures']})} if report else {},
        occurrences=sum(len(c['occurrences']) for c in report['captures']) if report else None,
        human_review='N/D', temporal_21_pages='N/D', non_temporal_21_pages='N/D',
        network_requests=report['network_requests'] if report else None,
        audit_writes=report['audit_writes'] if report else None,
        provider_calls=report['ai']['provider_calls'] if report else None), indent=2), encoding='utf-8')
assert before == after
print(json.dumps(dict(source_files=len(before), **summary_counts(report))))
'@
if ($LASTEXITCODE -ne 0) { throw 'Homologação offline recusada; examinar apenas saída privada.' }

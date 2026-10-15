#requires -Version 5.1
param(
    [string]$RepoRoot = 'C:\IA-PROJETOS\github\RASAI-Readiness-Auditor',
    [string]$AuditId = 'AUD-6BB4E5EA1F7D4E8A9E9518F17DEF69AB'
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $RepoRoot

# Never destroy uncommitted edits or silently rebase development work.
$dirty = @(git status --porcelain)
if ($LASTEXITCODE -ne 0) { throw 'git status failed.' }
if ($dirty.Count -gt 0) {
    $dirty | ForEach-Object { Write-Host $_ }
    throw 'Working tree is not clean. Preserve local edits before continuing.'
}
& git fetch origin
if ($LASTEXITCODE -ne 0) { throw 'git fetch failed.' }
& git switch main
if ($LASTEXITCODE -ne 0) { throw 'git switch main failed.' }
& git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) { throw 'git pull --ff-only failed.' }
$sha = (& git rev-parse HEAD).Trim()
Write-Host "MAIN_LOCAL: $sha"

$python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$rasai = Join-Path $RepoRoot '.venv\Scripts\rasai.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Python venv missing: run .\abrir-rasai-console.cmd once, close it, then retry.'
}
& $python -m pip install -e .
if ($LASTEXITCODE -ne 0) { throw 'Python editable installation failed.' }
if (-not (Test-Path -LiteralPath $rasai)) { throw 'rasai.exe missing after installation.' }

$source = Join-Path (Join-Path $RepoRoot 'audits') $AuditId
if (-not (Test-Path -LiteralPath (Join-Path $source 'audit.db') -PathType Leaf)) {
    throw "Missing source audit.db: $source"
}
$guid = [guid]::NewGuid().ToString('N').Substring(0, 8)
$outputRoot = Join-Path $env:TEMP "RASAI-REPORT-141-$guid"
Write-Host "OUTPUT_ROOT: $outputRoot"
& $rasai rematerialize-report --audit-dir $source --output-root $outputRoot
if ($LASTEXITCODE -ne 0) { throw 'Canonical rematerialization failed; do not run an AUD/RPR.' }
$destination = Join-Path $outputRoot $AuditId
$report = Join-Path $destination 'report-catalog'
if (-not (Test-Path -LiteralPath (Join-Path $report 'manifest.json'))) {
    throw 'No manifest in newly materialized report.'
}

# ASCII-only embedded Python avoids the PowerShell 5.1 UTF-8-without-BOM issue.
$validator = Join-Path $outputRoot 'validate-report-141.py'
@'
import json, re, sys
from pathlib import Path

source = Path(sys.argv[1])
generated = Path(sys.argv[2])
old = source / "report-catalog"
new = generated / "report-catalog"
before = json.loads((old / "manifest.json").read_text(encoding="utf-8"))
after = json.loads((new / "manifest.json").read_text(encoding="utf-8"))
assert after.get("freshness") == "PRELIMINARY", ("publication_state", after.get("freshness"))
a = before.get("audit_snapshot") or {}
b = after.get("audit_snapshot") or {}
assert a.get("source_logical_sha256") == b.get("source_logical_sha256"), "audit source changed"
rows = {}
for name in ("cat-01.html", "cat-04.html", "cat-07.html", "cat-09.html", "index.html"):
    old_html = (old / name).read_text(encoding="utf-8")
    new_html = (new / name).read_text(encoding="utf-8")
    old_n = len(re.findall(r"<tr\b", old_html, flags=re.I))
    new_n = len(re.findall(r"<tr\b", new_html, flags=re.I))
    rows[name] = {"original": old_n, "regenerated": new_n}
    # This audit is expected to retain substantive source-owned sections.
    assert new_n >= int(old_n * 0.85), (name, "substantive loss", old_n, new_n)
cat = (new / "cat-10.html").read_text(encoding="utf-8")
consent = "N\u00e3o observado"
generic = "Condi\u00e7\u00e3o t\u00e9cnica n\u00e3o catalogada"
assert cat.count(consent) >= 79, ("consent count", cat.count(consent))
assert cat.count("Tipo de plataforma") >= 8, "platform types absent"
assert cat.count(generic) <= 1, ("CAT-10 fallback", cat.count(generic))
for enum in ("NOT_OBSERVED", "GOOGLE_TAG_MANAGER", "GOOGLE_ANALYTICS", "TEALIUM"):
    assert enum not in cat, ("raw CAT-10 enum leaked", enum)
summary = {
    "audit_id": source.name, "freshness": after["freshness"], "catalog_rows": rows,
    "cat10_consent_readable": cat.count(consent),
    "cat10_platform_readable": cat.count("Tipo de plataforma"),
    "cat10_fallback_remaining": cat.count(generic),
    "old_source_logical_hash": a.get("source_logical_sha256"),
    "new_source_logical_hash": b.get("source_logical_sha256"),
}
print(json.dumps(summary, ensure_ascii=True, indent=2))
(generated.parent / "SMOKE_141_RESULT.json").write_text(
    json.dumps(summary, ensure_ascii=True, indent=2), encoding="ascii"
)
print("SMOKE_141_PARITY_OK")
'@ | Set-Content -LiteralPath $validator -Encoding ASCII
& $python $validator $source $destination
if ($LASTEXITCODE -ne 0) {
    Write-Host "Keep original and generated workspaces; use: $outputRoot"
    throw 'Real HTML parity failed. Do not approve #141 yet.'
}
$zip = Join-Path $outputRoot "RASAI-REPORT-141-$AuditId.zip"
Compress-Archive -Path (Join-Path $report '*') -DestinationPath $zip -Force
if (-not (Test-Path -LiteralPath $zip)) { throw 'Smoke archive missing.' }
Write-Host "SMOKE_141_PACKAGE: $zip"
Write-Host "SMOKE_141_REPORT: $(Join-Path $report 'index.html')"
Write-Host 'SMOKE_141_REPORT_READY: manually review CAT-01, CAT-10 and main index; send ZIP.'
Start-Process (Join-Path $report 'cat-01.html')
Start-Process (Join-Path $report 'cat-10.html')

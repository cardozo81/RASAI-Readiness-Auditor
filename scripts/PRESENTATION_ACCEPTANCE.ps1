param(
    [Parameter(Mandatory=$true)][string]$ExpectedSha,
    [Parameter(Mandatory=$true)][string]$AuditPath,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [string]$ExpectedDatabaseSha256 = '6a334d3bae292c987d25e08803f7fb4221d0a19a455db60e667c6b02bae2419d',
    [switch]$UpdateFastForward
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot
function Git-Value([string[]]$GitArgs) {
    $value = & git @GitArgs
    if ($LASTEXITCODE -ne 0) { throw 'Git validation failed.' }
    return (($value | Out-String).Trim())
}
if ((Git-Value @('remote','get-url','origin')) -ne 'https://github.com/cardozo81/RASAI-Readiness-Auditor.git') { throw 'Unexpected repository.' }
if ((Git-Value @('branch','--show-current')) -ne 'fix/partial-aud-presentation-independent-715') { throw 'Unexpected branch.' }
if (Git-Value @('status','--porcelain')) { throw 'Clean checkout required.' }
if ($ExpectedSha -notmatch '^[a-f0-9]{40}$') { throw 'Full exact commit SHA required.' }
if ($UpdateFastForward) {
    & git fetch origin fix/partial-aud-presentation-independent-715
    if ($LASTEXITCODE -ne 0) { throw 'Fetch failed.' }
    if ((Git-Value @('rev-parse','origin/fix/partial-aud-presentation-independent-715')) -ne $ExpectedSha) { throw 'Remote SHA differs from expected commit.' }
    & git merge --ff-only origin/fix/partial-aud-presentation-independent-715
    if ($LASTEXITCODE -ne 0) { throw 'Fast-forward failed.' }
}
if ((Git-Value @('rev-parse','HEAD')) -ne $ExpectedSha) { throw 'HEAD differs from expected commit.' }
$taskPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Existing Python 3.13 virtual environment required.' }
& $taskPython -m pytest -q tests/report_presentation tests/test_console_navigation.py tests/test_report_rematerialization.py
if ($LASTEXITCODE -ne 0) { throw 'Focused regression failed; no audit copy generated.' }
if (Git-Value @('status','--porcelain')) { throw 'Checkout changed during tests.' }
& $taskPython (Join-Path $PSScriptRoot 'presentation_acceptance.py') --audit $AuditPath --output $OutputPath --expected-db-sha256 $ExpectedDatabaseSha256 --browser
$acceptanceCode = $LASTEXITCODE
if ($acceptanceCode -ne 0) { throw "Acceptance incomplete or failed (exit $acceptanceCode). See confidential local artifacts." }
Write-Output "PASS_TECHNICAL_ACCEPTANCE_SHA=$ExpectedSha"
Write-Output 'HUMAN_ACCEPTANCE=PENDING'

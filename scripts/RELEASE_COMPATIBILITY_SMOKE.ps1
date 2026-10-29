param(
    [string]$Repository = (Split-Path -Parent $PSScriptRoot),
    [string]$Candidate = 'HEAD',
    [string]$Baseline = '4e9a3026ec0bbf6f46a4f30f3659fc2ab5a02a08',
    [string]$Python = 'python'
)

# Only committed sources are copied. No operator configuration or AUD is read.
$ErrorActionPreference = 'Stop'
$root = Join-Path ([IO.Path]::GetTempPath()) ('rasai-release-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root | Out-Null
$results = [System.Collections.Generic.List[object]]::new()
$exitCode = 0
$originalLocation = Get-Location
$originalBrowsersPath = $env:PLAYWRIGHT_BROWSERS_PATH

function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program exited with $LASTEXITCODE" }
}

function Get-VenvPython([string]$Directory) {
    if ($env:OS -eq 'Windows_NT') { return (Join-Path $Directory 'Scripts/python.exe') }
    return (Join-Path $Directory 'bin/python')
}

Start-Transcript -Path (Join-Path $root 'transcript.txt') | Out-Null
try {
    $candidateSha = (& git -C $Repository rev-parse --verify "$Candidate^{commit}").Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Candidate commit unavailable' }
    $baselineSha = (& git -C $Repository rev-parse --verify "$Baseline^{commit}").Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Baseline commit unavailable' }
    Invoke-Checked $Python @('-c', 'import sys; assert sys.version_info[:2] == (3,13), sys.version')
    foreach ($item in @(@('candidate', $candidateSha), @('baseline', $baselineSha))) {
        $name = $item[0]
        $sha = $item[1]
        $source = Join-Path $root $name
        $archive = Join-Path $root ($name + '.zip')
        Invoke-Checked 'git' @('-C', $Repository, 'archive', '--format=zip', "--output=$archive", $sha)
        Expand-Archive -LiteralPath $archive -DestinationPath $source
        $environment = Join-Path $root ($name + '-venv')
        Invoke-Checked $Python @('-m', 'venv', $environment)
        $runtime = Get-VenvPython $environment
        Set-Location $source
        $package = '.'
        if ($name -eq 'candidate') { $package = '.[attestation,geoip]' }
        Invoke-Checked $runtime @('-m', 'pip', 'install', '-e', $package, 'pytest')
        Invoke-Checked $runtime @('-m', 'pip', 'check')
        # Check each installed runtime against the manifest of its archived commit.
        $versionCheck = 'import rasai; import importlib.metadata as m; import tomllib; from pathlib import Path; expected=tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]; installed=m.version("rasai-readiness-auditor"); assert installed == expected, f"installed={installed} manifest={expected}"; assert rasai.__version__ == expected, f"namespace={rasai.__version__} manifest={expected}"; print("PACKAGE_VERSION_PASS", expected)'
        Invoke-Checked $runtime @('-c', $versionCheck)
        $cli = Join-Path (Split-Path $runtime) 'rasai'
        if ($env:OS -eq 'Windows_NT') { $cli += '.exe' }
        Invoke-Checked $cli @('--version')
        Invoke-Checked $cli @('audit', '--help')
        if ($name -eq 'candidate') {
            $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $root 'browsers'
            Invoke-Checked $runtime @('-m', 'playwright', 'install', 'chromium')
            Invoke-Checked $runtime @('-c', 'from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(); page=b.new_page(); page.set_content("<title>RASAi offline smoke</title>"); assert page.title()=="RASAi offline smoke"; b.close(); p.stop(); print("CHROMIUM_OFFLINE_PASS")')
            Invoke-Checked $runtime @('-m', 'pytest', '-q', 'tests/test_rpr_offline_acceptance.py', 'tests/test_runtime_contract_compatibility.py', 'tests/test_consolidation_cons5.py', 'tests/test_audit_cost_explain.py')
            $sentinel = Join-Path $root 'preserved-fixture.txt'
            Set-Content -LiteralPath $sentinel -Value 'Synthetic preservation marker; not historical AUD evidence.'
            $before = (Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash
        }
        $results.Add(@{ gate = "INSTALL_$name"; state = 'PASS'; sha = $sha; archive_sha256 = (Get-FileHash $archive -Algorithm SHA256).Hash })
        Invoke-Checked $runtime @('-m', 'pip', 'freeze')
    }
    $after = (Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash
    if ($before -ne $after) { throw 'Synthetic preservation marker changed' }
    $results.Add(@{ gate = 'ROLLBACK_ISOLATED_RUNTIME'; state = 'PASS'; before = $before; after = $after; limitation = 'Two separate runtimes; no historical AUD opened or downgraded.' })
    $results.Add(@{ gate = 'HISTORICAL_ARTIFACT_COMPATIBILITY'; state = 'NOT_VERIFIABLE'; limitation = 'Operator AUD databases and historical pre-operation hashes not supplied.' })
    $results.Add(@{ gate = 'OPTIONAL_INTEGRATIONS'; state = 'NOT_VERIFIABLE'; limitation = 'Web, PostgreSQL and Copilot extras and external credentials are outside this offline installation smoke.' })
} catch {
    $exitCode = 1
    $results.Add(@{ gate = 'SMOKE'; state = 'FAIL'; error = $_.Exception.Message })
    Write-Host ('FAIL: ' + $_.Exception.Message)
} finally {
    Set-Location $originalLocation
    $env:PLAYWRIGHT_BROWSERS_PATH = $originalBrowsersPath
    $results | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $root 'results.json') -Encoding utf8
    Write-Host "Evidence preserved at: $root"
    if ($env:GITHUB_OUTPUT) { "evidence=$root" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8 }
    Stop-Transcript | Out-Null
}
exit $exitCode

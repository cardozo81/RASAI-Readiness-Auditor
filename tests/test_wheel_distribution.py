"""Exercise the installed wheel outside the checkout, including its static data."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ("site.css", "app.js", "thresholds.json", "coverage-map.json")

# Runs with -I in a fresh, non-editable environment: no checkout/test imports.
INSTALLED_PROBE = r'''
import hashlib, importlib.metadata, json, sqlite3, sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
root, expected, version, receipt = Path(sys.argv[1]), json.loads(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
result = {'network_attempts': [], 'provider_calls': 0, 'resources': {}}
rendering = True
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def network_guard(event, args):
    if rendering and event in {'socket.connect', 'socket.getaddrinfo', 'urllib.Request'}:
        result['network_attempts'].append(event)
        raise AssertionError('External transport forbidden in report generation')
sys.addaudithook(network_guard)
try:
    import rasai
    installed = Path(rasai.__file__).resolve()
    assert installed.is_relative_to(Path(sys.prefix).resolve()), installed
    assert rasai.__version__ == importlib.metadata.version('rasai-readiness-auditor') == version
    result.update(version=version, package=str(installed), prefix=sys.prefix, cwd=str(Path.cwd()), isolated=sys.flags.isolated)
    from rasai import ai_canonical_orchestration
    def forbidden_provider(*args, **kwargs):
        result['provider_calls'] += 1
        raise AssertionError('LLM invocation forbidden in report generation')
    ai_canonical_orchestration.run_ai_need = forbidden_provider
    from rasai.parallel_report import generator
    for name in expected:
        path = Path(generator.__file__).parent / 'assets' / name
        result['resources'][name] = {'path': str(path), 'present': path.is_file(), 'sha256': sha(path) if path.is_file() else None}
    root.mkdir()
    with sqlite3.connect(root / 'audit.db') as db:
        db.executescript("""
        CREATE TABLE audits(audit_id TEXT PRIMARY KEY, status TEXT, completion_status TEXT, auditor_version TEXT);
        INSERT INTO audits VALUES('AUD-SYNTHETIC','COMPLETED','COMPLETE','historical-fixture');
        CREATE TABLE scores(score_id TEXT PRIMARY KEY, value REAL, dimension TEXT);
        INSERT INTO scores VALUES('zero',0,'DISCOVERY_ACCESS'),('unknown',NULL,'INDEXABILITY');
        CREATE TABLE evidence(evidence_id TEXT PRIMARY KEY,artifact_reference TEXT,observed_value TEXT);
        INSERT INTO evidence VALUES('ev-1','artifacts/page.html','Texto observado');
        CREATE TABLE findings(finding_id TEXT PRIMARY KEY,evidence_ids TEXT,title TEXT);
        INSERT INTO findings VALUES('finding-1','["ev-1"]','Achado sintético');
        CREATE TABLE directed_analysis_actions(action_id TEXT PRIMARY KEY,source_id TEXT,title TEXT,validation_steps_json TEXT);
        INSERT INTO directed_analysis_actions VALUES('action-1','finding-1','Revisar texto','["Revisar"]');
        CREATE TABLE ai_provider_attempts(attempt_id TEXT PRIMARY KEY,estimated_cost REAL,observed_cost REAL,cost_currency TEXT);
        INSERT INTO ai_provider_attempts VALUES('attempt-1',0.1,0,'USD');
        CREATE TABLE content_remediation_attempts(attempt_id TEXT PRIMARY KEY,estimated_cost REAL,cost_currency TEXT);
        INSERT INTO content_remediation_attempts VALUES('attempt-2',0.2,'USD');
        CREATE TABLE perplexity_search_runs(run_id TEXT PRIMARY KEY,attempt_id TEXT,estimated_cost REAL);
        INSERT INTO perplexity_search_runs VALUES('search-1','attempt-1',0.1);
        """)
        db.commit()
        snapshot = root / 'report-catalog' / 'integrity' / 'audit-snapshot.db'
        snapshot.parent.mkdir(parents=True)
        with sqlite3.connect(snapshot) as copy:
            db.backup(copy)
    (root / 'artifacts').mkdir()
    (root / 'artifacts/page.html').write_text('<p>Texto observado</p>', encoding='utf-8')
    from rasai.parallel_report.artifact_reader import inventory
    before = inventory(root)
    output = generator.generate(root)
    assert inventory(root) == before and generator.generate(root) == output
    manifest = json.loads((output / '_geracao.json').read_text(encoding='utf-8'))
    assert manifest['integrity'] == 'PASS' and manifest['page_count'] == 11
    assert manifest['external_requests'] == manifest['ai_calls'] == manifest['source_writes'] == 0
    assert manifest['score_recomputed'] is False
    assert manifest['source_tree_digest_before'] == manifest['source_tree_digest_after']
    for name, value in manifest['sha256_per_file'].items():
        assert sha(output / name) == value, name
    for name, value in expected.items():
        assert result['resources'][name]['sha256'] == value, name
    assert 'N/D' in (output / 'indices.html').read_text(encoding='utf-8')
    class Links(HTMLParser):
        def __init__(self):
            super().__init__(); self.ids=set(); self.refs=[]; self.navigation=0; self.in_navigation=False
        def handle_starttag(self, tag, attrs):
            attrs=dict(attrs)
            if 'id' in attrs: self.ids.add(attrs['id'])
            if tag=='nav' and attrs.get('aria-label')=='Páginas': self.in_navigation=True
            if tag=='a' and self.in_navigation: self.navigation+=1
            for field in ('href','src'):
                if field in attrs: self.refs.append(attrs[field])
        def handle_endtag(self, tag):
            if tag=='nav': self.in_navigation=False
    pages={}
    for file in output.glob('*.html'):
        parser=Links(); parser.feed(file.read_text(encoding='utf-8')); pages[file.resolve()]=parser
        assert parser.navigation==11, file.name
    assert len(pages)==11
    local_links=0
    for file, parser in pages.items():
        for ref in parser.refs:
            url=urlsplit(ref)
            assert not url.scheme and not url.netloc, ref
            target=(file.parent/unquote(url.path)).resolve() if url.path else file
            assert target.is_relative_to(root.resolve()) and target.exists(), ref
            if url.fragment and target.suffix=='.html': assert unquote(url.fragment) in pages[target].ids, ref
            local_links+=1
    # Playwright may use local IPC; browser HTTP(S) is denied separately below.
    rendering = False
    from playwright.sync_api import sync_playwright
    requests, errors, failures, browser_cases = [], [], [], []
    with sync_playwright() as pw:
        assert Path(pw.chromium.executable_path).exists(), 'Existing Chromium required for distribution gate'
        browser=pw.chromium.launch()
        context=browser.new_context(offline=True)
        context.route('**/*',lambda route: route.abort() if route.request.url.startswith(('http:','https:')) else route.continue_())
        page=context.new_page()
        page.on('request',lambda r: requests.append(r.url) if r.url.startswith(('http:','https:')) else None)
        page.on('pageerror',lambda error: errors.append(str(error)))
        page.on('requestfailed',lambda r: failures.append(r.url))
        for width in (1440,390):
            page.set_viewport_size({'width':width,'height':1080})
            for name in ('index','extracao','rede','ia-custos'):
                page.goto((output/(name+'.html')).as_uri())
                assert page.locator('nav[aria-label="Páginas"] a').count()==11
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.locator('#expand').click()
                assert page.locator('details:not([open])').count()==0
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.locator('#theme').click()
                assert page.locator('body.dark').count()==1
                page.locator('#theme').click()
                browser_cases.append({'page':name,'width':width})
        browser.close()
    assert not requests and not errors and not failures
    assert not result['network_attempts'] and result['provider_calls']==0 and inventory(root)==before
    result.update(status='PASS', output=str(output), local_links=local_links,
        generated_files=len(manifest['generated_files']), source_inventory=before,
        browser_cases=browser_cases, http_requests=requests, js_errors=errors, resource_failures=failures)
except BaseException as exc:
    result.update(status='FAIL', error=type(exc).__name__+': '+str(exc))
    raise
finally:
    receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
'''


def test_noneditable_wheel_generates_offline_report(tmp_path):
    source = tmp_path / "build-source"
    source.mkdir()
    shutil.copy2(ROOT / "pyproject.toml", source / "pyproject.toml")
    shutil.copytree(ROOT / "src", source / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"))
    env = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME"):
        env.pop(name, None)
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    def run(args):
        completed = subprocess.run([str(arg) for arg in args], cwd=tmp_path, env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        assert completed.returncode == 0, completed.stdout + completed.stderr
    dist = tmp_path / "dist"
    run([sys.executable, "-I", "-m", "pip", "wheel", "--no-deps", "--wheel-dir", dist, source])
    wheel, = dist.glob("*.whl")
    expected = {name: hashlib.sha256((ROOT / "src/rasai/parallel_report/assets" / name).read_bytes()).hexdigest() for name in ASSETS}
    with ZipFile(wheel) as archive:
        for name, digest in expected.items():
            assert hashlib.sha256(archive.read("rasai/parallel_report/assets/" + name)).hexdigest() == digest
        for resource in (ROOT / "src/rasai/config").glob("*"):
            if resource.suffix in {".ini", ".toml"}:
                assert archive.read("rasai/config/" + resource.name) == resource.read_bytes()
    environment = tmp_path / "installed-runtime"
    run([sys.executable, "-I", "-m", "venv", environment])
    runtime = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    # Match the browser driver whose Chromium was prepared by local tooling/CI.
    driver = "playwright==" + importlib.metadata.version("playwright")
    run([runtime, "-I", "-m", "pip", "install", wheel, driver])
    run([runtime, "-I", "-m", "pip", "check"])
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    receipt = tmp_path / "installed-report.json"
    run([runtime, "-I", "-c", INSTALLED_PROBE, tmp_path / "AUD-SYNTHETIC", json.dumps(expected), version, receipt])
    result = json.loads(receipt.read_text(encoding="utf-8"))
    assert result["status"] == "PASS" and result["isolated"] == 1

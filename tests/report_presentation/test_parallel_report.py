import json
from pathlib import Path
import socket
import sqlite3
from html.parser import HTMLParser

import pytest

from rasai.parallel_report.artifact_reader import confined, inventory, digest
from rasai.parallel_report.cost_reconciliation import reconcile
from rasai.parallel_report.coverage import state, display
from rasai.parallel_report.crossrefs import link_records
from rasai.parallel_report.evidence_index import locate, counts
from rasai.parallel_report.generator import generate
from rasai.parallel_report.read_model import build
from rasai.parallel_report.sanitization import sanitize
from rasai.parallel_report.sqlite_reader import connect, read_database
from rasai.parallel_report.thresholds import load


def fixture(root, complete=True):
    root.mkdir()
    db = sqlite3.connect(root / 'audit.db')
    db.executescript('''
    CREATE TABLE audits(audit_id TEXT PRIMARY KEY, status TEXT);
    INSERT INTO audits VALUES('AUD-SYNTHETIC','COMPLETE');
    CREATE TABLE scores(score_id TEXT PRIMARY KEY, value REAL, dimension TEXT);
    INSERT INTO scores VALUES('score-0',0,'DISCOVERY_ACCESS');
    INSERT INTO scores VALUES('score-null',NULL,'INDEXABILITY');
    ''')
    if complete:
        db.executescript('''
        CREATE TABLE evidence(evidence_id TEXT PRIMARY KEY,artifact_reference TEXT,observed_value TEXT);
        INSERT INTO evidence VALUES('ev-1','artifacts/page.html','<script>alert(1)</script>');
        CREATE TABLE findings(finding_id TEXT PRIMARY KEY,evidence_ids TEXT,title TEXT);
        INSERT INTO findings VALUES('finding-1','["ev-1"]','Teste literal');
        CREATE TABLE directed_analysis_actions(action_id TEXT PRIMARY KEY,source_id TEXT,title TEXT,validation_steps_json TEXT);
        INSERT INTO directed_analysis_actions VALUES('action-1','finding-1','Corrigir título','["Revisar título"]');
        CREATE TABLE page_snapshots(snapshot_id TEXT PRIMARY KEY,rendered_artifact_ref TEXT);
        INSERT INTO page_snapshots VALUES('snapshot-1','artifacts/page.html');
        CREATE TABLE ai_provider_attempts(attempt_id TEXT PRIMARY KEY,estimated_cost REAL,observed_cost REAL,cost_currency TEXT);
        INSERT INTO ai_provider_attempts VALUES('attempt-1',0.1,0,'USD');
        CREATE TABLE content_remediation_attempts(attempt_id TEXT PRIMARY KEY,estimated_cost REAL,cost_currency TEXT);
        INSERT INTO content_remediation_attempts VALUES('attempt-2',0.2,'USD');
        CREATE TABLE perplexity_search_runs(run_id TEXT PRIMARY KEY,attempt_id TEXT,estimated_cost REAL);
        INSERT INTO perplexity_search_runs VALUES('search-1','attempt-1',0.1);
        CREATE TABLE private_payload(id TEXT PRIMARY KEY,payload TEXT);
        INSERT INTO private_payload VALUES('secret-1','{"api_key":"PRIVATE_VALUE", "authorization":"Bearer HIDDEN_VALUE"}');
        ''')
    db.commit()
    catalog = root / 'report-catalog' / 'integrity'
    catalog.mkdir(parents=True)
    snapshot = sqlite3.connect(catalog / 'audit-snapshot.db')
    db.backup(snapshot)
    snapshot.close()
    db.close()
    (root / 'artifacts').mkdir()
    (root / 'artifacts' / 'page.html').write_text('<p>Olá mundo</p><a>link</a><img><script>alert(1)</script>', encoding='utf-8')
    return root


def test_read_only(tmp_path):
    root = fixture(tmp_path / 'audit')
    before = inventory(root)
    with connect(root / 'audit.db') as db:
        assert db.execute('PRAGMA query_only').fetchone()[0] == 1
        for sql in ('DELETE FROM scores', 'CREATE TABLE forbidden(x)', 'PRAGMA user_version=5'):
            with pytest.raises(sqlite3.OperationalError):
                db.execute(sql)
    assert inventory(root) == before
    assert not list(root.glob('audit.db-*'))


def test_active_wal_rejected(tmp_path):
    root = fixture(tmp_path / 'audit')
    (root / 'audit.db-wal').touch()
    with pytest.raises(ValueError, match='sidecar'):
        generate(root)
    assert not (root / 'report-presentation').exists()


@pytest.mark.parametrize('value,expected', [(0, '0'), (None, 'N/D')])
def test_zero_null(value, expected):
    assert display(value) == expected


def test_states():
    assert state('NOT_REQUESTED') != state('FAILED')
    assert state('NOT_APPLICABLE') != state('SUCCESS')
    assert state(None).startswith('Não medido')
    assert state('PARTIAL', 'amostra').endswith('amostra')
    assert state('FAIL').startswith('Não medido')  # rule FAIL is not an integration error


@pytest.mark.parametrize('reference', ['../outside', '/etc/passwd', 'C:\\secret', 'file:///secret', 'artifacts/../../secret'])
def test_traversal(tmp_path, reference):
    with pytest.raises((ValueError, OSError)):
        confined(tmp_path, reference)


def test_costs():
    tables = {'ai_provider_attempts': [{'attempt_id': 'a', 'observed_cost': 0, 'estimated_cost': 9, 'cost_currency': 'USD'}, {'attempt_id': 'b', 'estimated_cost': 2, 'cost_currency': 'EUR'}],
              'content_remediation_attempts': [{'attempt_id': 'c', 'estimated_cost': .3, 'cost_currency': 'USD'}],
              'perplexity_search_runs': [{'attempt_id': 'a', 'estimated_cost': 9}],
              'ai_provider_native_usage': [{'attempt_id': 'a', 'estimated_cost': 9}]}
    result = reconcile(tables)
    assert result['attempt_count'] == 3
    assert result['totals']['USD']['conciliado'] == '0.3'
    assert result['totals']['EUR']['conciliado'] == '2'
    assert result['totals']['EUR']['observado'] is None
    tables['perplexity_search_runs'].append({'attempt_id': 'orphan', 'estimated_cost': 100})
    assert reconcile(tables)['warnings']


def test_evidence_and_counts():
    assert locate('abc abc', 'abc')['line'] is None
    assert locate('first\nabc', 'abc')['line'] == 2
    assert locate('first\nabc', 'abc')['column'] == 1
    assert locate('abc', 'missing')['line'] is None
    assert counts('<p>one two</p><script>not words</script><a>x</a><img>')['words'] == 3


def test_sanitize():
    data = sanitize({'api_key': 'x', 'output_tokens': 0, 'payload': '{"password":"y"}', 'error': 'Authorization: Bearer ABCDEF'})
    assert data['api_key'] == '[REDACTED]'
    assert data['output_tokens'] == 0
    assert data['payload']['password'] == '[REDACTED]'
    assert 'ABCDEF' not in data['error']
    assert 'PRIVATE_INPUT' not in sanitize('<input type="password" value="PRIVATE_INPUT">')


def test_thresholds():
    assert load()[0]['origin'] == 'PRODUCT_PROPOSAL'
    assert load()[0]['thresholds'] == [60, 80, 95]


def test_primary_text_contrast():
    import re
    css = (Path(__file__).parents[2] / 'src/rasai/parallel_report/assets/site.css').read_text(encoding='utf-8')
    def luminance(hex_color):
        components = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in components]
        return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))
    for selector in (':root', 'body.dark'):
        block = re.search(re.escape(selector) + r'\{([^}]+)', css).group(1)
        tokens = dict(re.findall(r'--([a-z]+):(#[0-9a-f]+)', block))
        for key in ('bg', 'card'):
            background = tokens[key]
            if len(background) == 4:
                background = '#' + ''.join(c * 2 for c in background[1:])
            for foreground in ('ink', 'mut', 'acc'):
                values = sorted((luminance(tokens[foreground]), luminance(background)))
                assert (values[1] + .05) / (values[0] + .05) >= 4.5


class Links(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids, self.links = set(), []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            assert attrs['id'] not in self.ids
            self.ids.add(attrs['id'])
        if tag in {'a', 'link', 'script'}:
            self.links.append(attrs.get('href', attrs.get('src', '')))


@pytest.mark.parametrize('complete', [True, False])
def test_integration(tmp_path, monkeypatch, complete):
    root = fixture(tmp_path / 'audit', complete)
    before = inventory(root)
    def no_network(*args, **kwargs):
        raise AssertionError('Network forbidden')
    monkeypatch.setattr(socket, 'socket', no_network)
    output = generate(root)
    manifest = json.loads((output / '_geracao.json').read_text(encoding='utf-8'))
    assert manifest['page_count'] == 10
    assert manifest['source_tree_digest_before'] == manifest['source_tree_digest_after']
    assert manifest['parity_differences']['comparisons']['scores']['status'] == 'PASS'
    assert manifest['external_requests'] == manifest['ai_calls'] == manifest['source_writes'] == 0
    for name, value in manifest['sha256_per_file'].items():
        assert digest(output / name) == value
    htmls = {p.name: Links(p.read_text(encoding='utf-8')) for p in output.glob('*.html')}
    for name, parsed in htmls.items():
        for ref in parsed.links:
            target, _, anchor = ref.partition('#')
            assert not target.startswith(('http:', 'https:', 'javascript:'))
            if target:
                assert (output / target).is_file(), ref
            if anchor:
                assert anchor in htmls[target or name].ids
    for path in output.rglob('*'):
        if path.is_file():
            text = path.read_text(encoding='utf-8')
            assert 'PRIVATE_VALUE' not in text
            assert 'HIDDEN_VALUE' not in text
            assert '<script>alert(1)</script>' not in text or path.suffix == '.json'
    preserved = {str(p): digest(p) for p in output.rglob('*') if p.is_file()}
    second = generate(root)
    assert second != output and second.parent == output
    assert all(digest(Path(path)) == value for path, value in preserved.items())
    assert inventory(root) == before


def test_schema_and_crossrefs(tmp_path):
    root = fixture(tmp_path / 'audit')
    tables, schema = read_database(root / 'audit.db')
    assert 'device' not in schema['scores']['columns']
    records = build(tables, schema)
    links, _ = link_records(records)
    finding = next(r for r in records if r.table == 'findings')
    action = next(r for r in records if r.table == 'directed_analysis_actions')
    assert finding.href in links[action.href]
    assert action.href in links[finding.href]
    with pytest.raises(TypeError):
        finding.data['title'] = 'changed'


def test_extension_primary_key_does_not_shadow_entity():
    tables = {'findings': [{'finding_id': 'f'}],
              'root_cause_precision': [{'finding_id': 'f', 'observed_selector': 'h1'}],
              'recommendations': [{'recommendation_id': 'r', 'finding_id': 'f'}]}
    schema = {table: {'primary_key': [next(iter(rows[0]))]} for table, rows in tables.items()}
    records = build(tables, schema)
    links, ambiguous = link_records(records)
    finding = next(r for r in records if r.table == 'findings')
    assert len(links[finding.href]) == 2
    assert ambiguous == 0
    tables['passive_security_findings'] = [{'finding_id': 'f'}]
    schema['passive_security_findings'] = {'primary_key': ['finding_id']}
    records = build(tables, schema)
    links, ambiguous = link_records(records)
    assert ambiguous == 1  # two canonical owners: still abstain


def test_existing_presentation_not_shadowed():
    import rasai.report_presentation as legacy
    assert Path(legacy.__file__).name == 'report_presentation.py'
    assert callable(legacy.humanize_report_html)

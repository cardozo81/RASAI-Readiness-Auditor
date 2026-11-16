"""Presentation autonomy, SERP humanization, and timestamp/typography regressions.

Strictly offline. No AI, HTTP, source mutation or catalog HTML reads.
"""
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from rasai.parallel_report.catalog_context import catalog_context
from rasai.parallel_report.generator import generate
from rasai.parallel_report.page_views import editorial
from rasai.parallel_report.presentation_labels import public_value, presentation_timestamps
from rasai.parallel_report.read_model import build, SEARCH_PAGE
from rasai.parallel_report.thresholds import load

from test_parallel_report import fixture


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get('id'):
            self.ids.add(values['id'])
        if tag == 'a' and values.get('href'):
            self.hrefs.append(values['href'])


def test_all_presentation_links_resolve_with_no_catalog_package(tmp_path):
    audit = fixture(tmp_path / 'audit')
    # The catalog may not accompany the presentation when exported.
    # No link or material fact may rely upon its existence.
    from shutil import rmtree
    rmtree(audit / 'report-catalog')
    output = generate(audit)
    html = {path.name: path.read_text(encoding='utf-8') for path in output.glob('*.html')}
    assert len(html) == 11
    parsed = {}
    for filename, document in html.items():
        parser = Links()
        parser.feed(document)
        parsed[filename] = parser
        assert '—' not in document, filename
        assert '../report-catalog/' not in document, filename
        assert '(aprofundamento opcional; requer o pacote técnico' not in document
        for href in parser.hrefs:
            target = urlsplit(href)
            assert not target.scheme and not target.netloc, (filename, href)
            assert not href.startswith(('/', '../', '\\')), (filename, href)
            assert 'report-catalog' not in href, (filename, href)
            target_path = (output / filename).parent / unquote(target.path) if target.path else output / filename
            assert target_path.resolve().is_relative_to(output.resolve()), (filename, href)
            assert target_path.is_file(), (filename, href)
    for filename, parser in parsed.items():
        for href in parser.hrefs:
            target = urlsplit(href)
            if not target.fragment:
                continue
            target_name = Path(unquote(target.path)).name if target.path else filename
            if target_name in parsed:
                assert unquote(target.fragment) in parsed[target_name].ids, (filename, href)
    extract = html['extracao.html']
    assert 'Captura e prévia técnica local' in extract
    assert 'href="#capture-preview"' in extract
    assert 'id="capture-preview"' in extract
    assert 'id="presentation-records"' in extract
    assert 'Ver detalhes' in extract


def test_persisted_preview_has_only_local_destinations_and_timezone(tmp_path, monkeypatch):
    from rasai.parallel_report import catalog_context as module
    monkeypatch.setattr(module, '_verified_links', lambda *args: {'capture-context.html'})
    rows = {'page_snapshots': [
        {'device': 'MOBILE', 'captured_at': '2026-11-16T12:00:00Z', 'requested_url': 'https://example.test',
         'browser_metadata': json.dumps({
             'browser_identity': {'channel': 'Chrome', 'browser_version': '123'},
             'profile': {'viewport': {'width': 390, 'height': 844}},
             'visual_artifact_ref': 'artifacts/screenshot.png',
             'runtime_diagnostics': {'items': [
                 {'type': 'PAGE_ERROR', 'message': 'Falha observada', 'url': 'https://example.test/'}
             ]}
         })}
    ]}
    section = catalog_context(tmp_path, 'logical', 'AUD-X', rows, 'America/Sao_Paulo')['extracao']
    assert '16/11/2026 09:00:00 (America/Sao_Paulo)' in section
    assert 'Ver detalhes' in section
    assert 'Chrome 123' in section and '390 x 844' in section
    assert 'artifacts/screenshot.png' in section
    assert 'Ocorrências registradas pelo navegador na captura' in section
    assert 'Erro de JavaScript' in section and 'Falha observada' in section
    assert '#capture-preview' in section
    assert '#presentation-records' in section
    assert 'report-catalog' not in section


def test_competition_uses_factual_human_text_and_preserves_persisted_reason():
    cases = [
        ('CUSTOMER', 'matches configured customer domain', 'Resultado do domínio auditado', 'Pertence ao domínio'),
        ('ORGANIC_CANDIDATE', 'external organic result; business equivalence is not inferred', 'candidato, não concorrente comprovado', 'não foi comprovada equivalência'),
        ('PUBLIC_AUTHORITY', 'public-authority domain heuristic', 'autoridade pública', 'por regra'),
        ('KNOWLEDGE_REFERENCE', 'knowledge/reference platform heuristic', 'Fonte de referência', 'por regra'),
        ('SOCIAL_PLATFORM', 'social platform heuristic', 'Rede social', 'por regra'),
        ('VIDEO_PLATFORM', 'video platform heuristic', 'Plataforma de vídeo', 'por regra'),
        ('MARKETPLACE', 'marketplace heuristic; retained as a Search competitor candidate', 'Marketplace', 'sem presumir concorrência comercial'),
        ('NON_ORGANIC', 'SERP result_type=advertisement', 'Resultado não orgânico', 'tipo: advertisement'),
    ]
    rows = []
    for index, (kind, reason, kind_label, reason_label) in enumerate(cases):
        assert kind_label in public_value(kind, 'classification')
        assert reason_label in public_value(reason, 'reason')
        rows.append({'result_id': 'r' + str(index), 'position': index + 1,
                     'classification': kind, 'reason': reason,
                     'url': 'https://example.test/' + str(index), 'domain': 'example.test',
                     'eligible_for_content_comparison': 1, 'selected_for_content_comparison': 0})
    assert public_value(1, 'eligible_for_content_comparison') == 'Sim'
    assert public_value(0, 'selected_for_content_comparison') == 'Não'
    assert public_value(None, 'eligible_for_content_comparison') == 'N/D'
    assert public_value('UNRECOGNIZED', 'classification') == 'UNRECOGNIZED'
    assert public_value('unknown free text', 'reason') == 'unknown free text'
    schema = {'serp_competitive_results': {'primary_key': ['result_id']}}
    records = build({'serp_competitive_results': rows}, schema)
    html = editorial(SEARCH_PAGE, records, {}, load())
    assert 'não comprovação de concorrência comercial' in html
    assert 'Resultado orgânico externo' in html
    assert 'Motivo da classificação' in html
    assert 'external organic result; business equivalence is not inferred' in html  # original only in technical data


def test_timestamp_copy_only_changes_typed_visible_fields():
    timestamp = '2026-11-16T12:00:00Z'
    source = {'capture_utc': timestamp, 'captured_at': timestamp, 'note': timestamp,
              'nested': {'provider_created_at': timestamp},
              'evidence_text': 'Captura — preservar conteúdo original'}
    result = presentation_timestamps(source, 'America/Sao_Paulo')
    for key in ('capture_utc', 'captured_at'):
        assert result[key] == '16/11/2026 09:00:00 (America/Sao_Paulo)'
    assert result['nested']['provider_created_at'] == '16/11/2026 09:00:00 (America/Sao_Paulo)'
    assert result['note'] == timestamp
    assert result['evidence_text'] == source['evidence_text']
    assert source['capture_utc'] == timestamp
    assert public_value('2026-11-16', 'capture_utc', 'America/Sao_Paulo') == '2026-11-16'

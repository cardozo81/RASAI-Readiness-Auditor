"""Project selected human-readable facts from the verified, same-audit technical report."""
from collections import defaultdict
from html.parser import HTMLParser
import json

from rasai.catalog_report_site import verify_catalog_report_package
from rasai.catalog_source_dependencies import verify_source_dependencies
from .components import text, technical_link
from .read_model import SEARCH_PAGE
from .sanitization import sanitize


# Match fields, not row offsets. A changed or missing schema cannot be mislabelled.
# The linked technical page retains every row, including any beyond the preview.
TABLES = {
    'execution-evidence': [
        ('index', 'Estado funcional dos catálogos', ('Catálogo', 'Contexto', 'Selecionado', 'Estado funcional'), 10)],
    'cat-05': [
        ('index', 'Causas das limitações em pesquisa', ('Causa', 'Classe', 'Explicação técnica', 'Impacto negocial'), 8),
        (SEARCH_PAGE, 'Cobertura por fonte de pesquisa', ('Capacidade / fonte', 'Configurado', 'Solicitado', 'Habilitado', 'Executado', 'Dados', 'Estado'), 8),
        (SEARCH_PAGE, 'Cobertura do Common Crawl', ('Conjunto de dados', 'Método', 'Coletado em', 'Requisições', 'Registros', 'Sem captura', 'Erros'), 4),
        ('performance', 'Histórico CrUX por origem e período', ('Dataset', 'Método', 'Coletado em', 'Período início', 'Período fim', 'Pontos'), 8)],
    'cat-04': [
        ('performance', 'Por que o campo recebeu esta avaliação', ('Métrica', 'p75 observado', 'Limite para Bom', 'Diagnóstico'), 3),
        ('performance', 'Universo de campo por dispositivo', ('Fonte', 'Escopo', 'Dispositivo', 'Período observado', 'Alvo'), 8),
        ('performance', 'Métricas de laboratório, campo e histórico', ('Indicador', 'Valor', 'Tipo'), 24)],
    'ai-integrations': [
        ('ia-custos', 'Resultado e fallback por finalidade', ('Tarefa / finalidade', 'Resultado final', 'Provedor efetivo', 'Leitura', 'Sequência de tentativas'), 10),
        ('ia-custos', 'Prontidão antes de cada uso', ('Finalidade', 'Prontidão', 'Esperadas', 'Pendentes', 'Registrado em'), 8)],
    'index': [
        ('extracao', 'Arquitetura por captura', ('Snapshot', 'Página', 'Dispositivo', 'URL solicitada', 'URL final observada', 'Arquitetura observada', 'Declarada', 'Efetiva nesta análise', 'Fonte', 'Limite'), 4)],
    'cat-10': [
        ('seguranca', 'Alcance da observação passiva', ('Cobertura', 'Estado'), 20)],
}

REFERENCES = {
    'indices': ('methodology', 'Método e versão das regras de pontuação'),
    'descoberta': ('cat-01', 'Diagnóstico por ocorrência, documento e posição do validador W3C'),
    'extracao': ('capture-context', 'Abrir a captura e sua prévia local'),
    'rede': ('network', 'Abrir mapa, rota, cronologia e diagnóstico técnico de rede'),
    'ia-custos': ('metrics', 'Intervalos das tentativas, invólucros do pipeline e tempos HTTP'),
}


class PublicTables(HTMLParser):
    """Read only visible table cells; omit dialogs, controls and raw payloads."""
    def __init__(self):
        super().__init__()
        self.tables = []
        self.rows = self.row = self.cell = None
        self.skip = []

    def handle_starttag(self, tag, attrs):
        if tag in {'dialog', 'script', 'style', 'button', 'pre'}:
            self.skip.append(tag)
        if self.skip:
            return
        if tag == 'table':
            self.rows = []
        elif tag == 'tr' and self.rows is not None:
            self.row = []
        elif tag in {'th', 'td'} and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None and not self.skip:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if self.skip:
            if self.skip[-1] == tag:
                self.skip.pop()
            return
        if tag in {'td', 'th'} and self.cell is not None:
            self.row.append(' '.join(' '.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        elif tag == 'table' and self.rows is not None:
            if self.rows:
                self.tables.append(self.rows)
            self.rows = None


def catalog_context(root, logical, audit_id):
    directory = root / 'report-catalog'
    try:
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        if (manifest.get('audit_id') != audit_id
                or manifest.get('audit_snapshot', {}).get('source_logical_sha256') != logical
                or not verify_catalog_report_package(directory)[0]
                or not verify_source_dependencies(root, manifest.get('source_dependencies'))[0]):
            return {}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}
    files = {item['path'] for item in manifest['packaged_files']}
    sections = defaultdict(str)
    for stem, specs in TABLES.items():
        name = stem + '.html'
        if name not in files:
            continue
        parser = PublicTables()
        parser.feed((directory / name).read_text(encoding='utf-8'))
        for page, title, fields, limit in specs:
            for header, *rows in parser.tables:
                if tuple(header[:len(fields)]) != fields:
                    continue
                visible = [row[:len(fields)] for row in rows if len(row) >= len(fields)]
                if not visible:
                    continue
                head = ''.join('<th scope="col">' + text(field) + '</th>' for field in fields)
                body = ''.join('<tr>' + ''.join('<td>' + text(sanitize(cell)) + '</td>' for cell in row) + '</tr>'
                               for row in visible[:limit])
                source = technical_link('../report-catalog/' + name, 'Abrir quadro técnico de origem')
                sections[page] += (f'<details><summary>{text(title)}</summary><div class="tw"><table>'
                                   f'<caption>{text(title)} · {min(limit, len(visible))} de {len(visible)} linhas</caption>'
                                   f'<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>{source}</details>')
    for page, (stem, title) in REFERENCES.items():
        if stem + '.html' in files:
            sections[page] += '<p>' + technical_link('../report-catalog/' + stem + '.html', title) + '</p>'
    return sections

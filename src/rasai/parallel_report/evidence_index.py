"""Physical locations only when a literal has exactly one occurrence."""
from html.parser import HTMLParser
from .artifact_reader import confined, digest


def locate(text, literal):
    if not literal or text.count(literal) != 1:
        return {'coverage': 'Parcial — trecho ausente ou ambíguo', 'line': None, 'column': None}
    start = text.index(literal)
    return {'coverage': 'Medido', 'line': text[:start].count('\n') + 1,
            'column': start - text.rfind('\n', 0, start)}


class Counts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = self.images = self.hidden = 0
        self.words = []

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style'}:
            self.hidden += 1
        self.links += tag == 'a'
        self.images += tag == 'img'

    def handle_endtag(self, tag):
        if tag in {'script', 'style'}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.words.extend(data.split())


def counts(text):
    parser = Counts()
    parser.feed(text)
    return {'words': len(parser.words), 'links': parser.links, 'images': parser.images,
            'origin': 'Calculado no relatório', 'algorithm_version': 'html-parser-visible-text-1'}


def references(tables, root):
    output, calculated = [], []
    for table, rows in tables.items():
        for row_index, row in enumerate(rows):
            for key, value in row.items():
                if not isinstance(value, str) or not (key.endswith(('_artifact_ref', '_artifact_reference', '_evidence_ref')) or key in {'artifact_reference', 'main_content_ref', 'structured_data_ref'}):
                    continue
                entry = {'table': table, 'row_index': row_index, 'field': key, 'reference': value,
                         **{k: row.get(k) for k in ('audit_id', 'page_id', 'snapshot_id', 'device', 'captured_at', 'evidence_id', 'selector', 'xpath')}}
                try:
                    path = confined(root, value)
                    entry.update(sha256=digest(path), type=path.suffix, coverage='Parcial — localização literal não persistida')
                    literal = row.get('outer_html') or row.get('text_excerpt')
                    if path.suffix.lower() in {'.html', '.txt', '.json', '.response'}:
                        text = path.read_text(encoding='utf-8', errors='replace')
                        if literal:
                            entry.update(locate(text, literal), excerpt=literal)
                        if key == 'rendered_artifact_ref':
                            calculated.append({'source': value, 'sha256': entry['sha256'], **counts(text)})
                    expected = row.get(key.replace('_reference', '_sha256'))
                    if expected and expected != value and expected != entry['sha256']:
                        entry['coverage'] = 'Falhou — hash persistido divergente'
                except (OSError, ValueError):
                    entry['coverage'] = 'Parcial — arquivo ausente ou referência insegura'
                output.append(entry)
    return output, calculated

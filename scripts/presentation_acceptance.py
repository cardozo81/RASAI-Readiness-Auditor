"""Confidential local acceptance on a new isolated copy; never publish source data.

PowerShell wrapper pins the clean checkout. This runner blocks network, hashes
the complete original tree, copies it, preserves the previous presentation,
generates only the new presentation and validates every local link and source.
"""
import argparse
from collections import Counter
from hashlib import sha256
from html.parser import HTMLParser
import json
import ipaddress
from pathlib import Path
import shutil
import sqlite3
import sys
from urllib.parse import unquote, urlsplit

from rasai.document_advisory import _inventory, _plain
from rasai.parallel_report.artifact_reader import digest, inventory
from rasai.parallel_report.generator import generate
from rasai.parallel_report.sqlite_reader import read_database


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.ids, self.records, self.links, self.headings, self.tokens = set(), set(), [], [], []
        self.heading = None
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get('id'):
            if a['id'] in self.ids:
                raise ValueError('duplicate HTML identifier')
            self.ids.add(a['id'])
            if tag == 'div' and a.get('class') == 'record':
                self.records.add(a['id'])
        if tag in {'a','link','script','img'}:
            ref = a.get('href') or a.get('src')
            if ref: self.links.append(ref)
        if tag in {'h1','h2'}: self.heading = []

    def handle_data(self, text):
        self.tokens.append(text)
        if self.heading is not None: self.heading.append(text)

    def handle_endtag(self, tag):
        if tag in {'h1','h2'} and self.heading is not None:
            self.headings.append(''.join(self.heading).replace('\u2014','-'))
            self.heading = None


def validate_package(output):
    manifest=json.loads((output/'_geracao.json').read_text(encoding='utf-8'))
    for name, expected in manifest['sha256_per_file'].items():
        if digest(output/name) != expected: raise ValueError('generated file digest mismatch')
    if manifest.get('annex_contract') != 'CONTENT_SHA256_V1':
        raise ValueError('current presentation must use content-addressed annexes')
    if set(manifest.get('table_annexes', {})) != set(manifest['tables_read']):
        raise ValueError('table-annex mapping incomplete')
    for table, filename in manifest['table_annexes'].items():
        path=output/'anexos'/filename
        if not path.is_file() or digest(path)!=filename[:-5]:
            raise ValueError('table annex address mismatch: '+table)
    for name in ('coverage-map.json','evidence-coverage.json'):
        if not (output/'anexos'/'dados-de-apoio'/name).is_file():
            raise ValueError('missing support receipt: '+name)
        if (output/'assets'/name).exists():
            raise ValueError('legacy support receipt path is forbidden: '+name)
    docs={p.name:Document(p.read_text(encoding='utf-8')) for p in output.glob('*.html')}
    if len(docs)!=11: raise ValueError('expected eleven HTML pages')
    links=0
    for name,doc in docs.items():
        for ref in doc.links:
            links+=1
            url=urlsplit(ref)
            if url.scheme or url.netloc or 'report-catalog' in ref:
                raise ValueError('non-local presentation dependency')
            target=(output/unquote(url.path)).resolve() if url.path else output/name
            if not target.is_relative_to(output.resolve()) or not target.is_file():
                raise ValueError('broken or escaping local link')
            if url.fragment and target.name in docs and unquote(url.fragment) not in docs[target.name].ids:
                raise ValueError('broken local fragment')
    records=[identifier for doc in docs.values() for identifier in doc.records]
    if len(set(records))!=len(records): raise ValueError('duplicate record anchor')
    return manifest,docs,dict(pages=len(docs), records=len(records), links=links,
        broken_links=0,catalog_links=0,files_hashed=len(manifest['sha256_per_file']),
        physical_references=len(manifest['artifacts_read']),
        unique_physical_files=len({r['reference'] for r in manifest['artifacts_read']}))


def compare_reports(previous, output):
    """Sections, record identities and persisted fields, never byte-equal derived HTML."""
    old={p.name:Document(p.read_text(encoding='utf-8')) for p in previous.glob('*.html')}
    new={p.name:Document(p.read_text(encoding='utf-8')) for p in output.glob('*.html')}
    comparison={}
    for name,doc in new.items():
        prior=old.get(name)
        comparison[name]=dict(
            old_records=len(prior.records) if prior else None,new_records=len(doc.records),
            removed_record_anchors=sorted(prior.records-doc.records) if prior else [],
            added_sections=list((Counter(doc.headings)-Counter(prior.headings)).elements()) if prior else doc.headings,
            removed_sections=list((Counter(prior.headings)-Counter(doc.headings)).elements()) if prior else [],
        )
        if prior and prior.records-doc.records: raise ValueError('record anchor regression')
    # P11: legacy table-name digests change to content-derived filenames.
    # Preserve the original sanitized records by table identity; do NOT require
    # deprecated URLs to remain in the newly published package.
    new_manifest=json.loads((output/'_geracao.json').read_text(encoding='utf-8'))
    names=new_manifest['table_annexes']
    legacy={sha256(table.encode()).hexdigest()+'.json':table for table in names}
    preserved, migrated=0,0
    for file in (previous/'anexos').glob('*.json'):
        if file.name in legacy:
            table=legacy[file.name]
            new_file=output/'anexos'/names[table]
            if not new_file.is_file() or json.loads(file.read_text(encoding='utf-8')) != json.loads(new_file.read_text(encoding='utf-8')):
                raise ValueError('table annex semantic regression: '+table)
            migrated+=1
        else:
            new_file=output/'anexos'/file.name
            if not new_file.is_file() or digest(new_file)!=digest(file):
                raise ValueError('payload annex regression: '+file.name)
            preserved+=1
    return dict(pages=comparison, legacy_table_annexes_migrated=migrated,
                content_annexes_preserved=preserved)


def browser_check(output, destination):
    from playwright.sync_api import sync_playwright
    result=dict(status='PASS',viewports=[390,1440,2560],pages=0,requests=0,javascript_errors=0)
    with sync_playwright() as p:
        if not Path(p.chromium.executable_path).is_file():
            return dict(status='NOT_EXECUTED',reason='CHROMIUM_UNAVAILABLE')
        browser=p.chromium.launch()
        context=browser.new_context(offline=True)
        requests,errors=[],[]
        context.route('**/*',lambda route:route.abort() if route.request.url.startswith(('http:','https:')) else route.continue_())
        page=context.new_page()
        page.on('request',lambda r:requests.append(r.url) if r.url.startswith(('http:','https:')) else None)
        page.on('pageerror',lambda e:errors.append(type(e).__name__))
        for width in result['viewports']:
            page.set_viewport_size(dict(width=width,height=1000))
            for source in output.glob('*.html'):
                page.goto(source.as_uri())
                assert page.locator('nav[aria-label="Páginas"] a').count()==11
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),source.name
                page.locator('#expand').click()
                assert page.locator('details:not([open])').count()==0
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),source.name
                if page.locator('.modal-open:not(.capture-image-button):visible').count():
                    page.locator('.modal-open:not(.capture-image-button):visible').first.click()
                    assert page.locator('dialog[open]').is_visible()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),source.name
                    page.keyboard.press('Escape')
                    assert page.locator('dialog[open]').count()==0
                page.locator('#expand').click()
                assert page.locator('details[open]').count()==0
                page.locator('#theme').click()
                assert page.locator('body').evaluate('(e)=>e.classList.contains("dark")')
                page.locator('#theme').click()
                page.screenshot(path=str(destination/(source.stem+'-'+str(width)+'.png')))
                # Capture new executive sections at native viewport size; expanded
                # technical inventories can exceed Chromium's bitmap dimensions.
                for title in ('Estrutura editorial verificável da captura', 'Síntese das validações técnicas',
                              'Elegibilidade da comparação competitiva', 'Referências identificáveis do AI Overview',
                              'Histórico de campo com proveniência'):
                    heading=page.get_by_role('heading',name=title,exact=True)
                    if heading.count():
                        heading.scroll_into_view_if_needed()
                        page.screenshot(path=str(destination/(source.stem+'-'+sha256(title.encode()).hexdigest()[:8]+'-'+str(width)+'.png')))
                result['pages']+=1
        assert not requests and not errors
        browser.close()
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--audit',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--expected-db-sha256',required=True)
    parser.add_argument('--browser',action='store_true')
    args=parser.parse_args()
    source=_plain(args.audit.absolute()).resolve(strict=True);work=_plain(args.output.absolute())
    if (work.exists() or work.resolve().is_relative_to(source) or source.is_relative_to(work.resolve())):
        raise ValueError('new external output directory required')
    before=_inventory(source)
    if before.get('audit.db')!=args.expected_db_sha256: raise ValueError('unexpected audit database')
    work.mkdir(parents=True)
    (work/'original-inventory.json').write_text(json.dumps(before,indent=2),encoding='utf-8')
    copy=work/source.name
    shutil.copytree(source,copy)
    if _inventory(copy)!=before or _inventory(source)!=before: raise ValueError('copy or source mismatch')
    old=copy/'report-presentation'; backup=work/'previous-presentation'
    if old.exists(): shutil.copytree(old,backup)
    tables,schema=read_database(copy/'audit.db')
    with sqlite3.connect((copy/'audit.db').as_uri()+'?mode=ro&immutable=1',uri=True) as con:
        integrity=con.execute('PRAGMA integrity_check').fetchone()[0]
    con.close()
    if integrity!='ok': raise ValueError('SQLite integrity failure')
    baseline=inventory(copy)
    # No network in this process; the bounded structural child has its own audit hook.
    browser_phase = [False]
    def offline(event,args):
        # Windows asyncio implements its local wakeup pipe using socketpair.
        # Only that numeric loopback transport is allowed during browser QA.
        if event == 'socket.connect' and browser_phase[0]:
            try:
                if ipaddress.ip_address(args[1][0]).is_loopback: return
            except (ValueError, TypeError, IndexError):
                pass
        if event in {'socket.connect','socket.getaddrinfo'}: raise PermissionError('offline acceptance')
    sys.addaudithook(offline)
    try:
        output=generate(copy)
        manifest,docs,checks=validate_package(output)
        if inventory(copy)!=baseline or read_database(copy/'audit.db')!=(tables,schema):
            raise ValueError('source bytes or row identity changed')
        from rasai.parallel_report.read_model import destination
        expected=sum(len(rows) for n,rows in tables.items() if destination(n) is not None)
        if checks['records']!=expected: raise ValueError('record coverage mismatch')
        comparison=compare_reports(backup,output) if backup.exists() else None
        receipt=json.loads((output/'anexos/dados-de-apoio/evidence-coverage.json').read_text(encoding='utf-8'))
        report=dict(generator_version=manifest['generator_version'],source_db_sha256=before['audit.db'],
            sqlite_integrity=integrity,sqlite_tables=len(tables),sqlite_rows=sum(map(len,tables.values())),
            checks=checks,comparison=comparison,editorial=receipt['editorial'],
            original_source_preserved=False,copy_source_preserved=True,human_acceptance='PENDING',
            network_requests=0,provider_calls=0,score_recomputed=False)
        if args.browser:
            browser_phase[0] = True
            try: report['browser']=browser_check(output,work)
            finally: browser_phase[0] = False
        else: report['browser']=dict(status='NOT_EXECUTED',reason='BROWSER_NOT_REQUESTED')
        # Idempotence means no new worker, manifest or output bytes on reopening.
        generated_before=_inventory(output)
        if generate(copy)!=output or _inventory(output)!=generated_before:
            raise ValueError('presentation not idempotent')
    finally:
        after=_inventory(source)
        (work/'original-inventory-after.json').write_text(json.dumps(after,indent=2),encoding='utf-8')
        if after!=before: raise ValueError('original source changed; acceptance refused')
    report['original_source_preserved']=True
    (work/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(version=report['generator_version'],checks=checks,
        capture_state=receipt['editorial']['capture_state'],history_state=receipt['editorial']['history_state'],
        browser=report['browser'],original_source_preserved=True),ensure_ascii=True))
    return 0 if report['browser']['status']=='PASS' else 2


if __name__=='__main__':
    raise SystemExit(main())

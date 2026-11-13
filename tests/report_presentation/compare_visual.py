"""Private prototype comparison; outputs must stay outside version control."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

VIEWPORTS = [(1440,900),(1920,1080),(1280,800),(820,1180),(390,844)]
SELECTORS = ['body','aside','main','.top','.shell','.rail','.tw','.chip','.org','.ruler','.bar','.mk','.callout','details']
PROPERTIES = ['fontFamily','fontSize','lineHeight','backgroundColor','color','borderColor','borderRadius','padding','width','maxWidth','position','top','gap']


def compare(prototype, report, output):
    output.mkdir(parents=True, exist_ok=False)
    results, errors, external = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(offline=True, color_scheme='light')
        context.route('**/*', lambda r: r.abort() if r.request.url.startswith(('http:','https:')) else r.continue_())
        page = context.new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('request', lambda r: external.append(r.url) if r.url.startswith(('http:','https:')) else None)
        for width,height in VIEWPORTS:
            page.set_viewport_size({'width':width,'height':height})
            for name in sorted(path.name for path in report.glob('*.html')):
                pair = {'page':name,'viewport':[width,height],'styles':{}}
                for kind,root in [('prototype',prototype),('report',report)]:
                    page.goto((root/name).as_uri())
                    page.screenshot(path=str(output/f'{width}-{name}-{kind}.png'))
                    pair[kind+'_overflow'] = page.evaluate('document.documentElement.scrollWidth>innerWidth')
                    if kind=='report':
                        assert page.locator('.rail a').evaluate_all('(links)=>links.every(a=>document.getElementById(a.hash.slice(1)))')
                        assert page.locator('.mk[data-position]').evaluate_all('(items)=>items.every(e=>Number.isFinite(parseFloat(e.style.left))&&parseFloat(e.style.left)>=0&&parseFloat(e.style.left)<=100)')
                        assert page.locator('.stack [data-width]').evaluate_all('(items)=>items.every(e=>Number.isFinite(parseFloat(e.style.width)))')
                    pair['styles'][kind] = page.evaluate('''({selectors,properties})=>Object.fromEntries(selectors.map(s=>{const e=document.querySelector(s);return [s,e?Object.fromEntries(properties.map(k=>[k,getComputedStyle(e)[k]])):null]}))''',{'selectors':SELECTORS,'properties':PROPERTIES})
                pair['differences'] = {selector:{key:[pair['styles']['prototype'][selector][key],pair['styles']['report'][selector][key]] for key in PROPERTIES if pair['styles']['prototype'][selector][key]!=pair['styles']['report'][selector][key]} for selector in SELECTORS if pair['styles']['prototype'][selector] and pair['styles']['report'][selector]}
                results.append(pair)
        page.goto((report/'plano.html').as_uri())
        page.set_viewport_size({'width':1440,'height':900})
        for section,title in [('actions','Cartões de ação'),('corrections','Correções técnicas propostas (código)'),('suggestions','Textos sugeridos por IA')]:
            heading=page.get_by_role('heading',name=title,exact=True)
            heading.evaluate('(e)=>{let next=e.nextElementSibling;while(next&&next.tagName!=="H2"){if(next.tagName==="DETAILS"){next.open=true;next.scrollIntoView();return}next=next.nextElementSibling}e.scrollIntoView()}')
            page.screenshot(path=str(output/f'plano-{section}-expanded.png'))
        page.goto((report/'plano.html').as_uri())
        field=page.locator('.tools input').first
        field.fill('no-match-unique');assert '0 de ' in field.locator('..').inner_text();field.fill('')
        heading=page.locator('table th').first;heading.focus();page.keyboard.press('Enter');assert heading.get_attribute('aria-sort')=='ascending';page.keyboard.press('Space');assert heading.get_attribute('aria-sort')=='descending'
        page.locator('#expand').click();assert page.locator('details:not([open])').count()==0
        page.locator('#expand').click();assert page.locator('details[open]').count()==0
        page.emulate_media(color_scheme='dark');assert page.locator('body').evaluate('(e)=>getComputedStyle(e).backgroundColor')=='rgb(16, 22, 29)'
        page.get_by_role('heading',name='Ações por prioridade',exact=True).scroll_into_view_if_needed()
        page.screenshot(path=str(output/'plano-dark.png'))
        page.pdf(path=str(output/'plano-a4.pdf'),format='A4')
        browser.close()
    summary={'comparisons':results,'js_errors':errors,'external_requests':external}
    (output/'comparison.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    assert not errors and not external
    assert not any(row['report_overflow'] for row in results)
    print(json.dumps({'pairs':len(results),'screenshots':len(results)*2,'js_errors':len(errors),'external_requests':len(external),'report_overflow':sum(row['report_overflow'] for row in results),'output':str(output)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('prototype','report','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    compare(args.prototype.resolve(),args.report.resolve(),args.output.resolve())

"""Shared client-side UX for generated HTML report surfaces.

The enhancer keeps reports self-contained and read-only while adding scalable list
controls, responsive population cards and a consistent local section outline. No row,
card, metric or score is removed from the HTML source.
"""
from __future__ import annotations

from pathlib import Path


_STYLE_MARKER = "rasai-scale-ux-v2"
_SCRIPT_MARKER = "rasai-scale-ux-script-v2"

_SCALE_CSS = r"""
<style id="rasai-scale-ux-v2">
.rasai-list-toolbar{display:flex;flex-wrap:wrap;align-items:end;gap:9px;margin:14px 0;padding:12px;border:1px solid var(--line,rgba(111,123,141,.16));border-radius:7px;background:#f8f9fb}
.rasai-list-toolbar label{display:grid;gap:4px;min-width:150px;color:var(--muted,#6f7b8d);font-size:.76rem;font-weight:620}
.rasai-list-toolbar input,.rasai-list-toolbar select,.rasai-list-toolbar button{min-height:34px;border:1px solid var(--line,rgba(111,123,141,.22));border-radius:5px;background:#fff;color:var(--ink,#273449);padding:6px 9px;font:inherit}
.rasai-list-toolbar input{min-width:min(330px,70vw)}
.rasai-list-toolbar select[data-rasai-url-filter]{max-width:min(520px,80vw)}
.rasai-list-toolbar button{cursor:pointer;font-weight:620}.rasai-list-toolbar button:disabled{cursor:default;opacity:.45}
.rasai-list-toolbar .rasai-list-status{margin-left:auto;align-self:center;color:var(--muted,#6f7b8d);font-size:.8rem;white-space:nowrap}
.rasai-list-empty{padding:14px;border:1px dashed var(--line,rgba(111,123,141,.22));border-radius:6px;color:var(--muted,#6f7b8d);background:#fafbfc}
.rasai-population-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(320px,100%),1fr));gap:12px;margin:12px 0 18px}
.rasai-population-grid>.population-card{margin:0;min-width:0;overflow-wrap:anywhere}
.rasai-report-outline{position:sticky;top:0;z-index:30;margin:12px 0 14px;padding:10px 13px;border:1px solid var(--line,rgba(111,123,141,.18));border-radius:8px;background:rgba(251,252,254,.97);box-shadow:0 8px 18px rgba(31,45,61,.06)}
.rasai-report-outline.rasai-report-outline-legacy{position:static;z-index:auto;margin:12px 0 18px;padding:12px 14px;box-shadow:none;background:#fbfcfe}
.rasai-report-outline strong{display:block;margin-bottom:7px;font-size:.76rem;letter-spacing:.02em;text-transform:uppercase;color:var(--muted,#6f7b8d)}
.rasai-report-outline-links{display:flex;gap:7px 12px;flex-wrap:nowrap;overflow-x:auto;overscroll-behavior-inline:contain;scrollbar-width:thin;padding-bottom:2px}
.rasai-report-outline.rasai-report-outline-legacy .rasai-report-outline-links{flex-wrap:wrap;overflow:visible;padding-bottom:0}
.rasai-report-outline a{flex:0 0 auto;font-size:.8rem;text-decoration:none;white-space:nowrap}.rasai-report-outline a:hover{text-decoration:underline}
.rasai-section-anchor{scroll-margin-top:92px}
.rasai-analysis-status-actions{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:12px;padding-top:11px;border-top:1px solid var(--line,rgba(80,96,120,.16))}
.rasai-analysis-status-actions .rasai-help-open{margin:0;width:auto}
.rasai-analysis-status .report-dependency-state{margin:12px 0 0;padding:11px 13px;border-radius:8px;box-shadow:none}
.rasai-analysis-status-support{display:grid;gap:8px;margin-top:10px}
.rasai-analysis-status-support details{border:1px solid var(--line,rgba(80,96,120,.18));border-radius:8px;background:rgba(255,255,255,.72);padding:9px 11px}
.rasai-analysis-status-support summary{cursor:pointer;font-size:.82rem;font-weight:750;color:var(--ink,#273449)}
.rasai-analysis-status-support .notice{margin:9px 0 0;border-radius:7px;box-shadow:none}
.rasai-help-dialog:not(#rasai-consolidated-help)>section,.rasai-help-dialog:not(#rasai-consolidated-help)>details{padding:14px 16px;border:1px solid var(--line,rgba(80,96,120,.18));border-radius:10px;background:#fff;box-shadow:0 5px 16px rgba(31,45,61,.035)}
.rasai-help-dialog:not(#rasai-consolidated-help)>.rasai-help-summary{margin-top:18px;margin-bottom:18px;padding:13px 15px;border:1px solid var(--line,rgba(80,96,120,.16));border-left-width:4px}
.rasai-help-dialog:not(#rasai-consolidated-help)>.rasai-help-grid{gap:12px;margin-top:18px;margin-bottom:18px}
.rasai-help-dialog:not(#rasai-consolidated-help)>.rasai-help-grid>section{margin:0;padding:14px 16px;border:1px solid var(--line,rgba(80,96,120,.18));border-radius:10px;background:#fff;box-shadow:0 5px 16px rgba(31,45,61,.035)}
.rasai-help-dialog:not(#rasai-consolidated-help) .rasai-help-table{overflow:auto;border:1px solid var(--line,rgba(80,96,120,.14));border-radius:8px;background:#fff}
.rasai-help-dialog:not(#rasai-consolidated-help) .rasai-help-table table{margin:0}
.rasai-help-dialog:not(#rasai-consolidated-help) .rasai-help-technical{background:#f8f9fb}
@media(max-width:760px){.rasai-list-toolbar{align-items:stretch}.rasai-list-toolbar label{min-width:100%}.rasai-list-toolbar input,.rasai-list-toolbar select{min-width:0;width:100%;max-width:none}.rasai-list-toolbar .rasai-list-status{margin-left:0;width:100%}.rasai-population-grid{grid-template-columns:1fr}.rasai-report-outline{margin:8px 0 12px;padding:9px 11px}.rasai-report-outline-links{display:flex;grid-template-columns:none}.rasai-report-outline.rasai-report-outline-legacy .rasai-report-outline-links{display:grid;grid-template-columns:1fr}.rasai-analysis-status-actions{align-items:stretch}.rasai-analysis-status-actions .rasai-help-open{width:100%}}
@media print{.rasai-list-toolbar,.rasai-list-empty{display:none!important}.rasai-client-hidden{display:table-row!important}.page-card.rasai-client-hidden{display:block!important}.rasai-population-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.rasai-report-outline{display:none!important}.rasai-analysis-status-actions{display:none!important}}
</style>
""".strip()

_SCALE_SCRIPT = r"""
<script id="rasai-scale-ux-script-v2">
(function(){
  'use strict';
  const URL_THRESHOLD=2, LARGE_TABLE_FALLBACK=25, LARGE_CARD_FALLBACK=20;
  const normalize=v=>(v||'').toLocaleLowerCase('pt-BR');
  const stableText=item=>String((item&&item.textContent)||'');
  const isConsolidated=()=>Boolean(document.querySelector('[data-rasai-consolidated-experience="true"],#rasai-consolidated-help,[data-rasai-consolidated-help-trigger="true"]'));
  const safeUrl=v=>{
    try{
      const cleaned=(v||'').trim().replace(/[),.;]+$/,'');
      const u=new URL(cleaned);
      return /^https?:$/.test(u.protocol)?u.href:null;
    }catch(_){return null;}
  };
  const urlsInText=text=>{
    const matches=(text||'').match(/https?:\/\/[^\s<>'"`]+/gi)||[];
    return matches.map(safeUrl).filter(Boolean);
  };
  const itemCache=new WeakMap();
  const indexForItem=item=>{
    const cached=itemCache.get(item); if(cached) return cached;
    const text=stableText(item), upper=text.toUpperCase();
    const values=[];
    if(item.querySelectorAll){item.querySelectorAll('.page-url').forEach(node=>values.push(...urlsInText(node.textContent||'')));}
    values.push(...urlsInText(text));
    const indexed={text:normalize(text),upper,urls:Array.from(new Set(values))};
    itemCache.set(item,indexed); return indexed;
  };
  const urlsForItem=item=>indexForItem(item).urls;
  const urlsFor=items=>Array.from(new Set(items.flatMap(urlsForItem))).sort((a,b)=>a.localeCompare(b,'pt-BR'));
  const contextsFor=items=>{
    const joined=items.map(x=>indexForItem(x).upper).join('\n');
    const out=[];
    if(/\bMOBILE\b/.test(joined)) out.push('MOBILE');
    if(/\bDESKTOP\b/.test(joined)) out.push('DESKTOP');
    return out;
  };
  const shouldEnhance=(items,fallback)=>urlsFor(items).length>=URL_THRESHOLD||items.length>=fallback;
  const slug=value=>normalize(value).normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,70)||'secao';
  const headingEligible=heading=>{
    if(isConsolidated()) return true;
    return !heading.closest('dialog,.rasai-analysis-status,.rasai-fulfillment-banner,.rasai-page-transparency,footer,[data-rasai-no-outline="true"]');
  };
  const buildOutline=()=>{
    const main=document.querySelector('main'); if(!main) return null;
    const existing=main.querySelector('.rasai-report-outline');
    if(existing&&existing.dataset.rasaiOutlineVersion==='2') return existing;
    if(existing) existing.remove();
    const consolidated=isConsolidated();
    const headings=Array.from(main.querySelectorAll('h2')).filter(h=>stableText(h).trim()&&headingEligible(h));
    if(headings.length<3) return null;
    const used=new Set(Array.from(document.querySelectorAll('[id]')).map(el=>el.id));
    headings.forEach((heading,index)=>{
      if(!heading.id){let base='rasai-'+slug(stableText(heading)),id=base,n=2;while(used.has(id)){id=base+'-'+n++;}heading.id=id;used.add(id);}
      heading.classList.add('rasai-section-anchor');
    });
    const nav=document.createElement('nav');nav.className='rasai-report-outline'+(consolidated?' rasai-report-outline-legacy':'');nav.dataset.rasaiOutlineVersion='2';nav.setAttribute('aria-label','Seções do relatório');
    const title=document.createElement('strong');title.textContent='Neste relatório';nav.appendChild(title);
    const links=document.createElement('div');links.className='rasai-report-outline-links';
    headings.forEach(heading=>{const a=document.createElement('a');a.href='#'+heading.id;a.textContent=stableText(heading).trim();links.appendChild(a)});nav.appendChild(links);
    const hero=main.querySelector(':scope > .hero, :scope > header');
    if(hero&&hero.parentNode===main)hero.insertAdjacentElement('afterend',nav);else main.insertBefore(nav,main.firstChild);
    return nav;
  };
  const appendGlobalSupport=(status,selector,label)=>{
    const node=document.querySelector(selector); if(!node||node.closest('.rasai-analysis-status')) return;
    let host=status.querySelector('.rasai-analysis-status-support');
    if(!host){host=document.createElement('div');host.className='rasai-analysis-status-support';status.appendChild(host);}
    const details=document.createElement('details');details.className='rasai-analysis-status-detail';
    const summary=document.createElement('summary');summary.textContent=label;details.appendChild(summary);details.appendChild(node);host.appendChild(details);
  };
  const normalizeReportStructure=outline=>{
    if(isConsolidated()) return;
    const main=document.querySelector('main'); if(!main) return;
    const hero=main.querySelector(':scope > .hero, :scope > header');
    if(hero&&main.firstElementChild!==hero) main.insertBefore(hero,main.firstElementChild);
    if(outline&&hero&&outline.previousElementSibling!==hero) hero.insertAdjacentElement('afterend',outline);
    const anchor=outline||hero;
    const fulfillment=document.querySelector('.rasai-fulfillment-banner');
    if(fulfillment&&anchor){anchor.insertAdjacentElement('afterend',fulfillment);}
    else if(fulfillment&&fulfillment.parentNode!==main){main.insertBefore(fulfillment,main.firstChild);}
    const status=document.querySelector('.rasai-analysis-status[data-rasai-analysis-status="true"]');
    if(!status) return;
    const statusAnchor=fulfillment&&fulfillment.parentNode===main?fulfillment:(outline&&outline.parentNode===main?outline:hero);
    if(statusAnchor&&status.previousElementSibling!==statusAnchor) statusAnchor.insertAdjacentElement('afterend',status);
    else if(status.parentNode!==main) main.insertBefore(status,main.firstChild);
    const dependency=document.querySelector('.report-dependency-state[data-report-dependency-state="true"]');
    if(dependency&&!dependency.closest('.rasai-analysis-status')) status.appendChild(dependency);
    appendGlobalSupport(status,'section.notice[data-audit-limitations="true"]','Limitações desta auditoria');
    appendGlobalSupport(status,'section.notice[data-ai-operational-diagnostic="true"]','Diagnóstico operacional de IA');
    const transparency=document.querySelector('.rasai-page-transparency[data-rasai-page-help-trigger="true"]');
    if(transparency){
      const button=transparency.querySelector('.rasai-help-open');
      if(button){
        let actions=status.querySelector('.rasai-analysis-status-actions');
        if(!actions){actions=document.createElement('div');actions.className='rasai-analysis-status-actions';actions.setAttribute('aria-label','Ações e transparência desta análise');status.appendChild(actions);}
        const description=transparency.querySelector('p');if(description&&description.textContent&&!button.getAttribute('title'))button.setAttribute('title',description.textContent.trim());
        actions.appendChild(button);
      }
      transparency.remove();
    }
  };
  const groupPopulationCards=()=>{
    const parents=new Set();
    document.querySelectorAll('.population-card').forEach(card=>{if(card.parentElement) parents.add(card.parentElement);});
    parents.forEach(parent=>{
      if(parent.querySelector(':scope > .rasai-population-grid')) return;
      const cards=Array.from(parent.children).filter(el=>el.classList&&el.classList.contains('population-card'));
      if(cards.length<2) return;
      const grid=document.createElement('div');grid.className='rasai-population-grid';grid.dataset.rasaiPopulationGrid='true';
      parent.insertBefore(grid,cards[0]);cards.forEach(card=>grid.appendChild(card));
    });
  };
  function toolbar(total,contexts,urls,onChange){
    const root=document.createElement('div');root.className='rasai-list-toolbar';root.dataset.rasaiListToolbar='true';
    const searchLabel=document.createElement('label');searchLabel.textContent='Buscar na lista';
    const search=document.createElement('input');search.type='search';search.placeholder='URL, regra, status, texto...';search.setAttribute('aria-label','Buscar na lista');searchLabel.appendChild(search);root.appendChild(searchLabel);
    let urlSelect=null;
    if(urls.length>=URL_THRESHOLD){
      const label=document.createElement('label');label.textContent='URL';
      urlSelect=document.createElement('select');urlSelect.dataset.rasaiUrlFilter='true';urlSelect.setAttribute('aria-label','Filtrar URL');
      urlSelect.innerHTML='<option value="">Todas as URLs ('+urls.length+')</option>'+urls.map(()=>'<option></option>').join('');
      Array.from(urlSelect.options).slice(1).forEach((option,index)=>{option.value=urls[index];option.textContent=urls[index];});label.appendChild(urlSelect);root.appendChild(label);
    }
    let context=null;
    if(contexts.length>1){
      const label=document.createElement('label');label.textContent='Contexto';
      context=document.createElement('select');context.setAttribute('aria-label','Filtrar contexto');
      context.innerHTML='<option value="">Todos</option>'+contexts.map(v=>'<option value="'+v+'">'+v+'</option>').join('');label.appendChild(context);root.appendChild(label);
    }
    const sizeLabel=document.createElement('label');sizeLabel.textContent='Itens por página';
    const size=document.createElement('select');size.setAttribute('aria-label','Itens por página');
    size.innerHTML='<option value="10">10</option><option value="25">25</option><option value="50">50</option><option value="0">Todos</option>';size.value=total>10?'10':'25';sizeLabel.appendChild(size);root.appendChild(sizeLabel);
    const prev=document.createElement('button');prev.type='button';prev.textContent='Anterior';root.appendChild(prev);
    const next=document.createElement('button');next.type='button';next.textContent='Próxima';root.appendChild(next);
    const status=document.createElement('span');status.className='rasai-list-status';root.appendChild(status);
    const state={page:1,query:'',url:'',context:'',size:Number(size.value)};
    const emit=()=>onChange(state,{prev,next,status});
    search.addEventListener('input',()=>{state.query=normalize(search.value.trim());state.page=1;emit();});
    if(urlSelect)urlSelect.addEventListener('change',()=>{state.url=urlSelect.value;state.page=1;emit();});
    if(context)context.addEventListener('change',()=>{state.context=context.value;state.page=1;emit();});
    size.addEventListener('change',()=>{state.size=Number(size.value);state.page=1;emit();});
    prev.addEventListener('click',()=>{if(state.page>1){state.page--;emit();}});next.addEventListener('click',()=>{state.page++;emit();});
    return {root,state,emit};
  }
  function apply(items,state,controls,displayMode){
    const filtered=items.filter(item=>{const indexed=indexForItem(item);if(state.query&&!indexed.text.includes(state.query))return false;if(state.url&&!indexed.urls.includes(state.url))return false;if(state.context&&!indexed.upper.includes(state.context))return false;return true;});
    const pageSize=state.size||Math.max(filtered.length,1),pages=Math.max(1,Math.ceil(filtered.length/pageSize));if(state.page>pages)state.page=pages;
    const start=(state.page-1)*pageSize,end=state.size?start+pageSize:filtered.length,visible=new Set(filtered.slice(start,end));
    items.forEach(item=>{const show=visible.has(item);item.classList.toggle('rasai-client-hidden',!show);item.style.display=show?displayMode:'none';});
    controls.prev.disabled=state.page<=1;controls.next.disabled=state.page>=pages;controls.status.textContent=filtered.length+' de '+items.length+' item(ns) · página '+state.page+' de '+pages;return filtered.length;
  }
  const outline=buildOutline();
  normalizeReportStructure(outline);
  groupPopulationCards();
  document.querySelectorAll('table').forEach(table=>{
    if(table.dataset.rasaiNoPagination==='true'||table.dataset.rasaiListReady==='true')return;
    const tbody=table.tBodies&&table.tBodies[0];if(!tbody)return;const rows=Array.from(tbody.rows);if(!shouldEnhance(rows,LARGE_TABLE_FALLBACK))return;
    table.dataset.rasaiListReady='true';const urls=urlsFor(rows),ui=toolbar(rows.length,contextsFor(rows),urls,(state,controls)=>{const count=apply(rows,state,controls,'table-row');empty.style.display=count?'none':'block';});
    const host=table.closest('.table-wrap')||table;host.parentNode.insertBefore(ui.root,host);const empty=document.createElement('div');empty.className='rasai-list-empty';empty.textContent='Nenhum item corresponde aos filtros atuais.';empty.style.display='none';host.parentNode.insertBefore(empty,host.nextSibling);ui.emit();
  });
  const parents=new Set();document.querySelectorAll('.page-card').forEach(card=>{if(card.parentElement)parents.add(card.parentElement);});
  parents.forEach(parent=>{
    if(parent.dataset.rasaiCardListReady==='true')return;const cards=Array.from(parent.children).filter(el=>el.classList&&el.classList.contains('page-card'));if(!shouldEnhance(cards,LARGE_CARD_FALLBACK))return;
    parent.dataset.rasaiCardListReady='true';const first=cards[0],urls=urlsFor(cards);const ui=toolbar(cards.length,contextsFor(cards),urls,(state,controls)=>{const count=apply(cards,state,controls,'');empty.style.display=count?'none':'block';});
    parent.insertBefore(ui.root,first);const empty=document.createElement('div');empty.className='rasai-list-empty';empty.textContent='Nenhum cartão corresponde aos filtros atuais.';empty.style.display='none';parent.insertBefore(empty,first);ui.emit();
  });
})();
</script>
""".strip()


def enhance_report_html_for_scale(html: str) -> str:
    """Inject consistent report navigation and scalable list UX, idempotently."""
    if _STYLE_MARKER not in html:
        if "</head>" in html:
            html = html.replace("</head>", _SCALE_CSS + "</head>", 1)
        else:
            html = _SCALE_CSS + html
    if _SCRIPT_MARKER not in html:
        if "</body>" in html:
            html = html.replace("</body>", _SCALE_SCRIPT + "</body>", 1)
        else:
            html += _SCALE_SCRIPT
    return html


def enhance_report_directory(report_dir: Path) -> None:
    """Apply the common UX layer to every generated HTML report page."""
    for path in sorted(report_dir.glob("*.html")):
        html = path.read_text(encoding="utf-8")
        enhanced = enhance_report_html_for_scale(html)
        if enhanced != html:
            path.write_text(enhanced, encoding="utf-8", newline="\n")

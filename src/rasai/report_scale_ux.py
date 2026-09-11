"""Shared client-side UX for report surfaces with multiple audited URLs/items.

One URL keeps the compact report layout. From two distinct URLs onward, URL/device
filters become available. Large non-URL lists also receive the same controls as a safety
fallback. The generated report remains a self-contained static artifact: no row/card is
removed from HTML and no score changes.
"""
from __future__ import annotations

from pathlib import Path


_STYLE_MARKER = "rasai-scale-ux-v1"
_SCRIPT_MARKER = "rasai-scale-ux-script-v1"

_SCALE_CSS = r"""
<style id="rasai-scale-ux-v1">
.rasai-list-toolbar{display:flex;flex-wrap:wrap;align-items:end;gap:9px;margin:14px 0;padding:12px;border:1px solid var(--line,rgba(111,123,141,.16));border-radius:7px;background:#f8f9fb}
.rasai-list-toolbar label{display:grid;gap:4px;min-width:150px;color:var(--muted,#6f7b8d);font-size:.76rem;font-weight:620}
.rasai-list-toolbar input,.rasai-list-toolbar select,.rasai-list-toolbar button{min-height:34px;border:1px solid var(--line,rgba(111,123,141,.22));border-radius:5px;background:#fff;color:var(--ink,#273449);padding:6px 9px;font:inherit}
.rasai-list-toolbar input{min-width:min(330px,70vw)}
.rasai-list-toolbar select[data-rasai-url-filter]{max-width:min(520px,80vw)}
.rasai-list-toolbar button{cursor:pointer;font-weight:620}.rasai-list-toolbar button:disabled{cursor:default;opacity:.45}
.rasai-list-toolbar .rasai-list-status{margin-left:auto;align-self:center;color:var(--muted,#6f7b8d);font-size:.8rem;white-space:nowrap}
.rasai-list-empty{padding:14px;border:1px dashed var(--line,rgba(111,123,141,.22));border-radius:6px;color:var(--muted,#6f7b8d);background:#fafbfc}
@media(max-width:760px){.rasai-list-toolbar{align-items:stretch}.rasai-list-toolbar label{min-width:100%}.rasai-list-toolbar input,.rasai-list-toolbar select{min-width:0;width:100%;max-width:none}.rasai-list-toolbar .rasai-list-status{margin-left:0;width:100%}}
@media print{.rasai-list-toolbar,.rasai-list-empty{display:none!important}.rasai-client-hidden{display:table-row!important}.page-card.rasai-client-hidden{display:block!important}}
</style>
""".strip()

_SCALE_SCRIPT = r"""
<script id="rasai-scale-ux-script-v1">
(function(){
  'use strict';
  const URL_THRESHOLD=2, LARGE_TABLE_FALLBACK=25, LARGE_CARD_FALLBACK=20;
  const normalize=v=>(v||'').toLocaleLowerCase('pt-BR');
  // textContent is intentionally used instead of innerText. innerText becomes empty for
  // rows/cards hidden by pagination, which made subsequent URL filters lose their data.
  const stableText=item=>String((item&&item.textContent)||'');
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
    if(item.querySelectorAll){
      item.querySelectorAll('.page-url').forEach(node=>values.push(...urlsInText(node.textContent||'')));
    }
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
  function toolbar(total, contexts, urls, onChange){
    const root=document.createElement('div'); root.className='rasai-list-toolbar'; root.dataset.rasaiListToolbar='true';
    const searchLabel=document.createElement('label'); searchLabel.textContent='Buscar na lista';
    const search=document.createElement('input'); search.type='search'; search.placeholder='URL, regra, status, texto...'; search.setAttribute('aria-label','Buscar na lista'); searchLabel.appendChild(search); root.appendChild(searchLabel);
    let urlSelect=null;
    if(urls.length>=URL_THRESHOLD){
      const label=document.createElement('label'); label.textContent='URL';
      urlSelect=document.createElement('select'); urlSelect.dataset.rasaiUrlFilter='true'; urlSelect.setAttribute('aria-label','Filtrar URL');
      urlSelect.innerHTML='<option value="">Todas as URLs ('+urls.length+')</option>'+urls.map(()=>'<option></option>').join('');
      Array.from(urlSelect.options).slice(1).forEach((option,index)=>{option.value=urls[index];option.textContent=urls[index];});
      label.appendChild(urlSelect); root.appendChild(label);
    }
    let context=null;
    if(contexts.length>1){
      const label=document.createElement('label'); label.textContent='Contexto';
      context=document.createElement('select'); context.setAttribute('aria-label','Filtrar contexto');
      context.innerHTML='<option value="">Todos</option>'+contexts.map(v=>'<option value="'+v+'">'+v+'</option>').join(''); label.appendChild(context); root.appendChild(label);
    }
    const sizeLabel=document.createElement('label'); sizeLabel.textContent='Itens por página';
    const size=document.createElement('select'); size.setAttribute('aria-label','Itens por página');
    size.innerHTML='<option value="10">10</option><option value="25">25</option><option value="50">50</option><option value="0">Todos</option>'; size.value=total>10?'10':'25'; sizeLabel.appendChild(size); root.appendChild(sizeLabel);
    const prev=document.createElement('button'); prev.type='button'; prev.textContent='Anterior'; root.appendChild(prev);
    const next=document.createElement('button'); next.type='button'; next.textContent='Próxima'; root.appendChild(next);
    const status=document.createElement('span'); status.className='rasai-list-status'; root.appendChild(status);
    const state={page:1,query:'',url:'',context:'',size:Number(size.value)};
    const emit=()=>onChange(state,{prev,next,status});
    search.addEventListener('input',()=>{state.query=normalize(search.value.trim());state.page=1;emit();});
    if(urlSelect) urlSelect.addEventListener('change',()=>{state.url=urlSelect.value;state.page=1;emit();});
    if(context) context.addEventListener('change',()=>{state.context=context.value;state.page=1;emit();});
    size.addEventListener('change',()=>{state.size=Number(size.value);state.page=1;emit();});
    prev.addEventListener('click',()=>{if(state.page>1){state.page--;emit();}});
    next.addEventListener('click',()=>{state.page++;emit();});
    return {root,state,emit};
  }
  function apply(items,state,controls,displayMode){
    const filtered=items.filter(item=>{
      const indexed=indexForItem(item);
      if(state.query && !indexed.text.includes(state.query)) return false;
      if(state.url && !indexed.urls.includes(state.url)) return false;
      if(state.context && !indexed.upper.includes(state.context)) return false;
      return true;
    });
    const pageSize=state.size||Math.max(filtered.length,1), pages=Math.max(1,Math.ceil(filtered.length/pageSize));
    if(state.page>pages) state.page=pages;
    const start=(state.page-1)*pageSize, end=state.size?start+pageSize:filtered.length;
    const visible=new Set(filtered.slice(start,end));
    items.forEach(item=>{
      const show=visible.has(item);
      item.classList.toggle('rasai-client-hidden',!show);
      item.style.display=show?displayMode:'none';
    });
    controls.prev.disabled=state.page<=1; controls.next.disabled=state.page>=pages;
    controls.status.textContent=filtered.length+' de '+items.length+' item(ns) · página '+state.page+' de '+pages;
    return filtered.length;
  }
  document.querySelectorAll('table').forEach(table=>{
    if(table.dataset.rasaiNoPagination==='true' || table.dataset.rasaiListReady==='true') return;
    const tbody=table.tBodies&&table.tBodies[0]; if(!tbody) return;
    const rows=Array.from(tbody.rows); if(!shouldEnhance(rows,LARGE_TABLE_FALLBACK)) return;
    table.dataset.rasaiListReady='true';
    const urls=urlsFor(rows), ui=toolbar(rows.length,contextsFor(rows),urls,(state,controls)=>{
      const count=apply(rows,state,controls,'table-row'); empty.style.display=count?'none':'block';
    });
    const host=table.closest('.table-wrap')||table; host.parentNode.insertBefore(ui.root,host);
    const empty=document.createElement('div'); empty.className='rasai-list-empty'; empty.textContent='Nenhum item corresponde aos filtros atuais.'; empty.style.display='none'; host.parentNode.insertBefore(empty,host.nextSibling);
    ui.emit();
  });
  const parents=new Set();
  document.querySelectorAll('.page-card').forEach(card=>{if(card.parentElement) parents.add(card.parentElement);});
  parents.forEach(parent=>{
    if(parent.dataset.rasaiCardListReady==='true') return;
    const cards=Array.from(parent.children).filter(el=>el.classList&&el.classList.contains('page-card'));
    if(!shouldEnhance(cards,LARGE_CARD_FALLBACK)) return;
    parent.dataset.rasaiCardListReady='true';
    const first=cards[0], urls=urlsFor(cards);
    const ui=toolbar(cards.length,contextsFor(cards),urls,(state,controls)=>{
      const count=apply(cards,state,controls,''); empty.style.display=count?'none':'block';
    });
    parent.insertBefore(ui.root,first);
    const empty=document.createElement('div'); empty.className='rasai-list-empty'; empty.textContent='Nenhum cartão corresponde aos filtros atuais.'; empty.style.display='none'; parent.insertBefore(empty,first);
    ui.emit();
  });
})();
</script>
""".strip()


def enhance_report_html_for_scale(html: str) -> str:
    """Inject scalable navigation UX into one HTML page, idempotently."""
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
    """Apply the scalable UX to all generated HTML report pages."""
    for path in sorted(report_dir.glob("*.html")):
        html = path.read_text(encoding="utf-8")
        enhanced = enhance_report_html_for_scale(html)
        if enhanced != html:
            path.write_text(enhanced, encoding="utf-8", newline="\n")

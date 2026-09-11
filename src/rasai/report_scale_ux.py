"""Shared client-side UX for report surfaces with many URLs/items.

The generated report remains a self-contained static artifact. This module never removes
rows/cards from HTML and never changes scoring. It only injects a small local controller
that filters/paginates large collections in the browser.
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
.rasai-list-toolbar button{cursor:pointer;font-weight:620}.rasai-list-toolbar button:disabled{cursor:default;opacity:.45}
.rasai-list-toolbar .rasai-list-status{margin-left:auto;align-self:center;color:var(--muted,#6f7b8d);font-size:.8rem;white-space:nowrap}
.rasai-list-empty{padding:14px;border:1px dashed var(--line,rgba(111,123,141,.22));border-radius:6px;color:var(--muted,#6f7b8d);background:#fafbfc}
@media(max-width:760px){.rasai-list-toolbar{align-items:stretch}.rasai-list-toolbar label{min-width:100%}.rasai-list-toolbar input{min-width:0;width:100%}.rasai-list-toolbar .rasai-list-status{margin-left:0;width:100%}}
@media print{.rasai-list-toolbar,.rasai-list-empty{display:none!important}.rasai-client-hidden{display:table-row!important}.page-card.rasai-client-hidden{display:block!important}}
</style>
""".strip()

_SCALE_SCRIPT = r"""
<script id="rasai-scale-ux-script-v1">
(function(){
  'use strict';
  const MIN_TABLE_ROWS=15, MIN_CARDS=10;
  const normalize=v=>(v||'').toLocaleLowerCase('pt-BR');
  const contextsFor=items=>{
    const joined=items.map(x=>(x.innerText||'').toUpperCase()).join('\n');
    const out=[];
    if(/\bMOBILE\b/.test(joined)) out.push('MOBILE');
    if(/\bDESKTOP\b/.test(joined)) out.push('DESKTOP');
    return out;
  };
  function toolbar(total, contexts, onChange){
    const root=document.createElement('div'); root.className='rasai-list-toolbar'; root.dataset.rasaiListToolbar='true';
    const searchLabel=document.createElement('label'); searchLabel.textContent='Buscar na lista';
    const search=document.createElement('input'); search.type='search'; search.placeholder='URL, regra, status, texto...'; search.setAttribute('aria-label','Buscar na lista'); searchLabel.appendChild(search); root.appendChild(searchLabel);
    let context=null;
    if(contexts.length>1){
      const label=document.createElement('label'); label.textContent='Contexto';
      context=document.createElement('select'); context.setAttribute('aria-label','Filtrar contexto');
      context.innerHTML='<option value="">Todos</option>'+contexts.map(v=>'<option value="'+v+'">'+v+'</option>').join(''); label.appendChild(context); root.appendChild(label);
    }
    const sizeLabel=document.createElement('label'); sizeLabel.textContent='Itens por página';
    const size=document.createElement('select'); size.setAttribute('aria-label','Itens por página');
    size.innerHTML='<option value="10">10</option><option value="25">25</option><option value="50">50</option><option value="0">Todos</option>'; size.value=total>25?'10':'25'; sizeLabel.appendChild(size); root.appendChild(sizeLabel);
    const prev=document.createElement('button'); prev.type='button'; prev.textContent='Anterior'; root.appendChild(prev);
    const next=document.createElement('button'); next.type='button'; next.textContent='Próxima'; root.appendChild(next);
    const status=document.createElement('span'); status.className='rasai-list-status'; root.appendChild(status);
    const state={page:1,query:'',context:'',size:Number(size.value)};
    const emit=()=>onChange(state,{prev,next,status});
    search.addEventListener('input',()=>{state.query=normalize(search.value.trim());state.page=1;emit();});
    if(context) context.addEventListener('change',()=>{state.context=context.value;state.page=1;emit();});
    size.addEventListener('change',()=>{state.size=Number(size.value);state.page=1;emit();});
    prev.addEventListener('click',()=>{if(state.page>1){state.page--;emit();}});
    next.addEventListener('click',()=>{state.page++;emit();});
    return {root,state,emit};
  }
  function apply(items,state,controls,displayMode){
    const filtered=items.filter(item=>{
      const text=normalize(item.innerText||'');
      if(state.query && !text.includes(state.query)) return false;
      if(state.context && !(item.innerText||'').toUpperCase().includes(state.context)) return false;
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
    const rows=Array.from(tbody.rows); if(rows.length<MIN_TABLE_ROWS) return;
    table.dataset.rasaiListReady='true';
    const ui=toolbar(rows.length,contextsFor(rows),(state,controls)=>{
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
    if(cards.length<MIN_CARDS) return;
    parent.dataset.rasaiCardListReady='true';
    const first=cards[0];
    const ui=toolbar(cards.length,contextsFor(cards),(state,controls)=>{
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

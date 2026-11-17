(function(){
const $=(s,r=document)=>[...r.querySelectorAll(s)];
// ordenação por coluna
$('table').forEach(t=>{const ths=$('thead th',t);ths.forEach((th,i)=>{if(th.dataset.sort==='none')return;th.dataset.s=1;th.tabIndex=0;const go=()=>{const asc=th.getAttribute('aria-sort')!=='ascending';ths.forEach(x=>x.removeAttribute('aria-sort'));th.setAttribute('aria-sort',asc?'ascending':'descending');const b=t.tBodies[0],rows=[...b.rows];const v=r=>r.cells[i].innerText.trim();const n=s=>/^[+-]?(?:\d+(?:[.,]\d+)?)$/.test(s)?Number(s.replace(',','.')):NaN;rows.sort((a,c)=>{const x=v(a),y=v(c),nx=n(x),ny=n(y);const r=(!isNaN(nx)&&!isNaN(ny))?nx-ny:x.localeCompare(y,'pt-BR');return asc?r:-r});rows.forEach(r=>b.appendChild(r))};th.addEventListener('click',go);th.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();go()}})})});
// filtro em tabelas longas
$('table').filter(t=>t.tBodies[0].rows.length>8).forEach(t=>{const w=t.closest('.tw'),bar=document.createElement('div');bar.className='tools';bar.innerHTML='<input type="search" placeholder="Filtrar esta tabela" aria-label="Filtrar tabela"><span></span>';w.before(bar);const inp=bar.querySelector('input'),out=bar.querySelector('span'),rows=[...t.tBodies[0].rows];const run=()=>{const k=inp.value.toLowerCase();let c=0;rows.forEach(r=>{const m=r.innerText.toLowerCase().includes(k);r.hidden=!m;if(m)c++});out.textContent=k?c+' de '+rows.length+' linhas':rows.length+' linhas'};inp.addEventListener('input',run);run()});
// expandir/recolher tudo
const eb=document.getElementById('expand');if(eb){let open=false;eb.addEventListener('click',()=>{open=!open;$('main details').forEach(d=>d.open=open);eb.textContent=open?'Recolher detalhes':'Expandir detalhes'})}
// índice lateral com destaque da seção atual
const links=$('.rail a');if(links.length&&'IntersectionObserver'in window){const map=new Map(links.map(a=>[a.getAttribute('href').slice(1),a]));const io=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting){links.forEach(l=>l.classList.remove('on'));map.get(e.target.id)?.classList.add('on')}})},{rootMargin:'0px 0px -75% 0px'});$('article h2').forEach(h=>io.observe(h))}
})();

// Bind finite normalized widths without inline script or stylesheet attributes.
document.querySelectorAll('[data-width]').forEach(e=>{const n=Number(e.dataset.width);if(Number.isFinite(n))e.style.width=Math.max(0,Math.min(100,n))+'%'});
document.querySelectorAll('.mk[data-position]').forEach(e=>{const n=Number(e.dataset.position);if(Number.isFinite(n))e.style.left=Math.max(0,Math.min(100,n))+'%'});
// Persist the reader's choice throughout the 11 HTML pages, including file://.
// Browser localStorage under file:// is implementation-dependent: the URL
// parameter is the authoritative handoff for navigation inside this report.
(function(){
  const key='rasai.report-presentation.theme';
  const param='rasai_theme';
  const valid=value=>value==='dark'||value==='light';
  const root=new URL('.',location.href);
  const chosen=new URL(location.href).searchParams.get(param);
  let stored=null;
  try{stored=localStorage.getItem(key)}catch(_){/* file:// may deny storage */}
  function rewriteLocalLinks(theme){
    document.querySelectorAll('a[href]').forEach(link=>{
      const raw=link.getAttribute('href');
      if(!raw||raw.startsWith('#'))return;
      let target;
      try{target=new URL(raw,location.href)}catch(_){return}
      if(target.protocol!==root.protocol||target.host!==root.host
          ||!target.pathname.startsWith(root.pathname))return;
      const file=target.pathname.slice(root.pathname.length);
      // Never modify cross-report links, asset paths, hashes or evidence URLs.
      if(!/^[^/]+\.html?$/i.test(file))return;
      target.searchParams.set(param,theme);
      link.href=target.href;
    });
  }
  function apply(theme){
    document.body.classList.toggle('dark',theme==='dark');
    document.body.classList.toggle('light',theme==='light');
    try{localStorage.setItem(key,theme)}catch(_){/* optional preference */}
    try{
      const here=new URL(location.href);
      here.searchParams.set(param,theme);
      history.replaceState(history.state,'',here.href);
    }catch(_){/* file:// history policy differs between browsers */}
    rewriteLocalLinks(theme);
  }
  if(valid(chosen))apply(chosen);
  else if(valid(stored))apply(stored);
  document.querySelector('#theme')?.addEventListener('click',()=>{
    const systemDark=window.matchMedia?.('(prefers-color-scheme: dark)').matches??false;
    const isDark=document.body.classList.contains('dark')
      ||(!document.body.classList.contains('light')&&systemDark);
    apply(isDark?'light':'dark');
  });
})();
function reveal(){const target=document.getElementById(decodeURIComponent(location.hash.slice(1)));if(!target)return;for(let p=target.parentElement;p;p=p.parentElement){if(p.tagName==='DETAILS')p.open=true}if(target.tagName==='DETAILS')target.open=true;target.scrollIntoView()}
window.addEventListener('hashchange',reveal);reveal();
let printState=[];window.addEventListener('beforeprint',()=>{printState=[...document.querySelectorAll('details')].map(d=>[d,d.open]);printState.forEach(([d])=>d.open=true)});window.addEventListener('afterprint',()=>printState.forEach(([d,open])=>d.open=open));

// modal de detalhamento contextual: dialog nativo, foco restaurado e sem navegação falsa
function closeDetailDialog(dialog){if(!dialog||!dialog.open)return;dialog.close()}
document.querySelectorAll('.modal-open').forEach(button=>button.addEventListener('click',()=>{const dialog=document.getElementById(button.dataset.modal);if(!dialog||typeof dialog.showModal!=='function')return;dialog._rasaiOpener=button;document.body.classList.add('modal-active');dialog.showModal();requestAnimationFrame(()=>dialog.querySelector('[data-modal-close]')?.focus())}));
document.querySelectorAll('dialog.detail-dialog').forEach(dialog=>{dialog.querySelectorAll('[data-modal-close]').forEach(button=>button.addEventListener('click',()=>closeDetailDialog(dialog)));dialog.querySelectorAll('a[href^="#"]').forEach(a=>a.addEventListener('click',()=>closeDetailDialog(dialog)));dialog.addEventListener('click',event=>{if(event.target===dialog)closeDetailDialog(dialog)});dialog.addEventListener('cancel',()=>{document.body.classList.remove('modal-active')});dialog.addEventListener('close',()=>{document.body.classList.remove('modal-active');const opener=dialog._rasaiOpener;if(opener&&opener.isConnected)opener.focus()})});

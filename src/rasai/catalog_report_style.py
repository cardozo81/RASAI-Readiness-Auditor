"""Catalog-driven HTML report projection.

This module owns only ``report-catalog/``. It is deliberately read-only: it projects
persisted AUD facts, artifacts and execution telemetry without invoking collectors,
providers, AI, scoring or external integrations.

Presentation rules:
* CAT pages preserve the same section grammar and shared visual components.
* Primary copy uses human-facing labels; physical table/field names stay in technical
  provenance only.
* Modals are contextual and atomic: a trigger opens details for exactly the item clicked.
* Observed/collected facts stay separate from AI interpretation and remediation.
* Cross-catalog dependencies are references, not duplicated blocks of data.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable, Mapping, Sequence

from rasai.audit_catalog import CATALOGS, CATALOG_BY_ID
from rasai.audit_configuration_reuse import configuration_hash
from rasai.catalog_report_contract import (
    CATALOG_PAGE_BY_ID,
    CATALOG_REPORT_CONTRACT_VERSION,
    CATALOG_REPORT_DIR,
    CATALOG_REPORT_PAGES,
    CatalogReportPage,
)


_CSS = r"""
:root{--nav:286px;--bg:#f6f8fb;--card:#fff;--ink:#172033;--muted:#667085;--line:#e2e7ef;--blue:#3157c8;--green:#187a45;--amber:#9a6200;--red:#b42318;--cyan:#087a8c;--radius:14px;--shadow:0 1px 3px rgba(16,24,40,.06)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}a{color:var(--blue)}
.app-nav{position:fixed;inset:0 auto 0 0;width:var(--nav);overflow:auto;padding:20px 14px;background:#111827;color:#d6dfeb}.brand{padding:0 9px 15px;border-bottom:1px solid #2b3547;margin-bottom:12px}.brand small{display:block;color:#93a4ba;text-transform:uppercase;letter-spacing:.1em;font-size:.68rem}.brand strong{display:block;color:#fff;margin-top:4px}.nav-group{margin:14px 9px 5px;color:#8798ae;font-size:.66rem;text-transform:uppercase;letter-spacing:.1em}.app-nav a{display:block;color:#cbd5e1;text-decoration:none;padding:8px 10px;margin:3px 0;border-radius:8px;font-size:.82rem}.app-nav a:hover,.app-nav a:focus,.app-nav a.active{background:#253146;color:#fff}
.app-main{margin-left:var(--nav);width:calc(100% - var(--nav));max-width:1500px;padding:28px 34px 60px}.hero,.panel,.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}.hero{padding:24px 26px;margin-bottom:16px}.hero .eyebrow,.kicker{font-size:.7rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);font-weight:700}.hero h1{font-size:clamp(1.7rem,2.3vw,2.3rem);line-height:1.15;margin:.28rem 0 .6rem}.hero p{color:#4b5565;max-width:1000px}.panel{padding:19px 21px;margin:14px 0}.panel h2{font-size:1.26rem;margin:.15rem 0 .75rem}.panel h3{font-size:1rem;margin:.2rem 0 .55rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:11px}.card{padding:14px}.metric-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:9px}.metric{background:#fbfcfe;border:1px solid var(--line);border-radius:10px;padding:11px}.metric small{display:block;color:var(--muted);font-size:.7rem}.metric strong{display:block;margin-top:3px;overflow-wrap:anywhere}
.badge{display:inline-flex;align-items:center;border-radius:999px;padding:4px 8px;font-size:.68rem;font-weight:750;background:#eef1f5;color:#4b5565}.badge.good{background:#e9f7ee;color:var(--green)}.badge.warn{background:#fff3d7;color:#805200}.badge.bad{background:#feeceb;color:var(--red)}.badge.info{background:#eaf1ff;color:#244ea4}.badge.neutral{background:#eef0f3;color:#596274}
.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:10px;background:#fff}table{width:100%;border-collapse:collapse;font-size:.83rem}th,td{text-align:left;vertical-align:top;padding:9px 10px;border-bottom:1px solid #edf0f4}th{background:#f8fafc;color:#4b5565;text-transform:uppercase;letter-spacing:.03em;font-size:.69rem}tr:last-child td{border-bottom:0}table[data-sortable='true'] th{cursor:pointer;user-select:none}table[data-sortable='true'] th::after{content:' ↕';color:#98a2b3;font-weight:400}table[data-sortable='true'] th[data-sort-direction='asc']::after{content:' ↑';color:#344054}table[data-sortable='true'] th[data-sort-direction='desc']::after{content:' ↓';color:#344054}.table-controls{display:flex;align-items:center;justify-content:flex-end;gap:8px;margin-top:8px}.table-controls .table-page-info{color:var(--muted);font-size:.74rem;min-width:130px;text-align:center}.table-controls button{border:1px solid #bdc8da;background:#fff;color:#274690;border-radius:8px;padding:5px 9px;cursor:pointer}.table-controls button:disabled{opacity:.45;cursor:not-allowed}
.notice{border:1px solid #cbd8f5;background:#f2f6ff;border-radius:10px;padding:11px 13px;margin:10px 0}.notice.warn{border-color:#ecd09d;background:#fff8e9}.notice.bad{border-color:#efb7b2;background:#fff1f0}.notice.good{border-color:#b9dec5;background:#edf8f0}.muted{color:var(--muted)}.mono,code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}.outline{position:sticky;top:0;z-index:5;background:rgba(246,248,251,.96);backdrop-filter:blur(7px);padding:8px 0 10px;display:flex;gap:6px;overflow:auto}.outline a{white-space:nowrap;text-decoration:none;border:1px solid var(--line);background:#fff;border-radius:999px;padding:5px 9px;font-size:.72rem;color:#46536a}.catalog-state{display:flex;gap:10px;align-items:flex-start;justify-content:space-between}.source-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}.source-item{border:1px solid var(--line);border-radius:9px;padding:9px;background:#fbfcfe}.source-item small{display:block;color:var(--muted)}details{border:1px solid var(--line);border-radius:9px;background:#fbfcfd;margin:8px 0}summary{cursor:pointer;padding:9px 11px;font-weight:650}details>.detail-body{padding:0 11px 11px}
.action{display:inline-flex;align-items:center;justify-content:center;border:1px solid #bdc8da;background:#fff;color:#274690;border-radius:8px;padding:5px 8px;font:inherit;font-size:.75rem;cursor:pointer;text-decoration:none}.action:hover,.action:focus{background:#f2f6ff;border-color:#91a5ce}.ref{display:inline-flex;align-items:center;gap:4px;border-radius:999px;padding:3px 7px;background:#eef3fb;color:#345184;font-size:.7rem;text-decoration:none}.stack{display:grid;gap:8px}.section-lead{margin:.15rem 0 .8rem;color:#596274}.subsection{margin-top:14px}.subsection h3{margin-bottom:8px}.pill-list{display:flex;gap:6px;flex-wrap:wrap}.pre{white-space:pre-wrap;overflow:auto;max-height:52vh;background:#0f172a;color:#e2e8f0;border-radius:9px;padding:11px;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}.capture-preview{display:block;max-width:min(100%,820px);max-height:64vh;object-fit:contain;border:1px solid var(--line);border-radius:10px;background:#f8fafc;margin:8px auto}.capture-link{display:inline-flex;margin-top:6px}
dialog.rasai-modal{width:min(920px,calc(100vw - 32px));max-height:88vh;border:0;border-radius:14px;padding:0;box-shadow:0 22px 70px rgba(15,23,42,.32);color:var(--ink)}dialog.rasai-modal::backdrop{background:rgba(15,23,42,.56)}.modal-head{display:flex;gap:14px;align-items:flex-start;justify-content:space-between;padding:18px 20px;border-bottom:1px solid var(--line);background:#fbfcfe}.modal-head h2{margin:0;font-size:1.15rem}.modal-head p{margin:4px 0 0;color:var(--muted);font-size:.82rem}.modal-close{border:1px solid var(--line);background:#fff;border-radius:8px;padding:5px 9px;cursor:pointer}.modal-body{padding:18px 20px;overflow:auto;max-height:calc(88vh - 120px)}.modal-body h3{font-size:.92rem;margin:16px 0 6px}.modal-body h3:first-child{margin-top:0}.kv{display:grid;grid-template-columns:minmax(150px,220px) 1fr;border:1px solid var(--line);border-radius:9px;overflow:hidden;margin:8px 0}.kv dt,.kv dd{margin:0;padding:8px 10px;border-bottom:1px solid var(--line)}.kv dt{background:#f8fafc;color:#536076;font-size:.74rem;font-weight:700}.kv dd{overflow-wrap:anywhere}.kv dt:last-of-type,.kv dd:last-of-type{border-bottom:0}.footer{margin-top:24px;padding-top:14px;border-top:1px solid var(--line);color:var(--muted);font-size:.74rem}
@media(max-width:900px){.app-nav{position:sticky;top:0;width:auto;inset:auto;display:flex;gap:5px;overflow:auto;padding:8px;z-index:20}.brand,.nav-group{display:none}.app-nav nav{display:flex;min-width:max-content}.app-nav a{background:#253146;margin:0 2px}.app-main{margin:0;width:100%;padding:18px 12px 40px}.outline{top:47px}.kv{grid-template-columns:1fr}.kv dt{border-bottom:0;padding-bottom:2px}.kv dd{padding-top:2px}.table-controls{justify-content:space-between}}
@media print{body{background:#fff}.app-nav,.outline,.action,.rasai-modal,.table-controls{display:none!important}.app-main{margin:0;width:100%;max-width:none;padding:0}.hero,.panel,.card{box-shadow:none;break-inside:avoid}table[data-interactive-table] tbody tr{display:table-row!important}}
"""

_JS = r"""
(()=>{
const open=(id)=>{const el=document.getElementById(id);if(el&&typeof el.showModal==='function')el.showModal();};
document.addEventListener('click',(event)=>{const trigger=event.target.closest('[data-modal-open]');if(trigger){event.preventDefault();open(trigger.getAttribute('data-modal-open'));return;}const closer=event.target.closest('[data-modal-close]');if(closer){event.preventDefault();const dlg=closer.closest('dialog');if(dlg)dlg.close();}});
document.addEventListener('cancel',(event)=>{if(event.target.matches('dialog.rasai-modal'))event.target.close();});
document.addEventListener('click',(event)=>{const dlg=event.target;if(dlg instanceof HTMLDialogElement&&dlg.classList.contains('rasai-modal')){const rect=dlg.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)dlg.close();}});

const normalizeSortValue=(input)=>{
  const value=(input||'').trim();
  const localized=value.match(/^(\d{2})\/(\d{2})\/(\d{4})\s+(\d{2}):(\d{2}):(\d{2})/);
  if(localized)return `${localized[3]}-${localized[2]}-${localized[1]}T${localized[4]}:${localized[5]}:${localized[6]}`;
  const milliseconds=value.match(/^([+-]?[\d\s.,]+)\s*ms$/i);
  if(milliseconds){const numeric=Number(milliseconds[1].replace(/\s/g,'').replace(',','.'));if(Number.isFinite(numeric))return String(numeric);}
  const percent=value.match(/^([+-]?[\d\s.,]+)%$/);
  if(percent){const numeric=Number(percent[1].replace(/\s/g,'').replace(',','.'));if(Number.isFinite(numeric))return String(numeric);}
  return value;
};
const valueFor=(row,index)=>normalizeSortValue((row.cells[index]&&row.cells[index].innerText)||'');
document.querySelectorAll('table[data-interactive-table="true"]').forEach((table)=>{
  const tbody=table.tBodies[0]; if(!tbody)return;
  const original=Array.from(tbody.rows); let rows=original.slice(); let page=1; let sortIndex=-1; let sortDirection=1;
  const size=Math.max(0,Number.parseInt(table.dataset.pageSize||'0',10)||0);
  const sortable=table.dataset.sortable==='true';
  const wrap=table.closest('.table-wrap'); const controls=wrap&&wrap.nextElementSibling&&wrap.nextElementSibling.classList.contains('table-controls')?wrap.nextElementSibling:null;
  const info=controls?controls.querySelector('.table-page-info'):null; const prev=controls?controls.querySelector('[data-table-prev]'):null; const next=controls?controls.querySelector('[data-table-next]'):null;
  const render=()=>{
    original.forEach((row)=>{row.style.display='none';});
    const totalPages=size?Math.max(1,Math.ceil(rows.length/size)):1; page=Math.min(Math.max(page,1),totalPages);
    const start=size?(page-1)*size:0; const end=size?Math.min(start+size,rows.length):rows.length;
    rows.slice(start,end).forEach((row)=>{tbody.appendChild(row);row.style.display='table-row';});
    if(info)info.textContent=`Página ${page} de ${totalPages} · ${rows.length} registro(s)`;
    if(prev)prev.disabled=page<=1; if(next)next.disabled=page>=totalPages;
  };
  if(prev)prev.addEventListener('click',()=>{page-=1;render();});
  if(next)next.addEventListener('click',()=>{page+=1;render();});
  if(sortable&&table.tHead){Array.from(table.tHead.rows[0].cells).forEach((th,index)=>{
    th.tabIndex=0; th.setAttribute('role','button'); th.setAttribute('aria-label',`${th.innerText.trim()}: ordenar tabela`);
    const sort=()=>{sortDirection=sortIndex===index?-sortDirection:1;sortIndex=index;page=1;Array.from(table.tHead.rows[0].cells).forEach((cell)=>cell.removeAttribute('data-sort-direction'));th.setAttribute('data-sort-direction',sortDirection===1?'asc':'desc');rows.sort((a,b)=>valueFor(a,index).localeCompare(valueFor(b,index),'pt-BR',{numeric:true,sensitivity:'base'})*sortDirection);render();};
    th.addEventListener('click',sort);th.addEventListener('keydown',(event)=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();sort();}});
  });}
  render();
});
})();
"""

__all__ = [name for name in globals() if not name.startswith("__")]

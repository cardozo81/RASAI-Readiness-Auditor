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
:root{--nav:286px;--nav-bg:#0c2533;--nav-hover:#113444;--bg:#f3f6f6;--card:#fff;--ink:#142d3d;--secondary-ink:#445c69;--muted:#546c78;--light-muted:#596c76;--line:#e1e9e9;--blue:#3159a8;--green:#087a77;--amber:#875411;--orange:#94551e;--red:#b33b3b;--cyan:#087a77;--radius:14px;--shadow:0 1px 3px rgba(16,44,52,.07)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}a{color:var(--blue)}
.app-nav{position:fixed;inset:0 auto 0 0;width:var(--nav);overflow:auto;padding:20px 14px;background:var(--nav-bg);color:#d6dfeb}.brand{padding:0 9px 15px;border-bottom:1px solid #2b3547;margin-bottom:12px}.brand small{display:block;color:#93a4ba;text-transform:uppercase;letter-spacing:.1em;font-size:.68rem}.brand strong{display:block;color:#fff;margin-top:4px;font-size:.76rem;font-weight:600;line-height:1.35;overflow-wrap:anywhere}.nav-group{margin:14px 9px 5px;color:#8798ae;font-size:.66rem;text-transform:uppercase;letter-spacing:.1em}.app-nav a{display:block;color:#cbd5e1;text-decoration:none;padding:8px 10px;margin:3px 0;border-radius:8px;font-size:.82rem}.app-nav a:hover,.app-nav a:focus,.app-nav a.active{background:var(--nav-hover);color:#fff}.translation-mark{display:inline-flex;align-items:center;justify-content:center;margin-left:4px;font-size:.72em;cursor:help;opacity:.72;vertical-align:baseline}.external-link{overflow-wrap:anywhere;word-break:break-word}.external-link:hover,.external-link:focus{text-decoration-thickness:2px}
.app-main{margin-left:var(--nav);width:calc(100% - var(--nav));max-width:1500px;padding:28px 34px 60px}.hero,.panel,.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}.hero{padding:24px 26px;margin-bottom:16px}.hero .eyebrow{font-size:.66rem;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);font-weight:600}.kicker{font-size:.7rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);font-weight:700}.hero h1{font-size:clamp(1.7rem,2.3vw,2.3rem);line-height:1.15;margin:.28rem 0 .6rem}.hero p{color:#4b5565;max-width:1000px}.panel{padding:19px 21px;margin:14px 0}.panel h2{font-size:1.26rem;margin:.15rem 0 .75rem}.panel h3{font-size:1rem;margin:.2rem 0 .55rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:11px}.card{padding:14px}.metric-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:9px}.metric{background:#fbfcfe;border:1px solid var(--line);border-radius:10px;padding:11px}.metric small{display:block;color:var(--muted);font-size:.7rem}.metric strong{display:block;margin-top:3px;overflow-wrap:anywhere}
.badge{display:inline-flex;align-items:center;border-radius:999px;padding:4px 8px;font-size:.68rem;font-weight:750;background:#eef1f5;color:#4b5565}.badge.good{background:#e9f7ee;color:var(--green)}.badge.warn{background:#fff3d7;color:#805200}.badge.bad{background:#feeceb;color:var(--red)}.badge.info{background:#eaf1ff;color:#244ea4}.badge.neutral{background:#eef0f3;color:#596274}
.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:10px;background:#fff}table{width:100%;border-collapse:collapse;font-size:.83rem}th,td{text-align:left;vertical-align:top;padding:9px 10px;border-bottom:1px solid #edf0f4}td{color:var(--ink)}th{background:#f8fafc;color:#4b5565;text-transform:uppercase;letter-spacing:.03em;font-size:.69rem}tr:last-child td{border-bottom:0}table[data-sortable='true'] th{cursor:pointer;user-select:none}table[data-sortable='true'] th::after{content:' ↕';color:#98a2b3;font-weight:400}table[data-sortable='true'] th[data-sort-direction='asc']::after{content:' ↑';color:#344054}table[data-sortable='true'] th[data-sort-direction='desc']::after{content:' ↓';color:#344054}.table-controls{display:flex;align-items:center;justify-content:flex-end;gap:8px;margin-top:8px}.table-controls .table-page-info{color:var(--muted);font-size:.74rem;min-width:130px;text-align:center}.table-controls button{border:1px solid #bdc8da;background:#fff;color:#274690;border-radius:8px;padding:5px 9px;cursor:pointer}.table-controls button:disabled{opacity:.45;cursor:not-allowed}
.notice{border:1px solid #cbd8f5;background:#f2f6ff;border-radius:10px;padding:11px 13px;margin:10px 0}.notice.warn{border-color:#ecd09d;background:#fff8e9}.notice.bad{border-color:#efb7b2;background:#fff1f0}.notice.good{border-color:#b9dec5;background:#edf8f0}.notice.warn>strong{color:var(--amber)}.notice.bad>strong{color:var(--red)}.notice.good>strong{color:var(--green)}.state-text.good{color:var(--green)}.state-text.warn{color:var(--amber)}.state-text.bad{color:var(--red)}.state-text.neutral{color:var(--secondary-ink)}.metric strong>.state-text.neutral{font-weight:400}.result-value{font-weight:700;color:var(--ink)}.result-value.good{color:var(--green)}.result-value.warn{color:var(--amber)}.result-value.low{color:var(--orange)}.result-value.bad{color:var(--red)}.result-value.neutral{color:var(--ink)}.no-cost-value{color:var(--light-muted);font-weight:400}.muted{color:var(--muted)}.mono,code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}.outline{position:sticky;top:0;z-index:5;background:rgba(246,248,251,.96);backdrop-filter:blur(7px);padding:8px 0 10px;display:flex;gap:6px;overflow:auto}.outline a{white-space:nowrap;text-decoration:none;border:1px solid var(--line);background:#fff;border-radius:999px;padding:5px 9px;font-size:.72rem;color:#46536a}.catalog-state{display:flex;gap:10px;align-items:flex-start;justify-content:space-between}.source-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}.source-item{border:1px solid var(--line);border-radius:9px;padding:9px;background:#fbfcfe}.source-item small{display:block;color:var(--muted)}details{border:1px solid var(--line);border-radius:9px;background:#fbfcfd;margin:8px 0}summary{cursor:pointer;padding:9px 11px;font-weight:650}details>.detail-body{padding:0 11px 11px}
.action{display:inline-flex;align-items:center;justify-content:center;border:1px solid #bdc8da;background:#fff;color:#274690;border-radius:8px;padding:5px 8px;font:inherit;font-size:.75rem;cursor:pointer;text-decoration:none}.action:hover,.action:focus{background:#f2f6ff;border-color:#91a5ce}.ref{display:inline-flex;align-items:center;gap:4px;padding:3px 7px;background:#eef3fb;color:#345184;font-size:.7rem;text-decoration:none}.stack{display:grid;gap:8px}.section-lead{margin:.15rem 0 .8rem;color:#596274}.subsection{margin-top:14px}.subsection h3{margin-bottom:8px}.pill-list{display:flex;gap:6px;flex-wrap:wrap}.pre{white-space:pre-wrap;overflow:auto;max-height:52vh;background:#0f172a;color:#e2e8f0;border-radius:9px;padding:11px;font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}.capture-preview{display:block;max-width:min(100%,820px);max-height:64vh;object-fit:contain;border:1px solid var(--line);border-radius:10px;background:#f8fafc;margin:8px auto}.capture-link{display:inline-flex;margin-top:6px}
dialog.rasai-modal{width:min(920px,calc(100vw - 32px));max-height:88vh;border:0;border-radius:14px;padding:0;box-shadow:0 22px 70px rgba(15,23,42,.32);color:var(--ink)}dialog.rasai-modal::backdrop{background:rgba(15,23,42,.56)}.modal-head{display:flex;gap:14px;align-items:flex-start;justify-content:space-between;padding:18px 20px;border-bottom:1px solid var(--line);background:#fbfcfe}.modal-head h2{margin:0;font-size:1.15rem}.modal-head p{margin:4px 0 0;color:var(--muted);font-size:.82rem}.modal-close{border:1px solid var(--line);background:#fff;border-radius:8px;padding:5px 9px;cursor:pointer}.modal-body{padding:18px 20px;overflow:auto;max-height:calc(88vh - 120px);color:var(--ink)}.modal-body h2,.modal-body h3,.modal-body strong{color:var(--ink)}.modal-body .state-text.good{color:var(--green)}.modal-body .state-text.warn{color:var(--amber)}.modal-body .state-text.bad{color:var(--red)}.modal-body .result-value.good{color:var(--green)}.modal-body .result-value.warn{color:var(--amber)}.modal-body .result-value.low{color:var(--orange)}.modal-body .result-value.bad{color:var(--red)}.modal-body h3{font-size:.92rem;margin:16px 0 6px}.modal-body h3:first-child{margin-top:0}.kv{display:grid;grid-template-columns:minmax(150px,220px) 1fr;border:1px solid var(--line);border-radius:9px;overflow:hidden;margin:8px 0}.kv dt,.kv dd{margin:0;padding:8px 10px;border-bottom:1px solid var(--line)}.kv dt{background:#f8fafc;color:#536076;font-size:.74rem;font-weight:700}.kv dd{overflow-wrap:anywhere;color:var(--ink)}.kv dt:last-of-type,.kv dd:last-of-type{border-bottom:0}.footer{margin-top:24px;padding-top:14px;border-top:1px solid var(--line);color:var(--muted);font-size:.74rem}
/* #334: exclusive Directed Analysis roadmap; do not reflow shared CAT grids. */
.directed-roadmap-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.directed-roadmap-card{display:flex;flex-direction:column;min-width:0;overflow-wrap:anywhere;padding:17px 19px}
.directed-roadmap-card h3{margin:0 0 9px;font-size:1.04rem}
.directed-roadmap-objective{margin:0 0 13px;color:var(--secondary-ink);line-height:1.55;flex:1}
.directed-roadmap-counts{margin:0 0 13px;font-size:.82rem;color:var(--muted)}
.directed-roadmap-counts strong{color:var(--ink)}
.directed-roadmap-card-action{margin-top:auto}
.directed-roadmap-card-action .action{min-height:38px;padding:8px 12px}
#roadmap dialog.rasai-modal[id^='directed-roadmap-phase-'] .modal-body{overflow-wrap:anywhere}
.directed-roadmap-group{margin:10px 0}
.directed-roadmap-group summary{overflow-wrap:anywhere}
.directed-roadmap-occurrences{margin:0;padding:0 0 0 25px}
.directed-roadmap-occurrence{padding:9px 2px;overflow-wrap:anywhere;border-top:1px solid var(--line)}
.directed-roadmap-occurrence:first-child{border-top:0}
.directed-roadmap-occurrence .muted{margin:5px 0}
.directed-roadmap-references{margin:7px 0}
@media(max-width:1000px){.directed-roadmap-grid{grid-template-columns:minmax(0,1fr)}}
@media(max-width:900px){.app-nav{position:sticky;top:0;width:auto;inset:auto;display:flex;gap:5px;overflow:auto;padding:8px;z-index:20}.brand,.nav-group{display:none}.app-nav nav{display:flex;min-width:max-content}.app-nav a{background:#253146;margin:0 2px}.app-main{margin:0;width:100%;padding:18px 12px 40px}.outline{top:47px}.kv{grid-template-columns:1fr}.kv dt{border-bottom:0;padding-bottom:2px}.kv dd{padding-top:2px}.table-controls{justify-content:space-between}}
@media print{body{background:#fff}.app-nav,.outline,.action,.rasai-modal,.table-controls{display:none!important}.app-main{margin:0;width:100%;max-width:none;padding:0}.hero,.panel,.card{box-shadow:none;break-inside:avoid}table[data-interactive-table] tbody tr{display:table-row!important}}
/* The phase modal contains the only full list. Force it into print flow. */
@media print{
#roadmap .directed-roadmap-grid{display:none!important}
#roadmap dialog.rasai-modal[id^='directed-roadmap-phase-']{display:block!important;position:static!important;inset:auto!important;width:100%!important;max-height:none!important;margin:12px 0!important;padding:0!important;border:1px solid #bfc8d4;box-shadow:none!important;overflow:visible!important;break-inside:auto}
#roadmap dialog.rasai-modal[id^='directed-roadmap-phase-'] .modal-head{padding:9px 13px}
#roadmap dialog.rasai-modal[id^='directed-roadmap-phase-'] .modal-head .modal-close{display:none!important}
#roadmap dialog.rasai-modal[id^='directed-roadmap-phase-'] .modal-body{display:block!important;max-height:none!important;overflow:visible!important;padding:9px 13px}
#roadmap dialog.rasai-modal[id^='directed-roadmap-phase-'] details:not([open])>.detail-body{display:block!important}
#roadmap dialog.rasai-modal[id^='directed-roadmap-phase-'] details{break-inside:auto}
}

/* #633 shared navigation: mobile disclosure only when JS is available.
   Without JS every one of the canonical links remains visible. */
.report-skip-link{position:fixed;left:12px;top:-80px;z-index:200;background:#fff;color:var(--ink);padding:10px 14px;border:2px solid var(--cyan);border-radius:8px}
.report-skip-link:focus{top:10px}
.report-mobile-header{display:none}
.report-breadcrumbs{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:0 0 14px;color:var(--muted);font-size:.77rem}
.report-breadcrumbs a{color:var(--blue)}
.report-breadcrumbs .report-current-page{font-weight:650;color:var(--ink)}
:where(a,button,summary,[tabindex]):focus-visible{outline:3px solid #16938d;outline-offset:3px}
.app-nav :where(a,button):focus-visible{outline-color:#a2fff1}
@media(max-width:900px){
  .report-mobile-header{position:sticky;top:0;z-index:25;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:9px 14px;background:var(--nav-bg);color:#fff}
  .report-mobile-brand{font-size:.88rem;font-weight:750;color:#fff;text-decoration:none}
  .report-menu-button{border:1px solid #7d9caa;background:var(--nav-hover);border-radius:9px;color:#fff;padding:8px 14px;font:inherit;font-size:.8rem;cursor:pointer}
  .report-menu-button[aria-expanded='true']{background:#205366}
  .report-menu-enhanced .app-nav{display:none}
  .report-menu-enhanced.report-menu-open .app-nav{display:flex;top:49px;z-index:24}
}
@media print{
  .report-mobile-header,.report-skip-link{display:none!important}
  .report-breadcrumbs{font-size:9pt;margin:0 0 8mm;color:#303d45}
}

/* #633: objective index is an access path, never a replacement for action tables. */
.directed-goal-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,235px),1fr));gap:12px;margin:12px 0 20px}
.directed-goal-link{display:flex;flex-direction:column;align-items:flex-start;gap:6px;min-width:0;border-top:3px solid var(--cyan);text-decoration:none;color:var(--ink);transition:box-shadow .15s,border-color .15s}
.directed-goal-link:hover,.directed-goal-link:focus-visible{box-shadow:0 7px 24px rgba(12,37,51,.12);border-top-color:#065b59}
.directed-goal-name{font-weight:750;font-size:.92rem}
.directed-goal-link strong{font-size:1.8rem;line-height:1;color:var(--cyan);font-variant-numeric:tabular-nums}
.directed-goal-link small{color:var(--muted)}
.directed-goal-cta{margin-top:auto;padding-top:7px;color:var(--blue);font-weight:650;font-size:.77rem}
.directed-goal-details{scroll-margin-top:76px}
.directed-goal-details:target{border-color:var(--cyan);box-shadow:0 0 0 2px rgba(8,122,119,.12)}
.directed-goal-details .table-wrap{max-width:100%}
@media(max-width:900px){
  .report-menu-enhanced.report-menu-open::before{content:'';position:fixed;inset:0;background:rgba(7,27,39,.52);z-index:23}
  .report-menu-enhanced.report-menu-open .app-nav{display:block;position:fixed;top:49px;left:0;right:auto;bottom:0;width:min(360px,92vw);max-height:calc(100dvh - 49px);padding:18px 13px;overflow-y:auto;z-index:24;box-shadow:4px 12px 30px rgba(0,0,0,.24)}
  .report-menu-enhanced.report-menu-open .app-nav nav{display:block;min-width:0}
  .report-menu-enhanced.report-menu-open .brand,.report-menu-enhanced.report-menu-open .nav-group{display:block}
  .report-menu-enhanced.report-menu-open .app-nav a{margin:3px 0;padding:10px 12px}
  .report-menu-enhanced.report-menu-open body{overflow:hidden}
}
@media print{
  .directed-goal-grid{display:none}
  .directed-goal-details{break-inside:auto}
  .directed-goal-details:not([open])>.detail-body{display:block!important}
}

/* #633 real-AUD mobile capture context: long technical identifiers must wrap
   inside their card without expanding the document viewport. Preserve table
   overflow in .table-wrap and keep the full identifier selectable. */
.card .muted.mono{overflow-wrap:anywhere;word-break:break-word;white-space:normal}

/* #633 restrained analytical surfaces and reading order. */
:root{--radius:8px;--shadow:0 1px 2px rgba(12,37,51,.035);--line:#dce5e7;--bg:#f4f7f7;--nav-bg:#102f3d;--nav-hover:#1b4551}
.hero,.panel{border-radius:10px;box-shadow:none}
.card,.metric,.notice,details,.table-wrap{border-radius:7px;box-shadow:none}
.panel h2{letter-spacing:-.012em}
.card{border-left:1px solid var(--line)}
.directed-goal-link,.report-experience-card{border-top:1px solid var(--line)}
.report-reading-map{list-style:none;padding:0;margin:16px 0;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 22px;border-top:1px solid var(--line)}
.report-reading-step{display:grid;grid-template-columns:46px minmax(0,1fr);gap:12px;padding:22px 4px 24px;border-bottom:1px solid var(--line);min-width:0}
.report-reading-number{font-size:1rem;font-weight:750;font-variant-numeric:tabular-nums;color:var(--green);letter-spacing:.04em}
.report-reading-content{min-width:0}
.report-reading-content h3{font-size:1.05rem;margin:0 0 5px;color:var(--ink)}
.report-reading-content p{margin:0 0 13px;color:var(--secondary-ink);font-size:.87rem}
.report-reading-links{margin:0;padding-left:18px;display:grid;gap:8px}
.report-reading-links a{font-weight:600;overflow-wrap:anywhere}
@media(max-width:700px){.report-reading-map{grid-template-columns:minmax(0,1fr)}.report-reading-step{grid-template-columns:38px minmax(0,1fr);padding:18px 0}}
@media print{.report-reading-map{grid-template-columns:repeat(2,minmax(0,1fr))}.report-reading-step{break-inside:avoid}}

/* #633 objectives become a readable evidence index, not another card dashboard. */
.directed-goal-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 22px;border-top:1px solid var(--line)}
.directed-goal-link{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:4px 14px;padding:17px 2px;border:0;border-bottom:1px solid var(--line);background:transparent;box-shadow:none;color:var(--ink);text-decoration:none}
.directed-goal-link:hover,.directed-goal-link:focus-visible{box-shadow:none;background:#f4faf9;border-top-color:transparent}
.directed-goal-link .directed-goal-name{grid-column:1;font-size:.95rem}
.directed-goal-link strong{grid-column:2;grid-row:1/span 2;font-size:1.45rem;color:var(--green)}
.directed-goal-link small{grid-column:1;color:var(--secondary-ink)}
.directed-goal-link .directed-goal-cta{grid-column:1/-1;margin:5px 0 0;padding:0;font-size:.76rem}
@media(max-width:700px){.directed-goal-grid{grid-template-columns:minmax(0,1fr)}}
@media print{.directed-goal-grid{display:none}}

/* #633 structured interventions: neutral grouping, no inferred scoring. */
.directed-intervention-groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,165px),1fr));gap:0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);margin:14px 0}
.directed-intervention-group{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:baseline;gap:3px 12px;padding:14px 16px;border-right:1px solid var(--line);min-width:0}
.directed-intervention-group:last-child{border-right:0}
.directed-intervention-group span{font-weight:650;overflow-wrap:anywhere}
.directed-intervention-group strong{font-size:1.25rem;color:var(--ink);font-variant-numeric:tabular-nums}
.directed-intervention-group small{grid-column:1/-1;color:var(--muted)}
@media(max-width:700px){.directed-intervention-group{border-bottom:1px solid var(--line)}}
@media print{.directed-intervention-group{break-inside:avoid}}

/* #633 overview navigation adds routes, not duplicate measurements. */
.report-experience-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));gap:12px;margin:14px 0}
.report-experience-card{display:flex;flex-direction:column;gap:8px;text-decoration:none;color:var(--ink);border-top:3px solid var(--cyan);transition:transform .16s,box-shadow .16s}
.report-experience-card strong{font-size:1rem}
.report-experience-card span{color:var(--secondary-ink);font-size:.84rem;flex:1}
.report-experience-card small{color:var(--blue);font-size:.76rem;font-weight:700}
.report-experience-card:hover,.report-experience-card:focus-visible{transform:translateY(-2px);box-shadow:0 8px 26px rgba(12,37,51,.13)}
@media print{.report-experience-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.report-experience-card{break-inside:avoid;box-shadow:none!important;transform:none!important}}

/* #328: segment CAT-06/CAT-07 explanations without hiding source tables. */
.cat-apdex-readable{
  margin:16px 0;
  padding:17px 20px;
  min-width:0;
  border:1px solid var(--line);
  border-left:3px solid #526fc2;
  border-radius:11px;
  background:#fff;
}
.cat-apdex-readable>h3{
  margin:0 0 12px;
  padding:0 0 8px;
  border-bottom:1px solid var(--line);
  line-height:1.4;
}
.cat-apdex-readable>.table-wrap{max-width:100%}
.cat-apdex-readable [data-contract='CAT07-ARCHITECTURE-358']{
  background:#f8fbff;
  border:1px solid #d9e5f4;
  border-radius:10px;
  padding:14px 16px;
  margin:16px 0 0;
  overflow-wrap:anywhere;
}
.cat-apdex-readable [data-contract='CAT07-ARCHITECTURE-358'] h3{
  margin:0 0 10px;
  padding-bottom:8px;
  border-bottom:1px solid #d9e5f4;
}
@media(max-width:700px){
  .cat-apdex-readable{padding:13px 11px}
  .cat-apdex-readable [data-contract='CAT07-ARCHITECTURE-358']{padding:11px 9px}
}
@media print{
  .cat-apdex-readable,
  .cat-apdex-readable [data-contract='CAT07-ARCHITECTURE-358']{
    background:#fff;
    box-shadow:none;
    break-inside:auto;
  }
}



"""

_JS = r"""
(()=>{
const menuButton=document.querySelector('[data-report-menu-toggle]');
const menu=document.getElementById('report-primary-navigation');
if(menuButton&&menu){
  document.documentElement.classList.add('report-menu-enhanced');
  const setOpen=(value)=>{
    document.documentElement.classList.toggle('report-menu-open',value);
    menuButton.setAttribute('aria-expanded',String(value));
    menuButton.setAttribute('aria-label',value?'Fechar navegação do relatório':'Abrir navegação do relatório');
  };
  menuButton.addEventListener('click',()=>{
    const openNow=menuButton.getAttribute('aria-expanded')!=='true';
    setOpen(openNow);
    if(openNow){const current=menu.querySelector('[aria-current="page"]')||menu.querySelector('a');if(current)current.focus();}
  });
  menu.addEventListener('click',(event)=>{if(event.target.closest('a'))setOpen(false);});
  document.addEventListener('keydown',(event)=>{if(event.key==='Escape'&&menuButton.getAttribute('aria-expanded')==='true'){setOpen(false);menuButton.focus();}});
}
const open=(id)=>{const el=document.getElementById(id);if(el&&typeof el.showModal==='function'&&!el.open)el.showModal();};
const openHash=()=>{let id='';try{id=decodeURIComponent((location.hash||'').replace(/^#/,'')).trim();}catch(_error){return;}if(!id)return;const target=document.getElementById(id);if(!target)return;if(target.matches('details.directed-goal-details')){target.open=true;return;}open(id);};
document.addEventListener('click',(event)=>{const trigger=event.target.closest('[data-modal-open]');if(trigger){event.preventDefault();open(trigger.getAttribute('data-modal-open'));return;}const closer=event.target.closest('[data-modal-close]');if(closer){event.preventDefault();const dlg=closer.closest('dialog');if(dlg)dlg.close();}});
window.addEventListener('hashchange',openHash);
openHash();
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

import React, { ReactNode } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import * as Tabs from '@radix-ui/react-tabs';
import ReactECharts from 'echarts-for-react';
import { ChevronRight, X, Search, Bell, Sparkles } from 'lucide-react';

export type NavItem = { label: string; href: string; icon: ReactNode; badge?: string };

export function AppShell({ brand, subtitle, nav, activePath, topRight, context, children }: { brand: string; subtitle: string; nav: NavItem[]; activePath: string; topRight?: ReactNode; context?: ReactNode; children: ReactNode }) {
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark">R</div><div><strong>{brand}</strong><span>{subtitle}</span></div></div>
      <nav>{nav.map(item => <a className={activePath === item.href ? 'nav-item active' : 'nav-item'} href={item.href} key={item.href}><span className="nav-icon">{item.icon}</span><span>{item.label}</span>{item.badge && <em>{item.badge}</em>}</a>)}</nav>
      <div className="sidebar-footer"><span className="pulse-dot"/> Prototype mode</div>
    </aside>
    <div className="app-main">
      <header className="topbar"><div className="search-shell"><Search size={16}/><span>Buscar auditoria, job, URL, cliente...</span><kbd>⌘ K</kbd></div><div className="top-actions"><button className="icon-button" aria-label="Notificações"><Bell size={17}/></button>{topRight}</div></header>
      {context && <div className="context-strip">{context}</div>}
      <main className="content">{children}</main>
    </div>
  </div>;
}

export function ContextPill({ label, value }: { label: string; value: string }) { return <div className="context-pill"><span>{label}</span><strong>{value}</strong><ChevronRight size={13}/></div>; }
export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) { return <div className="page-header"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h1>{title}</h1>{description && <p>{description}</p>}</div>{actions && <div className="page-actions">{actions}</div>}</div>; }
export function Button({ children, variant='primary', onClick }: { children: ReactNode; variant?: 'primary'|'secondary'|'ghost'|'danger'; onClick?: () => void }) { return <button className={`button ${variant}`} onClick={onClick}>{children}</button>; }
export function Panel({ title, subtitle, action, children, className='' }: { title?: string; subtitle?: string; action?: ReactNode; children: ReactNode; className?: string }) { return <section className={`panel ${className}`}><div className="panel-head">{title && <div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>}{action}</div>{children}</section>; }

export function MetricCard({ label, value, trend, tone='neutral', hint }: { label: string; value: string; trend?: string; tone?: string; hint?: string }) { return <div className={`metric-card tone-${tone}`}><div className="metric-label">{label}</div><div className="metric-row"><strong>{value}</strong>{trend && <span>{trend}</span>}</div>{hint && <p>{hint}</p>}</div>; }

const toneMap: Record<string,string> = { SUCCEEDED:'success', SUCCESS:'success', ACTIVE:'success', READY:'success', RUNNING:'info', QUEUED:'neutral', SCHEDULED:'neutral', PARTIAL:'warning', ATTENTION:'warning', PAUSED:'warning', DEGRADED:'warning', FAILED:'danger', INVALID:'danger', SUSPENDED:'danger', DISABLED:'neutral', TIMEOUT:'danger' };
export function StatusBadge({ status, label }: { status: string; label?: string }) { const tone = toneMap[status] ?? 'neutral'; return <span className={`status-badge ${tone}`}><i/>{label ?? status}</span>; }

export function ProgressBar({ value }: { value: number }) { return <div className="progress"><span style={{ width: `${Math.max(0, Math.min(100, value))}%` }}/></div>; }
export function ProgressSteps({ stages }: { stages: {id:string; label:string; status:string; completedUnits?:number; totalUnits?:number}[] }) { return <div className="steps">{stages.map(s => <div className={`step ${s.status}`} key={s.id}><span className="step-dot"/><div><strong>{s.label}</strong>{s.totalUnits != null && <small>{s.completedUnits ?? 0}/{s.totalUnits}</small>}</div></div>)}</div>; }

export function SimpleTable({ columns, rows }: { columns: {key:string; label:string; render?: (row:any)=>ReactNode}[]; rows: any[] }) { return <div className="table-wrap"><table><thead><tr>{columns.map(c => <th key={c.key}>{c.label}</th>)}</tr></thead><tbody>{rows.map((row, i) => <tr key={row.id ?? row.jobId ?? row.auditId ?? row.scheduleId ?? row.credentialId ?? i}>{columns.map(c => <td key={c.key}>{c.render ? c.render(row) : String(row[c.key] ?? '—')}</td>)}</tr>)}</tbody></table></div>; }

export function TabsView({ tabs, defaultValue }: { tabs: {value:string; label:string; content:ReactNode}[]; defaultValue?: string }) { return <Tabs.Root defaultValue={defaultValue ?? tabs[0]?.value}><Tabs.List className="tabs-list">{tabs.map(t => <Tabs.Trigger key={t.value} value={t.value}>{t.label}</Tabs.Trigger>)}</Tabs.List>{tabs.map(t => <Tabs.Content key={t.value} value={t.value} className="tabs-content">{t.content}</Tabs.Content>)}</Tabs.Root>; }

export function Drawer({ trigger, title, description, children }: { trigger: ReactNode; title:string; description?:string; children:ReactNode }) { return <Dialog.Root><Dialog.Trigger asChild>{trigger}</Dialog.Trigger><Dialog.Portal><Dialog.Overlay className="drawer-overlay"/><Dialog.Content className="drawer"><div className="drawer-head"><div><Dialog.Title>{title}</Dialog.Title>{description && <Dialog.Description>{description}</Dialog.Description>}</div><Dialog.Close className="icon-button"><X size={18}/></Dialog.Close></div>{children}</Dialog.Content></Dialog.Portal></Dialog.Root>; }

export function TrendChart({ values, labels, name='Índice' }: { values:number[]; labels:string[]; name?:string }) { const option = { grid:{left:34,right:14,top:20,bottom:26}, tooltip:{trigger:'axis'}, xAxis:{type:'category',data:labels,boundaryGap:false,axisLine:{show:false},axisTick:{show:false}}, yAxis:{type:'value',min:'dataMin',max:'dataMax',splitLine:{lineStyle:{color:'#edf1f2'}}}, series:[{name,type:'line',data:values,smooth:true,symbolSize:7,lineStyle:{width:3,color:'#3d7476'},itemStyle:{color:'#3d7476'},areaStyle:{color:'rgba(61,116,118,.08)'}}]}; return <ReactECharts option={option} style={{height:240}}/>; }

export function Callout({ title, children, tone='info' }: { title:string; children:ReactNode; tone?:string }) { return <div className={`callout ${tone}`}><Sparkles size={18}/><div><strong>{title}</strong><p>{children}</p></div></div>; }
export function EmptyState({ title, description }: {title:string; description:string}) { return <div className="empty"><strong>{title}</strong><p>{description}</p></div>; }

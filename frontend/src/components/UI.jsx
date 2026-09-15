import React, { useEffect } from 'react'
import { Icon } from './Icons'
import { classNames } from '../lib/format'

export function Spinner({ label = 'Loading' }) { return <div className="loading-state"><span className="spinner"/><span>{label}…</span></div> }
export function Empty({ title = 'Nothing to show', text = 'No records match this view.' }) { return <div className="empty-state"><div className="empty-icon"><Icon name="note"/></div><strong>{title}</strong><span>{text}</span></div> }
export function Pill({ children, tone = 'neutral' }) { return <span className={`pill pill-${tone}`}>{children}</span> }
export function temperatureTone(v) { return v === 'Hot' ? 'danger' : v === 'Warm' ? 'warning' : 'info' }
export function statusTone(v = '') {
  if (v.includes('Won') || v === 'Completed' || v === 'Qualified') return 'success'
  if (v.includes('Lost') || v === 'Overdue') return 'danger'
  if (v.includes('Awaiting') || v.includes('Pending') || v === 'In Progress') return 'warning'
  return 'info'
}
export function Button({ children, icon, variant = 'primary', className = '', ...props }) {
  return <button className={classNames('btn', `btn-${variant}`, className)} {...props}>{icon && <Icon name={icon} size={17}/>}<span>{children}</span></button>
}
export function KpiCard({ label, value, helper, icon = 'forecast', tone = 'blue', onClick }) {
  return <button className={`kpi-card kpi-${tone}`} onClick={onClick} type="button"><div className="kpi-top"><span>{label}</span><div className="kpi-icon"><Icon name={icon} size={19}/></div></div><strong>{value}</strong>{helper && <small>{helper}</small>}</button>
}
export function Modal({ open, onClose, title, eyebrow, children, size = 'md' }) {
  useEffect(() => { if (!open) return; const fn=e=>e.key==='Escape'&&onClose(); window.addEventListener('keydown',fn); return()=>window.removeEventListener('keydown',fn) }, [open,onClose])
  if (!open) return null
  return <div className="modal-backdrop" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><section className={`modal modal-${size}`} role="dialog" aria-modal="true"><header><div>{eyebrow&&<span className="eyebrow">{eyebrow}</span>}<h2>{title}</h2></div><button className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="close"/></button></header><div className="modal-body">{children}</div></section></div>
}
export function Field({ label, hint, children, required, className = '' }) { return <label className={classNames('field', className)}><span>{label}{required&&<em>*</em>}</span>{children}{hint&&<small>{hint}</small>}</label> }
export function Input(props) { return <input className="input" {...props}/> }
export function Select({ children, ...props }) { return <select className="input" {...props}>{children}</select> }
export function Textarea(props) { return <textarea className="input textarea" rows="3" {...props}/> }
export function Pagination({ page, pages, onPage }) {
  if (!pages || pages <= 1) return null
  return <div className="pagination"><button disabled={page<=1} onClick={()=>onPage(page-1)}>Previous</button><span>Page <strong>{page}</strong> of {pages}</span><button disabled={page>=pages} onClick={()=>onPage(page+1)}>Next</button></div>
}
export function SectionHeader({ eyebrow, title, text, actions }) { return <div className="section-heading"><div>{eyebrow&&<span className="eyebrow">{eyebrow}</span>}<h1>{title}</h1>{text&&<p>{text}</p>}</div>{actions&&<div className="section-actions">{actions}</div>}</div> }
export function Table({ columns, rows, onRowClick, keyField='id' }) {
  return <div className="table-wrap"><table><thead><tr>{columns.map(c=><th key={c.key} className={c.align==='right'?'align-right':''}>{c.header?c.header(c):c.label}</th>)}</tr></thead><tbody>{rows.map(r=><tr key={r[keyField]} onClick={()=>onRowClick?.(r)} className={onRowClick?'clickable':''}>{columns.map(c=><td key={c.key} className={c.align==='right'?'align-right':''}>{c.render?c.render(r):r[c.key]??'—'}</td>)}</tr>)}</tbody></table></div>
}
export function ErrorBanner({ error, onRetry }) { if(!error) return null; return <div className="error-banner"><div><strong>Something needs attention</strong><span>{error.message || String(error)}</span></div>{onRetry&&<Button variant="ghost" icon="refresh" onClick={onRetry}>Retry</Button>}</div> }
export function Toast({ toast, onClose }) { useEffect(()=>{if(!toast)return; const t=setTimeout(onClose,3500);return()=>clearTimeout(t)},[toast,onClose]); if(!toast)return null; return <div className={`toast toast-${toast.type||'success'}`}><Icon name={toast.type==='error'?'close':'check'} size={18}/><span>{toast.message}</span></div> }

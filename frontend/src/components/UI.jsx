import React, { useEffect, useId, useRef, useState } from 'react'
import { Icon } from './Icons'
import { classNames } from '../lib/format'

export function Spinner({ label = 'Loading' }) { return <div className="loading-state"><span className="spinner"/><span>{label}…</span></div> }
export function Empty({ title = 'Nothing to show', text = 'No records match this view.' }) { return <div className="empty-state"><div className="empty-icon"><Icon name="note"/></div><strong>{title}</strong><span>{text}</span></div> }
export function Pill({ children, tone = 'neutral', className = '' }) { return <span className={`pill pill-${tone}${className ? ' ' + className : ''}`}>{children}</span> }
export function temperatureTone(v) { return v === 'Hot' ? 'danger' : v === 'Warm' ? 'warning' : 'info' }
// Three filled, gradient icons — not the shared outline icon set — so each temperature reads as
// its literal thing at a glance (fire / sun / snowflake), not an abstract wiggling line shape.
// Gradient ids are per-instance (useId) since a table can render many of the same signal at once.
function FlameIcon({ size = 13 }) {
  const gid = useId()
  return <svg width={size} height={size} viewBox="0 0 24 24" className="flame-fx" aria-hidden="true">
    <defs><linearGradient id={gid} x1="0" y1="1" x2="0" y2="0">
      <stop offset="0%" stopColor="#b71c1c"/><stop offset="42%" stopColor="#ff5a1f"/><stop offset="76%" stopColor="#ffb300"/><stop offset="100%" stopColor="#ffe27a"/>
    </linearGradient></defs>
    <path fill={`url(#${gid})`} d="M8.5 14.5A2.5 2.5 0 0 0 11 17a2.5 2.5 0 0 0 2.5-2.5c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>
  </svg>
}
// Wrapped in .sun-wrap so a blurred radial-gradient corona (::before, CSS) can pulse behind the
// rays — a halo, not just an icon wiggle.
function SunIcon({ size = 13 }) {
  const gid = useId()
  return <span className="sun-wrap"><svg width={size} height={size} viewBox="0 0 24 24" className="sun-fx" aria-hidden="true">
    <defs><radialGradient id={gid} cx="50%" cy="50%" r="55%">
      <stop offset="0%" stopColor="#fff6c9"/><stop offset="55%" stopColor="#ffb300"/><stop offset="100%" stopColor="#ff8f00"/>
    </radialGradient></defs>
    <g stroke={`url(#${gid})`} strokeWidth="2.3" strokeLinecap="round"><path d="M12 1.6v2.8M12 19.6V22M4.93 4.93l1.7 1.7M17.37 17.37l1.7 1.7M1.6 12h2.8M19.6 12H22M6.63 17.37l-1.7 1.7M19.07 4.93l-1.7 1.7"/></g>
    <circle cx="12" cy="12" r="4.6" fill={`url(#${gid})`}/>
  </svg></span>
}
// A solid gradient base draws the full crystal; a second bright overlay path with a short dash
// travels around it on a loop — a genuine sparkle-sweep, not just a wobble.
function SnowflakeIcon({ size = 13 }) {
  const gid = useId()
  const d = "M12 2v20M2 12h20M20 16l-4-4 4-4M4 8l4 4-4 4M16 4l-4 4-4-4M8 20l4-4 4 4"
  return <svg width={size} height={size} viewBox="0 0 24 24" className="snow-fx" aria-hidden="true">
    <defs><linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stopColor="#eef9ff"/><stop offset="100%" stopColor="#3fa9e0"/>
    </linearGradient></defs>
    <path d={d} stroke={`url(#${gid})`} strokeWidth="2.1" strokeLinecap="round" fill="none"/>
    <path d={d} className="snow-sparkle" stroke="#ffffff" strokeWidth="2.1" strokeLinecap="round" fill="none"/>
  </svg>
}
// Each signal is a full, unmistakable treatment — its own literal icon, its own particle motion
// (rising sparks / twinkling glints / falling flakes), and the whole pill breathing that signal's
// color in counterpoint — never just a generic pulse. See styles.css for the keyframes.
export function SignalPill({ value }) {
  if (value === 'Hot') return <Pill tone="danger" className="signal-hot"><FlameIcon/><i className="spark"/><i className="spark spark-2"/>{value}</Pill>
  if (value === 'Warm') return <Pill tone="warning" className="signal-warm"><SunIcon/><i className="glint"/><i className="glint glint-2"/>{value}</Pill>
  return <Pill tone="info" className="signal-cold"><SnowflakeIcon/><i className="flake"/><i className="flake flake-2"/>{value}</Pill>
}
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
  return <div className="modal-backdrop" onMouseDown={e=>e.target===e.currentTarget&&onClose()}><section className={`modal modal-${size}`} role="dialog" aria-modal="true"><header><div>{eyebrow&&<span className="eyebrow">{eyebrow}</span>}<h2>{title}</h2></div><button type="button" className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="close"/></button></header><div className="modal-body">{children}</div></section></div>
}
export function Field({ label, hint, children, required, className = '' }) { return <label className={classNames('field', className)}><span>{label}{required&&<em>*</em>}</span>{children}{hint&&<small>{hint}</small>}</label> }
export function Input(props) { return <input className="input" {...props}/> }
export function Select({ children, ...props }) { return <select className="input" {...props}>{children}</select> }
// A text input with dropdown suggestions: pick from `options`, or type a value that isn't on the list.
export function Combobox({ options = [], listId, ...props }) {
  const id = useId(); const dlId = listId || `combo-${id}`
  return <>
    <input className="input" list={dlId} autoComplete="off" {...props}/>
    <datalist id={dlId}>{options.map(x => <option key={x} value={x}/>)}</datalist>
  </>
}
// A multi-value tag picker backed by a single comma-separated string. Pick as many values from
// `options` as needed, or type new ones — there is no cap on how many tags can be added. Enter,
// comma or blur commits the current text as a tag; Backspace on an empty field removes the last one.
// Suggestions render as our own compact dropdown rather than a native <datalist> popup — the
// browser-native one can't be styled and renders far wider/taller-per-row than the rest of the UI.
export function TagsInput({ options = [], value = '', onChange, disabled, required, placeholder }) {
  const tags = String(value ?? '').split(',').map(t => t.trim()).filter(Boolean)
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const [hi, setHi] = useState(0)
  const wrapRef = useRef(null)
  const suggestions = options.filter(o => !tags.includes(o) && (!text || o.toLowerCase().includes(text.toLowerCase())))
  useEffect(() => { setHi(0) }, [text, open])
  useEffect(() => {
    if (!open) return
    const close = e => { if (!wrapRef.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])
  const commit = raw => {
    const t = raw.trim()
    setText(''); setOpen(false)
    if (!t) return
    if (!tags.some(x => x.toLowerCase() === t.toLowerCase())) onChange?.([...tags, t].join(', '))
  }
  const removeTag = t => onChange?.(tags.filter(x => x !== t).join(', '))
  const onKeyDown = e => {
    if (disabled) return
    if (e.key === 'ArrowDown' && open && suggestions.length) { e.preventDefault(); setHi(h => Math.min(h + 1, suggestions.length - 1)) }
    else if (e.key === 'ArrowUp' && open && suggestions.length) { e.preventDefault(); setHi(h => Math.max(h - 1, 0)) }
    else if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); commit(open && suggestions[hi] ? suggestions[hi] : text) }
    else if (e.key === 'Escape') setOpen(false)
    else if (e.key === 'Backspace' && !text && tags.length) removeTag(tags[tags.length - 1])
  }
  return <div className={classNames('tags-input', disabled && 'disabled')} ref={wrapRef}>
    {tags.map(t => <span className="tag-chip" key={t}>{t}{!disabled && <button type="button" onClick={() => removeTag(t)} aria-label={`Remove ${t}`}>×</button>}</span>)}
    {!disabled && <input className="tags-input-field" autoComplete="off" disabled={disabled}
      value={text} onChange={e => { setText(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)}
      onKeyDown={onKeyDown} onBlur={() => commit(text)}
      placeholder={tags.length ? '' : placeholder} required={required && !tags.length}/>}
    {!disabled && open && suggestions.length > 0 && <div className="tags-suggest" onMouseDown={e => e.preventDefault()}>
      {suggestions.map((o, i) => <button type="button" key={o} className={i === hi ? 'hi' : ''} onClick={() => commit(o)}>{o}</button>)}
    </div>}
  </div>
}
// Pick any number of people (ids). `users` is the assignable list; `known` are people already on the record who may be
// outside it, so their chips always show a name. `exclude` is the primary owner/assignee, who is never listed twice.
export function PeoplePicker({ users = [], known = [], value = [], onChange, exclude, disabled, placeholder = 'Add a person…' }) {
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const [hi, setHi] = useState(0)
  const wrapRef = useRef(null)
  const ids = value.map(String)
  const byId = new Map([...known, ...users].map(p => [String(p.id), p]))
  const suggestions = users.filter(p => String(p.id) !== String(exclude) && !ids.includes(String(p.id)) && (!text || `${p.name} ${p.role || ''}`.toLowerCase().includes(text.toLowerCase())))
  useEffect(() => { setHi(0) }, [text, open])
  useEffect(() => {
    if (!open) return
    const close = e => { if (!wrapRef.current?.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])
  const add = p => { setText(''); setOpen(false); if (p && !ids.includes(String(p.id))) onChange?.([...value, p.id]) }
  const remove = id => onChange?.(value.filter(v => String(v) !== String(id)))
  const onKeyDown = e => {
    if (disabled) return
    if (e.key === 'ArrowDown' && open && suggestions.length) { e.preventDefault(); setHi(h => Math.min(h + 1, suggestions.length - 1)) }
    else if (e.key === 'ArrowUp' && open && suggestions.length) { e.preventDefault(); setHi(h => Math.max(h - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); if (open && suggestions[hi]) add(suggestions[hi]) }
    else if (e.key === 'Escape') setOpen(false)
    else if (e.key === 'Backspace' && !text && value.length) remove(value[value.length - 1])
  }
  return <div className={classNames('tags-input', disabled && 'disabled')} ref={wrapRef}>
    {value.map(id => <span className="tag-chip" key={id}>{byId.get(String(id))?.name || `User ${id}`}{!disabled && <button type="button" onClick={() => remove(id)} aria-label={`Remove ${byId.get(String(id))?.name || id}`}>×</button>}</span>)}
    {!disabled && <input className="tags-input-field" autoComplete="off" value={text} onChange={e => { setText(e.target.value); setOpen(true) }}
      onFocus={() => setOpen(true)} onKeyDown={onKeyDown} placeholder={value.length ? '' : placeholder} aria-label="Add a person"/>}
    {!disabled && open && suggestions.length > 0 && <div className="tags-suggest" onMouseDown={e => e.preventDefault()}>
      {suggestions.map((p, i) => <button type="button" key={p.id} className={i === hi ? 'hi' : ''} onClick={() => add(p)}>{p.name}{p.role ? ` · ${p.role}` : ''}</button>)}
    </div>}
  </div>
}
export function Textarea(props) { return <textarea className="input textarea" rows="3" {...props}/> }
export function Pagination({ page, pages, onPage }) {
  if (!pages || pages <= 1) return null
  return <div className="pagination"><button disabled={page<=1} onClick={()=>onPage(page-1)}>Previous</button><span>Page <strong>{page}</strong> of {pages}</span><button disabled={page>=pages} onClick={()=>onPage(page+1)}>Next</button></div>
}
export function SectionHeader({ eyebrow, title, text, actions }) { return <div className="section-heading"><div>{eyebrow&&<span className="eyebrow">{eyebrow}</span>}<h1>{title}</h1>{text&&<p>{text}</p>}</div>{actions&&<div className="section-actions">{actions}</div>}</div> }
export function Table({ columns, rows, onRowClick, keyField='id' }) {
  return <div className="table-wrap"><table><thead><tr>{columns.map(c=><th key={c.key} className={c.align==='right'?'align-right':''}>{c.header?c.header(c):c.label}</th>)}</tr></thead><tbody>{rows.map(r=><tr key={r[keyField]} onClick={()=>onRowClick?.(r)} className={onRowClick?'clickable':''}>{columns.map(c=><td key={c.key} className={c.align==='right'?'align-right':''}>{c.render?c.render(r):r[c.key]??'—'}</td>)}</tr>)}</tbody></table></div>
}
export function BulkBar({ count, noun, onDelete, onClear, busy }) {
  if (!count) return null
  return <div className="bulk-bar" role="status"><strong>{count} {noun}{count===1?'':'s'} selected</strong><Button variant="soft" className="text-danger" icon="trash" onClick={onDelete} disabled={busy}>{busy?'Deleting…':'Delete selected'}</Button><Button variant="ghost" onClick={onClear} disabled={busy}>Clear</Button></div>
}
export function ErrorBanner({ error, onRetry }) { if(!error) return null; return <div className="error-banner"><div><strong>Something needs attention</strong><span>{error.message || String(error)}</span></div>{onRetry&&<Button variant="ghost" icon="refresh" onClick={onRetry}>Retry</Button>}</div> }
export function Toast({ toast, onClose }) { useEffect(()=>{if(!toast)return; const t=setTimeout(onClose,3500);return()=>clearTimeout(t)},[toast,onClose]); if(!toast)return null; return <div className={`toast toast-${toast.type||'success'}`}><Icon name={toast.type==='error'?'close':'check'} size={18}/><span>{toast.message}</span></div> }

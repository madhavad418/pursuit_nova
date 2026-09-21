import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import { dateText } from '../lib/format'
import { Button, Empty, ErrorBanner, Field, Input, Modal, PeoplePicker, Pill, SectionHeader, Select, Textarea, BulkBar, statusTone } from '../components/UI'
import { navigate } from '../lib/router'
import { useAuth } from '../components/Auth'
import { Icon } from '../components/Icons'
import { isRequestedHiddenAdmin, visiblePickerUsers } from '../lib/users'
import { deleteMany, bulkResultMessage } from '../lib/bulk'

const isAdminRole = (role) => role === 'Super Admin' || role === 'Admin'
const STATUSES = ['Open', 'In Progress', 'Completed', 'Cancelled']
const PRIORITIES = ['Low', 'Medium', 'High', 'Critical']
// Primary assignee first, then any additional people; long teams collapse to "Name +N" with the full list on hover
function Assignees({ a }) {
  const co = a.co_assignees || []
  return co.length ? <span title={[a.assigned_to_name, ...co.map(p => p.name)].join(', ')}>{a.assigned_to_name} <small style={{ color: 'var(--muted)' }}>+{co.length}</small></span> : a.assigned_to_name
}
const today = () => new Date().toISOString().slice(0, 10)
const summarize = rows => ({ total: rows.length, overdue: rows.filter(x => x.overdue).length, today: rows.filter(x => x.due_date === today() && !['Completed', 'Cancelled'].includes(x.status)).length, open: rows.filter(x => !['Completed', 'Cancelled'].includes(x.status)).length })

function FilterSelect({ value, onChange }) {
  return <Select value={value} onChange={e => onChange(e.target.value)} aria-label="Filter actions"><option value="all">All visible actions</option><option value="my">My actions</option><option value="overdue">Overdue</option><option value="today">Due today</option><option value="upcoming">Upcoming</option><option value="completed">Completed</option></Select>
}
// Column headings shared by both boards; widths come from .action-cols so every row lines up
function BoardHeader({ third, selectAll }) {
  return <div className="action-cols action-head" role="row"><span role="columnheader">{selectAll && <input type="checkbox" className="bulk-check" aria-label="Select all actions" checked={selectAll.checked} onChange={selectAll.onChange} />}Priority</span><span role="columnheader">Action</span><span role="columnheader">{third}</span><span role="columnheader">Assigned to</span><span role="columnheader">Due</span><span role="columnheader">Status</span><span role="columnheader" className="align-end">Actions</span></div>
}
function Counts({ counts }) {
  return <div className="mini-kpis"><div><span>Open work</span><strong>{counts.open}</strong></div><div><span>Overdue</span><strong className="text-danger">{counts.overdue}</strong></div><div><span>Due today</span><strong>{counts.today}</strong></div><div><span>Visible actions</span><strong>{counts.total}</strong></div></div>
}

/* ─── Actions linked to a prospect (unchanged behaviour) ─── */
function ProspectActions({ onToast, filter, assignableUsers }) {
  const { user } = useAuth(); const admin = isAdminRole(user.role)
  const [rows, setRows] = useState([]); const [error, setError] = useState(null)
  const [editOpen, setEditOpen] = useState(false); const [editForm, setEditForm] = useState({}); const [editSaving, setEditSaving] = useState(false)
  const [selected, setSelected] = useState([]); const [bulkBusy, setBulkBusy] = useState(false)
  const load = () => { setError(null); return api.get('/api/actions?filter=' + encodeURIComponent(filter)).then(r => { setRows(r); setSelected(s => s.filter(id => r.some(a => a.id === id))) }).catch(setError) }
  const bulkDelete = async () => {
    if (!selected.length || !confirm(`Delete ${selected.length} selected action${selected.length === 1 ? '' : 's'}?`)) return
    setBulkBusy(true)
    try { const res = await deleteMany(selected, id => api.delete(`/api/actions/${id}`)); onToast?.(bulkResultMessage('action', res)); setSelected(res.failed.map(f => f.id)) } finally { setBulkBusy(false) }
    load()
  }
  const allSelected = rows.length > 0 && rows.every(a => selected.includes(a.id))
  useEffect(() => { load() }, [filter])
  const counts = useMemo(() => summarize(rows), [rows])
  const update = async (a, status) => { try { await api.put(`/api/actions/${a.id}`, { status }); onToast?.({ message: `Action ${status.toLowerCase()}` }); load() } catch (e) { onToast?.({ type: 'error', message: e.message }) } }
  const deleteAction = async (a) => { if (!confirm(`Delete action "${a.description}"?`)) return; try { await api.delete(`/api/actions/${a.id}`); onToast?.({ message: 'Action deleted' }); load() } catch (e) { onToast?.({ type: 'error', message: e.message }) } }
  const openEdit = a => { setEditForm({ id: a.id, description: a.description || '', assigned_to: String(a.assigned_to), co_assignee_ids: (a.co_assignees || []).map(p => p.id), co_known: a.co_assignees || [], due_date: a.due_date || '', status: a.status || 'Open', priority: a.priority || 'Medium', remarks: a.remarks || '', company_name: a.company_name }); setEditOpen(true) }
  const setE = (k, v) => setEditForm(f => ({ ...f, [k]: v }))
  const saveEdit = async e => { e.preventDefault(); setEditSaving(true); try { const { id, company_name, co_known, ...fields } = editForm; fields.assigned_to = Number(fields.assigned_to); fields.co_assignee_ids = (fields.co_assignee_ids || []).filter(x => Number(x) !== fields.assigned_to).map(Number); await api.put(`/api/actions/${id}`, fields); onToast?.({ message: 'Action updated' }); setEditOpen(false); load() } catch (err) { onToast?.({ type: 'error', message: err.message }) } finally { setEditSaving(false) } }
  const currentActionAssignee = rows.find(r => String(r.assigned_to) === String(editForm.assigned_to))
  const hiddenCurrentActionAssignee = isRequestedHiddenAdmin({ id: editForm.assigned_to, name: currentActionAssignee?.assigned_to_name })
  const actionAssigneeOptions = editForm.assigned_to && !assignableUsers.some(x => String(x.id) === String(editForm.assigned_to)) ? [...assignableUsers, { id: editForm.assigned_to, name: hiddenCurrentActionAssignee ? 'Current assignee' : currentActionAssignee?.assigned_to_name || 'Current assignee', role: 'current' }] : assignableUsers
  return <>
    <Counts counts={counts} />
    <ErrorBanner error={error} onRetry={load} />
    <section className="panel action-panel">{admin && <BulkBar count={selected.length} noun="action" onDelete={bulkDelete} onClear={() => setSelected([])} busy={bulkBusy} />}<div className="action-board" role="table">{rows.length > 0 && <BoardHeader third="Company" selectAll={admin ? { checked: allSelected, onChange: () => setSelected(allSelected ? [] : rows.map(a => a.id)) } : null} />}{rows.map(a => <div className={a.overdue ? 'action-cols action-row overdue' : 'action-cols action-row'} role="row" key={a.id}><span className={`priority priority-${String(a.priority).toLowerCase()}`} data-label="Priority">{admin && <input type="checkbox" className="bulk-check" aria-label="Select action" checked={selected.includes(a.id)} onChange={() => setSelected(s => s.includes(a.id) ? s.filter(x => x !== a.id) : [...s, a.id])} />}{a.priority}</span><button className="action-link" onClick={() => navigate(`lead/${a.lead_id}`)} title={a.description}><strong>{a.description}</strong>{a.remarks && <span>{a.remarks}</span>}</button><span className="action-cell" data-label="Company">{a.company_name}</span><span className="action-cell" data-label="Assigned to"><Assignees a={a} /></span><span className={a.overdue ? 'action-cell action-date text-danger' : 'action-cell action-date'} data-label="Due">{dateText(a.due_date)}</span><span className="action-cell" data-label="Status"><Pill tone={a.overdue ? 'danger' : statusTone(a.status)}>{a.overdue ? 'Overdue' : a.status}</Pill></span><div className="action-buttons">{a.status !== 'Completed' ? <Button variant="text" onClick={() => update(a, 'Completed')}>Complete</Button> : <span className="slot" aria-hidden="true" />}{a.status === 'Open' ? <Button variant="text" onClick={() => update(a, 'In Progress')}>Start</Button> : <span className="slot" aria-hidden="true" />}{admin ? <button className="icon-btn" title="Edit" aria-label="Edit action" onClick={() => openEdit(a)}><Icon name="edit" size={16} /></button> : <span className="slot" aria-hidden="true" />}{admin ? <button className="icon-btn text-danger" title="Delete" aria-label="Delete action" onClick={() => deleteAction(a)}><Icon name="trash" size={16} /></button> : <span className="slot" aria-hidden="true" />}</div></div>)}{!rows.length && <Empty title="No actions in this view" text="You're clear for the selected filter." />}</div></section>
    <Modal open={editOpen} onClose={() => setEditOpen(false)} title="Edit action" eyebrow={editForm.company_name}><form onSubmit={saveEdit}>
      <div className="form-grid">
        <Field label="Description" className="span-2"><Textarea required value={editForm.description || ''} onChange={e => setE('description', e.target.value)} /></Field>
        <Field label="Assigned to"><Select value={editForm.assigned_to || ''} onChange={e => setE('assigned_to', e.target.value)}>{actionAssigneeOptions.map(x => <option key={x.id} value={x.id}>{x.name}{x.role && x.role !== 'current' ? ` · ${x.role}` : ''}</option>)}</Select></Field>
        <Field label="Additional assignees" hint="Add as many people as needed" className="span-2"><PeoplePicker users={assignableUsers} known={editForm.co_known || []} exclude={editForm.assigned_to} value={(editForm.co_assignee_ids || []).filter(x => String(x) !== String(editForm.assigned_to))} onChange={v => setE('co_assignee_ids', v)} /></Field>
        <Field label="Due date"><Input type="date" required value={editForm.due_date || ''} onChange={e => setE('due_date', e.target.value)} /></Field>
        <Field label="Status"><Select value={editForm.status || ''} onChange={e => setE('status', e.target.value)}>{STATUSES.map(x => <option key={x}>{x}</option>)}</Select></Field>
        <Field label="Priority"><Select value={editForm.priority || ''} onChange={e => setE('priority', e.target.value)}>{PRIORITIES.map(x => <option key={x}>{x}</option>)}</Select></Field>
        <Field label="Remarks" className="span-2"><Textarea value={editForm.remarks || ''} onChange={e => setE('remarks', e.target.value)} /></Field>
      </div>
      <div className="modal-actions"><Button type="button" variant="ghost" onClick={() => setEditOpen(false)}>Cancel</Button><Button type="submit" disabled={editSaving}>{editSaving ? 'Saving…' : 'Save changes'}</Button></div>
    </form></Modal>
  </>
}

/* ─── Generic actions: work not tied to a prospect (PPT, summit preparation…) ─── */
const emptyGeneric = userId => ({ id: null, title: '', action_type: '', description: '', assigned_to: String(userId), co_assignee_ids: [], due_date: '', priority: 'Medium', status: 'Open', remarks: '' })

function GenericActions({ onToast, filter, assignableUsers, createSignal }) {
  const { user } = useAuth(); const admin = isAdminRole(user.role)
  const [data, setData] = useState({ items: [], types: [], can_create: false }); const [error, setError] = useState(null)
  const [form, setForm] = useState(null); const [saving, setSaving] = useState(false); const [viewing, setViewing] = useState(null)
  const [selected, setSelected] = useState([]); const [bulkBusy, setBulkBusy] = useState(false)
  const load = () => { setError(null); return api.get('/api/generic-actions?filter=' + encodeURIComponent(filter)).then(d => { setData(d); setSelected(s => s.filter(id => (d.items || []).some(a => a.id === id && a.can_delete))) }).catch(setError) }
  useEffect(() => { load() }, [filter])
  useEffect(() => { if (createSignal) setForm(emptyGeneric(user.id)) }, [createSignal])
  const rows = data.items || []
  const counts = useMemo(() => summarize(rows), [rows])
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const fail = e => onToast?.({ type: 'error', message: e.message })
  const update = async (a, status) => { try { await api.put(`/api/generic-actions/${a.id}`, { status }); onToast?.({ message: `Action ${status === 'Completed' ? 'completed' : 'started'}` }); load() } catch (e) { fail(e) } }
  const deletable = rows.filter(a => a.can_delete); const allSelected = deletable.length > 0 && deletable.every(a => selected.includes(a.id))
  const bulkDelete = async () => {
    if (!selected.length || !confirm(`Delete ${selected.length} selected action${selected.length === 1 ? '' : 's'}?`)) return
    setBulkBusy(true)
    try { const res = await deleteMany(selected, id => api.delete(`/api/generic-actions/${id}`)); onToast?.(bulkResultMessage('action', res)); setSelected(res.failed.map(f => f.id)) } finally { setBulkBusy(false) }
    load()
  }
  const remove = async a => { if (!confirm(`Delete action "${a.title}"?`)) return; try { await api.delete(`/api/generic-actions/${a.id}`); onToast?.({ message: 'Action deleted' }); load() } catch (e) { fail(e) } }
  const openEdit = a => setForm({ id: a.id, title: a.title || '', action_type: a.action_type || '', description: a.description || '', assigned_to: String(a.assigned_to), co_assignee_ids: (a.co_assignees || []).map(p => p.id), co_known: a.co_assignees || [], due_date: a.due_date || '', priority: a.priority || 'Medium', status: a.status || 'Open', remarks: a.remarks || '' })
  const save = async e => {
    e.preventDefault()
    const title = form.title.trim(), action_type = form.action_type.trim()
    if (!title || !action_type) { onToast?.({ type: 'error', message: !title ? 'Title is required' : 'Type is required' }); return }
    setSaving(true)
    try {
      const { id, co_known, ...fields } = form; fields.title = title; fields.action_type = action_type; fields.assigned_to = Number(fields.assigned_to)
      if (admin) fields.co_assignee_ids = (fields.co_assignee_ids || []).filter(x => Number(x) !== fields.assigned_to).map(Number); else delete fields.co_assignee_ids
      if (id) { await api.put(`/api/generic-actions/${id}`, fields); onToast?.({ message: 'Action updated' }) }
      else { await api.post('/api/generic-actions', fields); onToast?.({ message: 'Action created' }) }
      setForm(null); load()
    } catch (err) { fail(err) } finally { setSaving(false) }
  }
  // The assignee list must always include the current assignee, even if they are outside the editor's assignable list
  const currentAssignee = rows.find(r => String(r.assigned_to) === String(form?.assigned_to))
  const hiddenCurrentAssignee = isRequestedHiddenAdmin({ id: form?.assigned_to, name: currentAssignee?.assigned_to_name })
  const assigneeOptions = form && !assignableUsers.some(x => String(x.id) === String(form.assigned_to)) ? [...assignableUsers, { id: form.assigned_to, name: hiddenCurrentAssignee ? 'Current assignee' : currentAssignee?.assigned_to_name || 'Current assignee', role: 'current' }] : assignableUsers

  return <>
    <Counts counts={counts} />
    <ErrorBanner error={error} onRetry={load} />
    <section className="panel action-panel">{deletable.length > 0 && <BulkBar count={selected.length} noun="action" onDelete={bulkDelete} onClear={() => setSelected([])} busy={bulkBusy} />}<div className="action-board" role="table">
      {rows.length > 0 && <BoardHeader third="Type" selectAll={deletable.length ? { checked: allSelected, onChange: () => setSelected(allSelected ? [] : deletable.map(a => a.id)) } : null} />}
      {rows.map(a => <div className={a.overdue ? 'action-cols action-row overdue' : 'action-cols action-row'} role="row" key={a.id}>
        <span className={`priority priority-${String(a.priority).toLowerCase()}`} data-label="Priority">{a.can_delete && <input type="checkbox" className="bulk-check" aria-label="Select action" checked={selected.includes(a.id)} onChange={() => setSelected(s => s.includes(a.id) ? s.filter(x => x !== a.id) : [...s, a.id])} />}{a.priority}</span>
        <button className="action-link" onClick={() => setViewing(a)} title={a.title}>
          <strong>{a.title}</strong>
          {a.created_by !== a.assigned_to && <span>Created by {a.created_by_name}</span>}
        </button>
        <span className="action-cell" data-label="Type"><span className="generic-type">{a.action_type}</span></span>
        <span className="action-cell" data-label="Assigned to"><Assignees a={a} /></span>
        <span className={a.overdue ? 'action-cell action-date text-danger' : 'action-cell action-date'} data-label="Due">{dateText(a.due_date)}</span>
        <span className="action-cell" data-label="Status"><Pill tone={a.overdue ? 'danger' : statusTone(a.status)}>{a.overdue ? 'Overdue' : a.status}</Pill></span>
        <div className="action-buttons">
          {a.can_edit && a.status !== 'Completed' && a.status !== 'Cancelled' ? <Button variant="text" onClick={() => update(a, 'Completed')}>Complete</Button> : <span className="slot" aria-hidden="true" />}
          {a.can_edit && a.status === 'Open' ? <Button variant="text" onClick={() => update(a, 'In Progress')}>Start</Button> : <span className="slot" aria-hidden="true" />}
          {a.can_edit ? <button className="icon-btn" title="Edit" aria-label="Edit action" onClick={() => openEdit(a)}><Icon name="edit" size={16} /></button> : <span className="slot" aria-hidden="true" />}
          {a.can_delete ? <button className="icon-btn text-danger" title="Delete" aria-label="Delete action" onClick={() => remove(a)}><Icon name="trash" size={16} /></button> : <span className="slot" aria-hidden="true" />}
        </div>
      </div>)}
      {!rows.length && <Empty title="No generic actions in this view" text={data.can_create ? 'Create one for work like PPT or summit preparation.' : "You're clear for the selected filter."} />}
    </div></section>

    <Modal open={!!form} onClose={() => setForm(null)} title={form?.id ? 'Edit generic action' : 'New generic action'} eyebrow="Not linked to a prospect">{form && <form onSubmit={save}>
      <div className="form-grid">
        <Field label="Title" required className="span-2"><Input required maxLength={255} autoFocus value={form.title} onChange={e => set('title', e.target.value)} placeholder="e.g. Prepare summit PPT" /></Field>
        <Field label="Type" required><Input required maxLength={60} value={form.action_type} onChange={e => set('action_type', e.target.value)} placeholder="e.g. PPT, Summit preparation" /></Field>
        <Field label="Assigned to" required><Select value={form.assigned_to} onChange={e => set('assigned_to', e.target.value)}>{assigneeOptions.map(x => <option key={x.id} value={x.id}>{x.name}{x.role && x.role !== 'current' ? ` · ${x.role}` : ''}</option>)}</Select></Field>
        {(admin || (form.co_known || []).length > 0) && <Field label="Additional assignees" hint={admin ? 'Add as many people as needed — each is notified' : 'Set by an Admin'} className="span-2"><PeoplePicker disabled={!admin} users={assignableUsers} known={form.co_known || []} exclude={form.assigned_to} value={(form.co_assignee_ids || []).filter(x => String(x) !== String(form.assigned_to))} onChange={v => set('co_assignee_ids', v)} /></Field>}
        <Field label="Due date" required><Input type="date" required value={form.due_date} onChange={e => set('due_date', e.target.value)} /></Field>
        <Field label="Priority"><Select value={form.priority} onChange={e => set('priority', e.target.value)}>{PRIORITIES.map(x => <option key={x}>{x}</option>)}</Select></Field>
        {form.id && <Field label="Status"><Select value={form.status} onChange={e => set('status', e.target.value)}>{STATUSES.map(x => <option key={x}>{x}</option>)}</Select></Field>}
        <Field label="Description" className="span-2"><Textarea value={form.description} onChange={e => set('description', e.target.value)} placeholder="What needs to be done" /></Field>
        <Field label="Remarks" className="span-2"><Textarea value={form.remarks} onChange={e => set('remarks', e.target.value)} /></Field>
      </div>
      <div className="modal-actions"><Button type="button" variant="ghost" onClick={() => setForm(null)}>Cancel</Button><Button type="submit" disabled={saving}>{saving ? 'Saving…' : form.id ? 'Save changes' : 'Create action'}</Button></div>
    </form>}</Modal>

    <Modal open={!!viewing} onClose={() => setViewing(null)} title={viewing?.title} eyebrow={viewing?.action_type}>{viewing && <div className="generic-detail">
      <div className="generic-detail-grid">
        <div><span>Assigned to</span><strong>{[viewing.assigned_to_name, ...(viewing.co_assignees || []).map(p => p.name)].join(', ')}</strong></div>
        <div><span>Created by</span><strong>{viewing.created_by_name}</strong></div>
        <div><span>Due</span><strong className={viewing.overdue ? 'text-danger' : ''}>{dateText(viewing.due_date)}</strong></div>
        <div><span>Status</span><Pill tone={viewing.overdue ? 'danger' : statusTone(viewing.status)}>{viewing.overdue ? 'Overdue' : viewing.status}</Pill></div>
        <div><span>Priority</span><strong>{viewing.priority}</strong></div>
        {viewing.completion_date && <div><span>Completed</span><strong>{dateText(viewing.completion_date)}</strong></div>}
      </div>
      {viewing.description && <p><span>Description</span>{viewing.description}</p>}
      {viewing.remarks && <p><span>Remarks</span>{viewing.remarks}</p>}
      <div className="modal-actions">{viewing.can_edit && <Button variant="ghost" onClick={() => { const v = viewing; setViewing(null); openEdit(v) }}>Edit</Button>}<Button onClick={() => setViewing(null)}>Close</Button></div>
    </div>}</Modal>
  </>
}

export default function ActionsPage({ onToast }) {
  const { has } = useAuth()
  const [tab, setTab] = useState(() => { try { return localStorage.getItem('pn_actions_tab') === 'generic' ? 'generic' : 'prospect' } catch { return 'prospect' } })
  const [filter, setFilter] = useState('all'); const [assignableUsers, setAssignableUsers] = useState([]); const [createSignal, setCreateSignal] = useState(0)
  useEffect(() => { api.get('/api/users/assignable').then(res => setAssignableUsers(visiblePickerUsers(res, { hideKamalakar: true, hideSuperAdmin: true }))).catch(() => { }) }, [])
  const pick = t => { setTab(t); setCreateSignal(0); try { localStorage.setItem('pn_actions_tab', t) } catch { } }
  return <>
    <SectionHeader eyebrow="Execution discipline" title="Actions" text={tab === 'generic' ? 'Track work that is not tied to a prospect, like PPT and summit preparation.' : 'Turn every meeting commitment into a visible owner, due date and outcome.'} actions={<>
      <div className="segmented" role="tablist"><button role="tab" aria-selected={tab === 'prospect'} className={tab === 'prospect' ? 'active' : ''} onClick={() => pick('prospect')}>Prospect actions</button><button role="tab" aria-selected={tab === 'generic'} className={tab === 'generic' ? 'active' : ''} onClick={() => pick('generic')}>Generic actions</button></div>
      <FilterSelect value={filter} onChange={setFilter} />
      {tab === 'generic' && has('ACTION_EDIT') && <Button icon="plus" onClick={() => setCreateSignal(n => n + 1)}>New action</Button>}
    </>} />
    {tab === 'generic'
      ? <GenericActions onToast={onToast} filter={filter} assignableUsers={assignableUsers} createSignal={createSignal} />
      : <ProspectActions onToast={onToast} filter={filter} assignableUsers={assignableUsers} />}
  </>
}

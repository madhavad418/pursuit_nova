import React,{useEffect,useMemo,useState} from 'react'
import { api } from '../lib/api'
import { dateText } from '../lib/format'
import { Button,Empty,ErrorBanner,Field,Input,Modal,Pill,SectionHeader,Select,Textarea,statusTone } from '../components/UI'
import { navigate } from '../lib/router'
import { useAuth } from '../components/Auth'
import { Icon } from '../components/Icons'

const isAdminRole = (role) => role === 'Super Admin' || role === 'Admin'

export default function ActionsPage({onToast}){
 const {user}=useAuth(); const admin=isAdminRole(user.role)
 const [filter,setFilter]=useState('all'); const [rows,setRows]=useState([]); const [error,setError]=useState(null)
 const [editOpen,setEditOpen]=useState(false); const [editForm,setEditForm]=useState({}); const [editSaving,setEditSaving]=useState(false); const [assignableUsers,setAssignableUsers]=useState([])
 const load=()=>{setError(null);return api.get('/api/actions?filter='+encodeURIComponent(filter)).then(setRows).catch(setError)}
 useEffect(()=>{load()},[filter])
 useEffect(()=>{api.get('/api/users/assignable').then(setAssignableUsers).catch(()=>{})},[])
 const counts=useMemo(()=>({total:rows.length,overdue:rows.filter(x=>x.overdue).length,today:rows.filter(x=>x.due_date===new Date().toISOString().slice(0,10)).length,open:rows.filter(x=>!['Completed','Cancelled'].includes(x.status)).length}),[rows])
 const update=async(a,status)=>{try{await api.put(`/api/actions/${a.id}`,{status});onToast?.({message:`Action ${status.toLowerCase()}`});load()}catch(e){onToast?.({type:'error',message:e.message})}}
 const deleteAction=async(a)=>{if(!confirm(`Delete action "${a.description}"?`))return;try{await api.delete(`/api/actions/${a.id}`);onToast?.({message:'Action deleted'});load()}catch(e){onToast?.({type:'error',message:e.message})}}
 const openEdit=a=>{setEditForm({id:a.id,description:a.description||'',assigned_to:String(a.assigned_to),due_date:a.due_date||'',status:a.status||'Open',priority:a.priority||'Medium',remarks:a.remarks||'',company_name:a.company_name});setEditOpen(true)}
 const setE=(k,v)=>setEditForm(f=>({...f,[k]:v}))
 const saveEdit=async e=>{e.preventDefault();setEditSaving(true);try{const {id,company_name,...fields}=editForm;fields.assigned_to=Number(fields.assigned_to);await api.put(`/api/actions/${id}`,fields);onToast?.({message:'Action updated'});setEditOpen(false);load()}catch(err){onToast?.({type:'error',message:err.message})}finally{setEditSaving(false)}}
 return <><SectionHeader eyebrow="Execution discipline" title="Actions" text="Turn every meeting commitment into a visible owner, due date and outcome." actions={<Select value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">All visible actions</option><option value="my">My actions</option><option value="overdue">Overdue</option><option value="today">Due today</option><option value="upcoming">Upcoming</option><option value="completed">Completed</option></Select>}/><div className="mini-kpis"><div><span>Open work</span><strong>{counts.open}</strong></div><div><span>Overdue</span><strong className="text-danger">{counts.overdue}</strong></div><div><span>Due today</span><strong>{counts.today}</strong></div><div><span>Visible actions</span><strong>{counts.total}</strong></div></div><ErrorBanner error={error} onRetry={load}/><section className="panel"><div className="action-board">{rows.map(a=><div className={a.overdue?'action-board-row overdue':'action-board-row'} key={a.id}><span className={`priority priority-${String(a.priority).toLowerCase()}`}>{a.priority}</span><button className="action-link" onClick={()=>navigate(`lead/${a.lead_id}`)}><strong>{a.description}</strong><span>{a.company_name} · {a.assigned_to_name}</span></button><div className="action-due"><span>Due</span><strong className={a.overdue?'text-danger':''}>{dateText(a.due_date)}</strong></div><Pill tone={a.overdue?'danger':statusTone(a.status)}>{a.overdue?'Overdue':a.status}</Pill><div className="row-actions">{a.status!=='Completed'&&<Button variant="text" onClick={()=>update(a,'Completed')}>Complete</Button>}{a.status==='Open'&&<Button variant="text" onClick={()=>update(a,'In Progress')}>Start</Button>}{admin&&<><button className="icon-btn" title="Edit" onClick={()=>openEdit(a)}><Icon name="edit" size={16}/></button><button className="icon-btn text-danger" title="Delete" onClick={()=>deleteAction(a)}><Icon name="trash" size={16}/></button></>}</div></div>)}{!rows.length&&<Empty title="No actions in this view" text="You're clear for the selected filter."/>}</div></section>
<Modal open={editOpen} onClose={()=>setEditOpen(false)} title="Edit action" eyebrow={editForm.company_name}><form onSubmit={saveEdit}>
 <div className="form-grid">
  <Field label="Description" className="span-2"><Textarea required value={editForm.description||''} onChange={e=>setE('description',e.target.value)}/></Field>
  <Field label="Assigned to"><Select value={editForm.assigned_to||''} onChange={e=>setE('assigned_to',e.target.value)}>{assignableUsers.map(x=><option key={x.id} value={x.id}>{x.name} · {x.role}</option>)}</Select></Field>
  <Field label="Due date"><Input type="date" required value={editForm.due_date||''} onChange={e=>setE('due_date',e.target.value)}/></Field>
  <Field label="Status"><Select value={editForm.status||''} onChange={e=>setE('status',e.target.value)}>{['Open','In Progress','Completed','Cancelled'].map(x=><option key={x}>{x}</option>)}</Select></Field>
  <Field label="Priority"><Select value={editForm.priority||''} onChange={e=>setE('priority',e.target.value)}>{['Low','Medium','High','Critical'].map(x=><option key={x}>{x}</option>)}</Select></Field>
  <Field label="Remarks" className="span-2"><Textarea value={editForm.remarks||''} onChange={e=>setE('remarks',e.target.value)}/></Field>
 </div>
 <div className="modal-actions"><Button type="button" variant="ghost" onClick={()=>setEditOpen(false)}>Cancel</Button><Button type="submit" disabled={editSaving}>{editSaving?'Saving…':'Save changes'}</Button></div>
</form></Modal></>
}

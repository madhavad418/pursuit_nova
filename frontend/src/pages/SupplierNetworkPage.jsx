import React,{useEffect,useState} from 'react'
import { api } from '../lib/api'
import { Button,Empty,ErrorBanner,Field,Input,Modal,Pill,SectionHeader,Select,Spinner,Table,Textarea } from '../components/UI'
import { Icon } from '../components/Icons'
import { useAuth } from '../components/Auth'

// Order mirrors the registration pipeline as given by the business team: a company moves left to
// right as JSAN works its way onto that company's supplier/subcontractor roster. "Clarification
// required" is a blocker state, not a final stage — a company can land there from anywhere while
// JSAN waits on an answer, then move on once resolved.
export const REGISTRATION_STATUSES=['Ready to initiate','Initiated','Qualification preparation','Portal qualification','Procurement outreach','Scope confirmation','Clarification required']
const STATUS_TONE={'Ready to initiate':'neutral','Initiated':'neutral','Qualification preparation':'info','Portal qualification':'info','Procurement outreach':'warning','Scope confirmation':'warning','Clarification required':'danger'}

const emptyForm={company_name:'',market:'',registration_status:'Ready to initiate',entry_route:'',public_evidence:'',suggested_approach:'',notes:''}

export default function SupplierNetworkPage({route,onToast}){
 const {has}=useAuth()
 const [data,setData]=useState(null); const [error,setError]=useState(null)
 const [statusFilter,setStatusFilter]=useState('')
 const [editing,setEditing]=useState(null) // the target row currently open in the edit modal
 const [createOpen,setCreateOpen]=useState(false); const [form,setForm]=useState(emptyForm); const [saving,setSaving]=useState(false)
 const canEdit=has('COMPANY_EDIT')
 const load=()=>{setError(null);api.get('/api/vendor-targets').then(setData).catch(setError)}
 useEffect(()=>{load()},[])
 const items=(data?.items||[]).filter(x=>!statusFilter||x.registration_status===statusFilter)
 const counts=Object.fromEntries(REGISTRATION_STATUSES.map(s=>[s,(data?.items||[]).filter(x=>x.registration_status===s).length]))
 const openEdit=row=>setEditing({...row})
 // Global search links here as supplier-network?open=<id>; open that target once the list has loaded.
 const openId=route?.query?.get('open')
 useEffect(()=>{if(!openId||!data)return; const r=data.items?.find(x=>String(x.id)===openId); if(r)openEdit(r)},[openId,data])
 const deleteTarget=async(e,row)=>{
  e.stopPropagation()
  if(!confirm(`Remove ${row.company_name} from the Supplier Network? This cannot be undone.`))return
  try{await api.delete(`/api/vendor-targets/${row.id}`);onToast?.({message:`${row.company_name} removed`});load()}
  catch(err){onToast?.({type:'error',message:err.message})}
 }
 const saveEdit=async e=>{
  e.preventDefault(); if(!editing)return; setSaving(true)
  try{
   await api.put(`/api/vendor-targets/${editing.id}`,{company_name:editing.company_name,market:editing.market,registration_status:editing.registration_status,entry_route:editing.entry_route,public_evidence:editing.public_evidence,suggested_approach:editing.suggested_approach,notes:editing.notes})
   onToast?.({message:`${editing.company_name} updated`}); setEditing(null); load()
  }catch(err){onToast?.({type:'error',message:err.message})}finally{setSaving(false)}
 }
 const create=async e=>{
  e.preventDefault(); setSaving(true)
  try{
   await api.post('/api/vendor-targets',form)
   onToast?.({message:`${form.company_name} added to the Supplier Network`}); setCreateOpen(false); setForm(emptyForm); load()
  }catch(err){onToast?.({type:'error',message:err.message})}finally{setSaving(false)}
 }
 return <>
  <SectionHeader eyebrow="Alliance workspace" title="Supplier Network" text="JSAN's own registration and onboarding progress with telecom majors it is pursuing as a supplier, subcontractor or delivery partner." actions={canEdit?<Button icon="plus" onClick={()=>{setForm(emptyForm);setCreateOpen(true)}}>Add target</Button>:null}/>
  <ErrorBanner error={error} onRetry={load}/>
  {!data&&!error&&<Spinner label="Loading Supplier Network"/>}
  {data&&<>
   <div className="mini-kpis">
    <div><span>Targets tracked</span><strong>{data.items.length}</strong></div>
    {REGISTRATION_STATUSES.slice(0,3).map(s=><div key={s}><span>{s}</span><strong>{counts[s]||0}</strong></div>)}
   </div>
   <div className="toolbar-card">
    <Select value={statusFilter} onChange={e=>setStatusFilter(e.target.value)}>
     <option value="">All registration statuses</option>
     {REGISTRATION_STATUSES.map(s=><option key={s} value={s}>{s} ({counts[s]||0})</option>)}
    </Select>
    <button className="icon-btn" onClick={load} title="Refresh"><span aria-hidden>↻</span></button>
   </div>
   {items.length?<section className="panel table-panel">
    <Table keyField="id" rows={items} onRowClick={canEdit?openEdit:undefined} columns={[
     {key:'company_name',label:'Company',render:r=><div className="primary-cell"><strong>{r.company_name}</strong><span>{r.market||'Market not set'}</span></div>},
     {key:'registration_status',label:'Registration status',render:r=><Pill tone={STATUS_TONE[r.registration_status]||'neutral'}>{r.registration_status}</Pill>},
     {key:'entry_route',label:'Entry route'},
     {key:'suggested_approach',label:'Suggested JSAN approach',render:r=><span className="clamp-2">{r.suggested_approach||'—'}</span>},
     {key:'notes',label:'Notes',render:r=><span className="clamp-2">{r.notes||'—'}</span>},
     ...(canEdit?[{key:'_actions',label:'Actions',render:r=><div className="row-actions" onClick={e=>e.stopPropagation()}><button className="icon-btn" title="Edit" aria-label={`Edit ${r.company_name}`} onClick={()=>openEdit(r)}><Icon name="edit" size={16}/></button><button className="icon-btn text-danger" title="Delete" aria-label={`Delete ${r.company_name}`} onClick={e=>deleteTarget(e,r)}><Icon name="trash" size={16}/></button></div>}]:[])
    ]}/>
   </section>:<Empty title="No targets in this view" text="Change the filter, or add the first supplier/partner target."/>}
  </>}
  <Modal open={!!editing} onClose={()=>setEditing(null)} title="Edit supplier target" eyebrow={editing?.company_name} size="lg">
   {editing&&<form onSubmit={saveEdit}>
    <div className="form-grid">
     <Field label="Company name" required><Input required maxLength={220} value={editing.company_name||''} onChange={e=>setEditing(x=>({...x,company_name:e.target.value}))}/></Field>
     <Field label="Market"><Input maxLength={120} value={editing.market||''} onChange={e=>setEditing(x=>({...x,market:e.target.value}))}/></Field>
     <Field label="Registration status" required><Select value={editing.registration_status} onChange={e=>setEditing(x=>({...x,registration_status:e.target.value}))}>{REGISTRATION_STATUSES.map(s=><option key={s}>{s}</option>)}</Select></Field>
     <Field label="Entry route"><Input maxLength={220} value={editing.entry_route||''} onChange={e=>setEditing(x=>({...x,entry_route:e.target.value}))} placeholder="e.g. Supplier enquiries"/></Field>
     <Field label="Public evidence" className="span-2"><Textarea value={editing.public_evidence||''} onChange={e=>setEditing(x=>({...x,public_evidence:e.target.value}))}/></Field>
     <Field label="Suggested JSAN approach" className="span-2"><Textarea value={editing.suggested_approach||''} onChange={e=>setEditing(x=>({...x,suggested_approach:e.target.value}))}/></Field>
     <Field label="Notes" className="span-2" hint="Ongoing tracking — calls made, contacts reached, blockers."><Textarea value={editing.notes||''} onChange={e=>setEditing(x=>({...x,notes:e.target.value}))}/></Field>
    </div>
    <div className="modal-actions"><Button type="button" variant="ghost" onClick={()=>setEditing(null)}>Cancel</Button><Button type="submit" disabled={saving}>{saving?'Saving…':'Save changes'}</Button></div>
   </form>}
  </Modal>
  <Modal open={createOpen} onClose={()=>setCreateOpen(false)} title="Add supplier/partner target" eyebrow="New registration target" size="lg">
   <form onSubmit={create}>
    <div className="form-grid">
     <Field label="Company name" required><Input required maxLength={220} value={form.company_name} onChange={e=>setForm(f=>({...f,company_name:e.target.value}))}/></Field>
     <Field label="Market"><Input maxLength={120} value={form.market} onChange={e=>setForm(f=>({...f,market:e.target.value}))} placeholder="e.g. USA, Europe"/></Field>
     <Field label="Registration status" required><Select value={form.registration_status} onChange={e=>setForm(f=>({...f,registration_status:e.target.value}))}>{REGISTRATION_STATUSES.map(s=><option key={s}>{s}</option>)}</Select></Field>
     <Field label="Entry route"><Input maxLength={220} value={form.entry_route} onChange={e=>setForm(f=>({...f,entry_route:e.target.value}))} placeholder="e.g. Supplier enquiries"/></Field>
     <Field label="Public evidence" className="span-2"><Textarea value={form.public_evidence} onChange={e=>setForm(f=>({...f,public_evidence:e.target.value}))}/></Field>
     <Field label="Suggested JSAN approach" className="span-2"><Textarea value={form.suggested_approach} onChange={e=>setForm(f=>({...f,suggested_approach:e.target.value}))}/></Field>
     <Field label="Notes" className="span-2"><Textarea value={form.notes} onChange={e=>setForm(f=>({...f,notes:e.target.value}))}/></Field>
    </div>
    <div className="modal-actions"><Button type="button" variant="ghost" onClick={()=>setCreateOpen(false)}>Cancel</Button><Button type="submit" disabled={saving}>{saving?'Adding…':'Add target'}</Button></div>
   </form>
  </Modal>
 </>
}

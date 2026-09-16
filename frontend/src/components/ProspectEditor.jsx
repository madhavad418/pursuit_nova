import React,{useEffect,useState} from 'react'
import { api } from '../lib/api'
import { Button,Field,Input,Modal,Select,Spinner,Textarea } from './UI'

export const LEAD_STATUSES=['New','Assigned','Contacted','Engaged','Qualified','Converted','On Hold','Unresponsive','Disqualified','Lost']
export const LEAD_SOURCES=['LinkedIn','Referral','Event','Conference','Website','Existing Customer','Partner','Management Reference','Outbound','RFP / Tender','Other']

const str=v=>v==null?'':String(v)

// Only send what actually changed, so saving never overwrites a field the user did not touch.
const changed=(form,orig,keys)=>Object.fromEntries(keys.filter(k=>str(form[k]).trim()!==str(orig[k]).trim()).map(k=>[k,typeof form[k]==='string'?form[k].trim():form[k]]))

/**
 * Full prospect editor: company identity and links plus every prospect field.
 * Opens on a lead id, loads the latest data, and saves company and prospect changes separately.
 */
// Which fields each entry point edits, in display order.
//  list     -> Prospects tab row edit icon
//  overview -> prospect page "Edit prospect" (matches the Overview columns: Company, Vertical, Owner, Source, Geography, Remarks)
export const EDITOR_FIELDS={
 list:['temperature','status','owner_id','next_follow_up','region','country','state','city','remarks'],
 overview:['name','vertical','owner_id','source','source_detail','city','state','country','remarks'],
}
// Rows as displayed; grouped rows edit several fields under one Overview heading
const LAYOUT={list:EDITOR_FIELDS.list,overview:['name','vertical','owner_id','source_group','geography','remarks']}
const COMPANY_KEYS=new Set(['name','vertical'])

/**
 * Prospect editor. `variant` picks the field set (see EDITOR_FIELDS). Loads the latest data on open,
 * sends only changed fields, and locks what the user's role cannot change.
 */
export function ProspectEditor({leadId,open,onClose,onSaved,onToast,variant='list'}){
 const [detail,setDetail]=useState(null); const [form,setForm]=useState(null); const [users,setUsers]=useState([]); const [saving,setSaving]=useState(false); const [error,setError]=useState('')
 const keys=EDITOR_FIELDS[variant]||EDITOR_FIELDS.list
 const layout=LAYOUT[variant]||LAYOUT.list
 const overviewLabels=variant==='overview'
 useEffect(()=>{
  if(!open||!leadId)return
  let live=true; setDetail(null); setForm(null); setError('')
  Promise.all([api.get(`/api/leads/${leadId}`),api.get('/api/users/assignable').catch(()=>[])]).then(([d,u])=>{
   if(!live)return
   const l=d.lead; const orig={name:l.company_name,vertical:l.vertical,owner_id:String(l.owner_id),temperature:l.temperature,status:l.status,source:l.source,source_detail:l.source_detail,region:l.region,country:l.country,state:l.state,city:l.city,next_follow_up:l.next_follow_up,remarks:l.remarks}
   setDetail({...d,orig}); setForm(Object.fromEntries(Object.entries(orig).map(([k,v])=>[k,str(v)]))); setUsers(u)
  }).catch(e=>live&&setError(e.message))
  return()=>{live=false}
 },[open,leadId])
 const set=(k,v)=>setForm(f=>({...f,[k]:v}))
 const perms=detail?.permissions||{}
 const locked=k=>COMPANY_KEYS.has(k)?!perms.can_edit_company:k==='owner_id'?!perms.can_reassign:!perms.can_edit
 const canSave=keys.some(k=>!locked(k))
 const save=async e=>{
  e.preventDefault(); if(!detail)return
  const editable=keys.filter(k=>!locked(k))
  const companyChanges=changed(form,detail.orig,editable.filter(k=>COMPANY_KEYS.has(k)))
  const leadChanges=changed(form,detail.orig,editable.filter(k=>!COMPANY_KEYS.has(k)))
  if('owner_id' in leadChanges)leadChanges.owner_id=Number(leadChanges.owner_id)
  if(!Object.keys(companyChanges).length&&!Object.keys(leadChanges).length){onToast?.({message:'No changes to save'});onClose();return}
  setSaving(true)
  const done=[]
  try{
   if(Object.keys(companyChanges).length){await api.put(`/api/companies/${detail.lead.company_id}`,companyChanges);done.push('company')}
   if(Object.keys(leadChanges).length){await api.put(`/api/leads/${detail.lead.id}`,leadChanges);done.push('prospect')}
   onToast?.({message:`${form.name||detail.lead.company_name} updated`}); onClose(); onSaved?.()
  }catch(err){
   onToast?.({type:'error',message:done.length?`Saved the ${done.join(' and ')} details, but: ${err.message}`:err.message})
   if(done.length)onSaved?.()
  }finally{setSaving(false)}
 }
 const ownerOptions=form&&!users.some(u=>String(u.id)===form.owner_id)?[{id:form.owner_id,name:detail?.lead.owner_name||'Current owner',role:'current'},...users]:users
 const input=(k,props={})=><Input disabled={locked(k)} value={form[k]} onChange={e=>set(k,e.target.value)} {...props}/>
 const FIELDS={
  name:()=> <Field key="name" label={overviewLabels?'Company':'Company name'} required>{input('name',{required:true,maxLength:220})}</Field>,
  vertical:()=> <Field key="vertical" label="Vertical" required>{input('vertical',{required:true,maxLength:120,placeholder:'e.g. Telecommunications'})}</Field>,
  owner_id:()=> <Field key="owner_id" label="Owner"><Select disabled={locked('owner_id')} value={form.owner_id} onChange={e=>set('owner_id',e.target.value)}>{ownerOptions.map(u=><option key={u.id} value={u.id}>{u.name}{u.role&&u.role!=='current'?` · ${u.role}`:''}</option>)}</Select></Field>,
  temperature:()=> <Field key="temperature" label="Signal"><Select disabled={locked('temperature')} value={form.temperature} onChange={e=>set('temperature',e.target.value)}>{['Hot','Warm','Cold'].map(x=><option key={x}>{x}</option>)}</Select></Field>,
  status:()=> <Field key="status" label="Status"><Select disabled={locked('status')} value={form.status} onChange={e=>set('status',e.target.value)}>{LEAD_STATUSES.map(x=><option key={x}>{x}</option>)}</Select></Field>,
  source:()=> <Field key="source" label="Source"><Select disabled={locked('source')} value={form.source} onChange={e=>set('source',e.target.value)}>{(LEAD_SOURCES.includes(form.source)?LEAD_SOURCES:[form.source,...LEAD_SOURCES]).map(x=><option key={x}>{x}</option>)}</Select></Field>,
  source_detail:()=> <Field key="source_detail" label="Source detail">{input('source_detail',{maxLength:255})}</Field>,
  next_follow_up:()=> <Field key="next_follow_up" label="Next follow-up">{input('next_follow_up',{type:'date'})}</Field>,
  region:()=> <Field key="region" label="Region">{input('region',{maxLength:80})}</Field>,
  country:()=> <Field key="country" label="Country">{input('country',{maxLength:100})}</Field>,
  state:()=> <Field key="state" label="State">{input('state',{maxLength:100})}</Field>,
  city:()=> <Field key="city" label="City">{input('city',{maxLength:100})}</Field>,
  source_group:()=> <div key="source_group" className="field"><span>Source</span><div className="field-group source-group">
   <Select aria-label="Source" disabled={locked('source')} value={form.source} onChange={e=>set('source',e.target.value)}>{(LEAD_SOURCES.includes(form.source)?LEAD_SOURCES:[form.source,...LEAD_SOURCES]).map(x=><option key={x}>{x}</option>)}</Select>
   {input('source_detail',{'aria-label':'Source detail',maxLength:255,placeholder:'Detail, e.g. referred by'})}
  </div></div>,
  geography:()=> <div key="geography" className="field span-2"><span>Geography</span><div className="field-group geography-group">
   {input('city',{'aria-label':'City',maxLength:100,placeholder:'City'})}
   {input('state',{'aria-label':'State',maxLength:100,placeholder:'State'})}
   {input('country',{'aria-label':'Country',maxLength:100,placeholder:'Country'})}
  </div></div>,
  remarks:()=> <Field key="remarks" label="Remarks" className="span-2"><Textarea disabled={locked('remarks')} value={form.remarks} onChange={e=>set('remarks',e.target.value)}/></Field>,
 }
 return <Modal open={open} onClose={onClose} title="Edit prospect" eyebrow={detail?.lead.company_name||'Loading…'} size="lg">
  {error&&<div className="error-banner"><div><strong>Could not load this prospect</strong><span>{error}</span></div></div>}
  {!form&&!error&&<Spinner label="Loading prospect"/>}
  {form&&<form onSubmit={save}>
   {!canSave&&<div className="warning-callout"><span>You can view this prospect but not change it.</span></div>}
   <div className="form-grid">{layout.map(k=>FIELDS[k]())}</div>
   <div className="modal-actions"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>{canSave&&<Button type="submit" disabled={saving}>{saving?'Saving…':'Save changes'}</Button>}</div>
  </form>}
 </Modal>
}

const CONTACT_FIELDS=['name','designation','department','email','phone','linkedin_url','location','remarks','is_primary']

/** Edit or remove one contact. `contact` null closes the dialog. */
export function ContactEditor({contact,companyName,onClose,onSaved,onToast}){
 const [form,setForm]=useState(null); const [saving,setSaving]=useState(false)
 useEffect(()=>{setForm(contact?{...Object.fromEntries(CONTACT_FIELDS.map(k=>[k,k==='is_primary'?!!contact[k]:str(contact[k])]))}:null)},[contact?.id])
 const set=(k,v)=>setForm(f=>({...f,[k]:v}))
 const save=async e=>{
  e.preventDefault()
  const diff=Object.fromEntries(CONTACT_FIELDS.filter(k=>k==='is_primary'?form[k]!==!!contact[k]:form[k].trim()!==str(contact[k]).trim()).map(k=>[k,k==='is_primary'?form[k]:form[k].trim()]))
  if(!Object.keys(diff).length){onClose();return}
  setSaving(true)
  try{await api.put(`/api/contacts/${contact.id}`,diff);onToast?.({message:`${form.name} updated`});onClose();onSaved?.()}catch(err){onToast?.({type:'error',message:err.message})}finally{setSaving(false)}
 }
 const remove=async()=>{
  if(!confirm(`Remove ${contact.name} from ${companyName}? Meetings and history stay as they are.`))return
  setSaving(true)
  try{await api.put(`/api/contacts/${contact.id}`,{active:false});onToast?.({message:`${contact.name} removed`});onClose();onSaved?.()}catch(err){onToast?.({type:'error',message:err.message})}finally{setSaving(false)}
 }
 return <Modal open={!!contact&&!!form} onClose={onClose} title="Edit contact" eyebrow={companyName}>{form&&<form onSubmit={save}>
  <div className="form-grid">
   <Field label="Name" required><Input required maxLength={180} value={form.name} onChange={e=>set('name',e.target.value)}/></Field>
   <Field label="Designation"><Input maxLength={180} value={form.designation} onChange={e=>set('designation',e.target.value)}/></Field>
   <Field label="Department"><Input maxLength={120} value={form.department} onChange={e=>set('department',e.target.value)}/></Field>
   <Field label="Email"><Input type="email" maxLength={190} value={form.email} onChange={e=>set('email',e.target.value)}/></Field>
   <Field label="Phone"><Input maxLength={80} value={form.phone} onChange={e=>set('phone',e.target.value)}/></Field>
   <Field label="LinkedIn profile"><Input value={form.linkedin_url} onChange={e=>set('linkedin_url',e.target.value)} placeholder="https://linkedin.com/in/…"/></Field>
   <Field label="Location"><Input maxLength={220} value={form.location} onChange={e=>set('location',e.target.value)}/></Field>
   <Field label="Remarks"><Input value={form.remarks} onChange={e=>set('remarks',e.target.value)}/></Field>
  </div>
  <label className="check-row"><input type="checkbox" checked={form.is_primary} onChange={e=>set('is_primary',e.target.checked)}/> Primary contact for this company</label>
  <div className="modal-actions split"><Button type="button" variant="ghost" className="text-danger" onClick={remove} disabled={saving}>Remove contact</Button><span/><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" disabled={saving}>{saving?'Saving…':'Save changes'}</Button></div>
 </form>}</Modal>
}

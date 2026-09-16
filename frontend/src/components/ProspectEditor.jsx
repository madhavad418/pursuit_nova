import React,{useEffect,useState} from 'react'
import { api } from '../lib/api'
import { Button,Field,Input,Modal,Select,Spinner,Textarea } from './UI'

export const LEAD_STATUSES=['New','Assigned','Contacted','Engaged','Qualified','Converted','On Hold','Unresponsive','Disqualified','Lost']
export const LEAD_SOURCES=['LinkedIn','Referral','Event','Conference','Website','Existing Customer','Partner','Management Reference','Outbound','RFP / Tender','Other']

const COMPANY_FIELDS=['name','vertical','website','linkedin_url','external_url','company_remarks']
const LEAD_FIELDS=['owner_id','temperature','status','source','source_detail','region','country','state','city','next_follow_up','remarks']
const str=v=>v==null?'':String(v)

// Only send what actually changed, so saving never overwrites a field the user did not touch.
const changed=(form,orig,keys)=>Object.fromEntries(keys.filter(k=>str(form[k]).trim()!==str(orig[k]).trim()).map(k=>[k,typeof form[k]==='string'?form[k].trim():form[k]]))

/**
 * Full prospect editor: company identity and links plus every prospect field.
 * Opens on a lead id, loads the latest data, and saves company and prospect changes separately.
 */
export function ProspectEditor({leadId,open,onClose,onSaved,onToast}){
 const [detail,setDetail]=useState(null); const [form,setForm]=useState(null); const [users,setUsers]=useState([]); const [saving,setSaving]=useState(false); const [error,setError]=useState('')
 useEffect(()=>{
  if(!open||!leadId)return
  let live=true; setDetail(null); setForm(null); setError('')
  Promise.all([api.get(`/api/leads/${leadId}`),api.get('/api/users/assignable').catch(()=>[])]).then(([d,u])=>{
   if(!live)return
   const l=d.lead; const orig={name:l.company_name,vertical:l.vertical,website:l.website,linkedin_url:l.linkedin_url,external_url:l.external_url,company_remarks:l.company_remarks,owner_id:String(l.owner_id),temperature:l.temperature,status:l.status,source:l.source,source_detail:l.source_detail,region:l.region,country:l.country,state:l.state,city:l.city,next_follow_up:l.next_follow_up,remarks:l.remarks}
   setDetail({...d,orig}); setForm(Object.fromEntries(Object.entries(orig).map(([k,v])=>[k,str(v)]))); setUsers(u)
  }).catch(e=>live&&setError(e.message))
  return()=>{live=false}
 },[open,leadId])
 const set=(k,v)=>setForm(f=>({...f,[k]:v}))
 const perms=detail?.permissions||{}
 const save=async e=>{
  e.preventDefault(); if(!detail)return
  const companyChanges=perms.can_edit_company?changed(form,detail.orig,COMPANY_FIELDS):{}
  if('company_remarks' in companyChanges){companyChanges.remarks=companyChanges.company_remarks;delete companyChanges.company_remarks}
  const leadChanges=perms.can_edit?changed(form,detail.orig,LEAD_FIELDS):{}
  if(!perms.can_reassign)delete leadChanges.owner_id
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
 const ro=!perms.can_edit_company
 return <Modal open={open} onClose={onClose} title="Edit prospect" eyebrow={detail?.lead.company_name||'Loading…'} size="xl">
  {error&&<div className="error-banner"><div><strong>Could not load this prospect</strong><span>{error}</span></div></div>}
  {!form&&!error&&<Spinner label="Loading prospect"/>}
  {form&&<form onSubmit={save}>
   {!perms.can_edit&&<div className="warning-callout"><span>You can view this prospect but not change it.</span></div>}
   <div className="form-section"><h3>Company</h3>{ro&&perms.can_edit&&<p className="subtle">Your role cannot change company details.</p>}<div className="form-grid">
    <Field label="Company name" required><Input required maxLength={220} disabled={ro} value={form.name} onChange={e=>set('name',e.target.value)}/></Field>
    <Field label="Vertical" required><Input required maxLength={120} disabled={ro} value={form.vertical} onChange={e=>set('vertical',e.target.value)} placeholder="e.g. Telecommunications"/></Field>
    <Field label="Website"><Input disabled={ro} value={form.website} onChange={e=>set('website',e.target.value)} placeholder="https://company.com"/></Field>
    <Field label="Company LinkedIn page"><Input disabled={ro} value={form.linkedin_url} onChange={e=>set('linkedin_url',e.target.value)} placeholder="https://linkedin.com/company/…"/></Field>
    <Field label="Other link" hint="e.g. tender portal or article"><Input disabled={ro} value={form.external_url} onChange={e=>set('external_url',e.target.value)} placeholder="https://"/></Field>
    <Field label="Company notes"><Input disabled={ro} value={form.company_remarks} onChange={e=>set('company_remarks',e.target.value)}/></Field>
   </div></div>
   <fieldset className="form-section plain-fieldset" disabled={!perms.can_edit}><h3>Prospect</h3><div className="form-grid">
    <Field label="Owner" hint={perms.can_reassign?undefined:'Your role cannot reassign prospects.'}><Select disabled={!perms.can_reassign} value={form.owner_id} onChange={e=>set('owner_id',e.target.value)}>{ownerOptions.map(u=><option key={u.id} value={u.id}>{u.name}{u.role&&u.role!=='current'?` · ${u.role}`:''}</option>)}</Select></Field>
    <Field label="Signal"><Select value={form.temperature} onChange={e=>set('temperature',e.target.value)}>{['Hot','Warm','Cold'].map(x=><option key={x}>{x}</option>)}</Select></Field>
    <Field label="Status"><Select value={form.status} onChange={e=>set('status',e.target.value)}>{LEAD_STATUSES.map(x=><option key={x}>{x}</option>)}</Select></Field>
    <Field label="Source"><Select value={form.source} onChange={e=>set('source',e.target.value)}>{(LEAD_SOURCES.includes(form.source)?LEAD_SOURCES:[form.source,...LEAD_SOURCES]).map(x=><option key={x}>{x}</option>)}</Select></Field>
    <Field label="Source detail"><Input maxLength={255} value={form.source_detail} onChange={e=>set('source_detail',e.target.value)}/></Field>
    <Field label="Next follow-up"><Input type="date" value={form.next_follow_up} onChange={e=>set('next_follow_up',e.target.value)}/></Field>
    <Field label="Region"><Input maxLength={80} value={form.region} onChange={e=>set('region',e.target.value)}/></Field>
    <Field label="Country"><Input maxLength={100} value={form.country} onChange={e=>set('country',e.target.value)}/></Field>
    <Field label="State"><Input maxLength={100} value={form.state} onChange={e=>set('state',e.target.value)}/></Field>
    <Field label="City"><Input maxLength={100} value={form.city} onChange={e=>set('city',e.target.value)}/></Field>
    <Field label="Remarks" className="span-2"><Textarea value={form.remarks} onChange={e=>set('remarks',e.target.value)}/></Field>
   </div></fieldset>
   <div className="modal-actions"><Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>{(perms.can_edit||perms.can_edit_company)&&<Button type="submit" disabled={saving}>{saving?'Saving…':'Save changes'}</Button>}</div>
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

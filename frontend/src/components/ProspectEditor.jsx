import React,{useEffect,useState} from 'react'
import { api } from '../lib/api'
import { Button,Field,Input,Modal,Select,Spinner,Textarea } from './UI'

export const LEAD_STATUSES=['New','Assigned','Contacted','Engaged','Qualified','Converted','On Hold','Unresponsive','Disqualified','Lost']
export const LEAD_SOURCES=['LinkedIn','Referral','Event','Conference','Website','Existing Customer','Partner','Management Reference','Outbound','RFP / Tender','Other']

export const REGIONS=['North America','Europe','APAC','Middle East','Africa','Latin America','Global']

const str=v=>v==null?'':String(v)

// Only send what actually changed, so saving never overwrites a field the user did not touch.
const changed=(form,orig,keys)=>Object.fromEntries(keys.filter(k=>str(form[k]).trim()!==str(orig[k]).trim()).map(k=>[k,form[k].trim()]))

// The edit form mirrors "Create prospect": Company, Primary contact, Prospect ownership (plus Status, which only editing can change).
const COMPANY_KEYS=['name','vertical','website','linkedin_url']
const LEAD_KEYS=['region','country','state','city','owner_id','temperature','source','source_detail','next_follow_up','status','remarks']
// Form key -> contact field
const CONTACT_KEYS={contact_name:'name',designation:'designation',email:'email',phone:'phone',contact_linkedin:'linkedin_url'}

/**
 * Edit a prospect from the Prospects row or the Overview card. Loads the latest data on open,
 * sends only changed fields, and locks what the user's role cannot change.
 */
export function ProspectEditor({leadId,open,onClose,onSaved,onToast}){
 const [detail,setDetail]=useState(null); const [form,setForm]=useState(null); const [users,setUsers]=useState([]); const [saving,setSaving]=useState(false); const [error,setError]=useState('')
 useEffect(()=>{
  if(!open||!leadId)return
  let live=true; setDetail(null); setForm(null); setError('')
  Promise.all([api.get(`/api/leads/${leadId}`),api.get('/api/users/assignable').catch(()=>[])]).then(([d,u])=>{
   if(!live)return
   const l=d.lead; const contacts=d.contacts||[]
   const primary=contacts.find(c=>c.is_primary)||contacts[0]||null   // same contact the Overview shows as primary
   const orig={name:l.company_name,vertical:l.vertical,website:l.website,linkedin_url:l.linkedin_url,region:l.region,country:l.country,state:l.state,city:l.city,
    owner_id:String(l.owner_id),temperature:l.temperature,source:l.source,source_detail:l.source_detail,next_follow_up:l.next_follow_up,status:l.status,remarks:l.remarks,
    ...Object.fromEntries(Object.entries(CONTACT_KEYS).map(([k,f])=>[k,primary?.[f]]))}
   setDetail({...d,orig,primary}); setForm(Object.fromEntries(Object.entries(orig).map(([k,v])=>[k,str(v)]))); setUsers(u)
  }).catch(e=>live&&setError(e.message))
  return()=>{live=false}
 },[open,leadId])
 const set=(k,v)=>setForm(f=>({...f,[k]:v}))
 const perms=detail?.permissions||{}
 const lockedContactFields=new Set(perms.locked_contact_fields||[])
 const locked=k=>COMPANY_KEYS.includes(k)?!perms.can_edit_company
  :k in CONTACT_KEYS?(!perms.can_edit_contacts||lockedContactFields.has(CONTACT_KEYS[k]))
  :k==='owner_id'?!perms.can_reassign:!perms.can_edit
 const allKeys=[...COMPANY_KEYS,...Object.keys(CONTACT_KEYS),...LEAD_KEYS]
 const canSave=detail&&allKeys.some(k=>!locked(k))
 const save=async e=>{
  e.preventDefault(); if(!detail)return
  const editable=allKeys.filter(k=>!locked(k))
  const companyChanges=changed(form,detail.orig,editable.filter(k=>COMPANY_KEYS.includes(k)))
  const leadChanges=changed(form,detail.orig,editable.filter(k=>LEAD_KEYS.includes(k)))
  if('owner_id' in leadChanges)leadChanges.owner_id=Number(leadChanges.owner_id)
  const contactChanges=Object.fromEntries(Object.entries(changed(form,detail.orig,editable.filter(k=>k in CONTACT_KEYS))).map(([k,v])=>[CONTACT_KEYS[k],v]))
  const hasContact=Object.keys(contactChanges).length>0
  // A primary contact needs a name, whether it already exists or is being added here
  if(hasContact&&!form.contact_name.trim()){onToast?.({type:'error',message:'Primary contact name is required'});return}
  if(!Object.keys(companyChanges).length&&!hasContact&&!Object.keys(leadChanges).length){onToast?.({message:'No changes to save'});onClose();return}
  setSaving(true)
  const done=[]
  try{
   if(Object.keys(companyChanges).length){await api.put(`/api/companies/${detail.lead.company_id}`,companyChanges);done.push('company')}
   if(hasContact){
    if(detail.primary)await api.put(`/api/contacts/${detail.primary.id}`,contactChanges)
    else await api.post(`/api/companies/${detail.lead.company_id}/contacts`,{...contactChanges,is_primary:true})
    done.push('contact')
   }
   if(Object.keys(leadChanges).length){await api.put(`/api/leads/${detail.lead.id}`,leadChanges);done.push('prospect')}
   onToast?.({message:`${form.name||detail.lead.company_name} updated`}); onClose(); onSaved?.()
  }catch(err){
   onToast?.({type:'error',message:done.length?`Saved the ${done.join(' and ')} details, but: ${err.message}`:err.message})
   if(done.length)onSaved?.()
  }finally{setSaving(false)}
 }
 const ownerOptions=form&&!users.some(u=>String(u.id)===form.owner_id)?[{id:form.owner_id,name:detail?.lead.owner_name||'Current owner',role:'current'},...users]:users
 const withCurrent=(list,v)=>v&&!list.includes(v)?[v,...list]:list
 const input=(k,props={})=><Input disabled={locked(k)} value={form[k]} onChange={e=>set(k,e.target.value)} {...props}/>
 const select=(k,options)=><Select disabled={locked(k)} value={form[k]} onChange={e=>set(k,e.target.value)}>{options}</Select>
 return <Modal open={open} onClose={onClose} title="Edit prospect" eyebrow={detail?.lead.company_name||'Loading…'} size="xl">
  {error&&<div className="error-banner"><div><strong>Could not load this prospect</strong><span>{error}</span></div></div>}
  {!form&&!error&&<Spinner label="Loading prospect"/>}
  {form&&<form onSubmit={save}>
   {!canSave&&<div className="warning-callout"><span>You can view this prospect but not change it.</span></div>}
   <div className="form-section"><h3>Company</h3><div className="form-grid">
    <Field label="Company name" required>{input('name',{required:true,maxLength:220})}</Field>
    <Field label="Vertical" required>{input('vertical',{required:true,maxLength:120,placeholder:'e.g. Telecommunications'})}</Field>
    <Field label="Website">{input('website',{placeholder:'https://'})}</Field>
    <Field label="LinkedIn company">{input('linkedin_url',{placeholder:'https://linkedin.com/company/...'})}</Field>
    <Field label="Region">{select('region',<><option value="">Select region</option>{withCurrent(REGIONS,form.region).map(x=><option key={x}>{x}</option>)}</>)}</Field>
    <Field label="Country">{input('country',{maxLength:100})}</Field>
    <Field label="State">{input('state',{maxLength:100})}</Field>
    <Field label="City">{input('city',{maxLength:100})}</Field>
   </div></div>
   <div className="form-section"><h3>Primary contact</h3><div className="form-grid">
    <Field label="Name">{input('contact_name',{maxLength:180,required:!!detail.primary})}</Field>
    <Field label="Designation">{input('designation',{maxLength:180})}</Field>
    <Field label="Email">{input('email',{type:'email',maxLength:190})}</Field>
    <Field label="Phone">{input('phone',{maxLength:80})}</Field>
    <Field label="LinkedIn">{input('contact_linkedin')}</Field>
   </div></div>
   <div className="form-section"><h3>Prospect ownership</h3><div className="form-grid">
    <Field label="Owner">{select('owner_id',ownerOptions.map(u=><option key={u.id} value={u.id}>{u.name}{u.role&&u.role!=='current'?` · ${u.role}`:''}</option>))}</Field>
    <Field label="Signal">{select('temperature',['Hot','Warm','Cold'].map(x=><option key={x}>{x}</option>))}</Field>
    <Field label="Source">{select('source',withCurrent(LEAD_SOURCES,form.source).map(x=><option key={x}>{x}</option>))}</Field>
    <Field label="Source detail">{input('source_detail',{maxLength:255})}</Field>
    <Field label="Next follow-up">{input('next_follow_up',{type:'date'})}</Field>
    <Field label="Status">{select('status',withCurrent(LEAD_STATUSES,form.status).map(x=><option key={x}>{x}</option>))}</Field>
    <Field label="Remarks" className="span-2"><Textarea disabled={locked('remarks')} value={form.remarks} onChange={e=>set('remarks',e.target.value)}/></Field>
   </div></div>
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

import React,{useEffect,useState} from 'react'
import { api } from '../lib/api'
import { Button,Empty,ErrorBanner,Field,Input,Modal,Pill,SectionHeader,Select,Spinner,Table,Textarea } from '../components/UI'
import { Icon } from '../components/Icons'
import { useAuth } from '../components/Auth'
import { dateText } from '../lib/format'
import RfpDocuments from '../components/RfpDocuments'

// Two independent participation tracks share one status list, mirroring the pipeline the business
// team described: JSAN's own bid, and JSAN bidding together with a vendor/subcontractor.
const FALLBACK_STATUSES=['Initiated','In progress','Submitted','Awaited response','Awarded to JSAN','Not awarded to JSAN','Close']
const FALLBACK_QA=['Not started','Questions submitted','Answers received','Closed']
const STATUS_TONE={'Initiated':'neutral','In progress':'info','Submitted':'info','Awaited response':'warning','Awarded to JSAN':'success','Not awarded to JSAN':'danger','Close':'neutral'}
const QA_TONE={'Not started':'neutral','Questions submitted':'info','Answers received':'success','Closed':'neutral'}

const emptyForm={name:'',description:'',rfp_date:'',submission_eta:'',qa_timeline:'',qa_status:'Not started',technical_response:'',pricing:'',jsan_status:'Initiated',vendor_status:'Initiated'}

const FIELD_TABS=['Overview','Description','Technical response','Pricing']
// These tabs hold document uploads, which need a saved RFP id to attach to.
const DOC_TABS=['Description','Technical response']

// JSAN's reference technical response with every answer removed, shipped from frontend/public/templates
// (regenerate it with scripts/make_technical_response_template.py).
const TEMPLATE_FILE = '/templates/JSAN_Technical_Response_Template.docx'

function RfpFields({v,set,statuses,qaStatuses,disabled,tab,gotoTab,extraTabs,docsProps}){
 return <>
  <div className="tabs">{FIELD_TABS.map(x=><button key={x} type="button" className={tab===x?'active':''} onClick={()=>gotoTab(x)}>{x}</button>)}{extraTabs}</div>
  {tab==='Overview'&&<div className="form-grid">
   <Field label="RFP name" required className="span-2"><Input required maxLength={220} disabled={disabled} value={v.name||''} onChange={e=>set('name',e.target.value)} placeholder="e.g. ABC telecom managed-services tender"/></Field>
   <Field label="Date of RFP"><Input type="date" disabled={disabled} value={v.rfp_date||''} onChange={e=>set('rfp_date',e.target.value)}/></Field>
   <Field label="ETA for submission"><Input type="date" disabled={disabled} value={v.submission_eta||''} onChange={e=>set('submission_eta',e.target.value)}/></Field>
   <Field label="JSAN participation status"><Select disabled={disabled} value={v.jsan_status||'Initiated'} onChange={e=>set('jsan_status',e.target.value)}>{statuses.map(s=><option key={s}>{s}</option>)}</Select></Field>
   <Field label="JSAN participation with vendor"><Select disabled={disabled} value={v.vendor_status||'Initiated'} onChange={e=>set('vendor_status',e.target.value)}>{statuses.map(s=><option key={s}>{s}</option>)}</Select></Field>
   <Field label="Q&A timeline" className="span-2" hint="Key clarification dates — when questions are due and answers expected."><Input maxLength={220} disabled={disabled} value={v.qa_timeline||''} onChange={e=>set('qa_timeline',e.target.value)} placeholder="e.g. Questions by 01 Oct, answers by 05 Oct"/></Field>
   <Field label="Q&A status"><Select disabled={disabled} value={v.qa_status||'Not started'} onChange={e=>set('qa_status',e.target.value)}>{qaStatuses.map(s=><option key={s}>{s}</option>)}</Select></Field>
  </div>}
  {tab==='Description'&&<div className="form-grid">
   <Field label="RFP description" className="span-2"><Textarea rows={10} disabled={disabled} value={v.description||''} onChange={e=>set('description',e.target.value)}/></Field>
  </div>}
  {tab==='Description'&&docsProps&&<RfpDocuments {...docsProps} category="description"/>}
  {tab==='Technical response'&&<div className="form-grid">
   <div className="template-bar span-2">
    <div className="template-bar-copy"><strong>JSAN technical response template</strong><span>The reference response with every answer removed - 13 sections, exhibit tables and evidence columns, ready to fill in.</span></div>
    <a className="btn btn-soft" href={TEMPLATE_FILE} download>Download template (.docx)</a>
   </div>
   <Field label="JSAN technical response" className="span-2"><Textarea rows={10} disabled={disabled} value={v.technical_response||''} onChange={e=>set('technical_response',e.target.value)}/></Field>
  </div>}
  {tab==='Technical response'&&docsProps&&<RfpDocuments {...docsProps} category="technical_response"/>}
  {tab==='Pricing'&&<div className="form-grid">
   <Field label="Pricing" className="span-2" hint="Commercial summary, budget or pricing notes."><Textarea rows={10} disabled={disabled} value={v.pricing||''} onChange={e=>set('pricing',e.target.value)}/></Field>
  </div>}
 </>
}

const FORM_KEYS=['name','description','rfp_date','submission_eta','qa_timeline','qa_status','technical_response','pricing','jsan_status','vendor_status']
const pick=(o,keys)=>Object.fromEntries(keys.map(k=>[k,o[k]]))

export default function RfpsPage({onToast}){
 const {has}=useAuth(); const canEdit=has('COMPANY_EDIT')
 const [data,setData]=useState(null); const [error,setError]=useState(null)
 const [statusFilter,setStatusFilter]=useState('')
 // `editor` holds whichever RFP is open for create/edit; it has no id until the first save.
 const [editor,setEditor]=useState(null); const [editorTab,setEditorTab]=useState('Overview'); const [saving,setSaving]=useState(false)
 const load=()=>{setError(null);api.get('/api/rfps').then(setData).catch(setError)}
 useEffect(()=>{load()},[])
 const statuses=data?.statuses||FALLBACK_STATUSES
 const qaStatuses=data?.qa_statuses||FALLBACK_QA
 const canDownload=!!data?.can_download
 const items=(data?.items||[]).filter(x=>!statusFilter||x.jsan_status===statusFilter||x.vendor_status===statusFilter)
 const counts=Object.fromEntries(statuses.map(s=>[s,(data?.items||[]).filter(x=>x.jsan_status===s||x.vendor_status===s).length]))
 const openCreate=()=>{setEditor({...emptyForm});setEditorTab('Overview')}
 const openEdit=r=>{setEditor({...r});setEditorTab('Overview')}
 const closeEditor=()=>{setEditor(null)}
 // Pull fresh rows after a document change, patching only the open editor's documents so unsaved field edits survive.
 const onDocsChanged=async()=>{try{const d=await api.get('/api/rfps');setData(d);setEditor(cur=>{if(!cur?.id)return cur;const fresh=d.items.find(x=>x.id===cur.id);return fresh?{...cur,documents:fresh.documents,document_count:fresh.document_count}:cur})}catch(e){setError(e)}}
 // Description/Technical response/Documents tabs hold uploads, which need a saved id; create a draft
 // RFP the first time the user reaches one of them from the "Add RFP" form.
 const gotoTab=async tab=>{
  if(!editor.id&&(DOC_TABS.includes(tab)||tab==='Documents')){
   const name=(editor.name||'').trim()
   if(!name){onToast?.({type:'error',message:'Add the RFP name before attaching documents'});return}
   setSaving(true)
   try{
    const created=await api.post('/api/rfps',pick({...editor,name},FORM_KEYS))
    onToast?.({message:`${created.name} added`})
    setEditor(created); load()
   }catch(err){onToast?.({type:'error',message:err.message});setSaving(false);return}
   setSaving(false)
  }
  setEditorTab(tab)
 }
 const save=async e=>{
  e.preventDefault(); if(!editor)return; setSaving(true)
  try{
   if(editor.id){
    await api.put(`/api/rfps/${editor.id}`,pick(editor,FORM_KEYS))
    onToast?.({message:`${editor.name} updated`})
    const d=await api.get('/api/rfps'); setData(d); const fresh=d.items.find(x=>x.id===editor.id)||editor; setEditor(fresh)
   }else{
    await api.post('/api/rfps',pick(editor,FORM_KEYS))
    onToast?.({message:`${editor.name} added`})
    closeEditor(); load()
   }
  }catch(err){onToast?.({type:'error',message:err.message})}finally{setSaving(false)}
 }
 const removeRfp=async(e,r)=>{
  e.stopPropagation()
  if(!confirm(`Delete RFP "${r.name}" and its uploaded documents? This cannot be undone.`))return
  try{await api.delete(`/api/rfps/${r.id}`);onToast?.({message:`${r.name} deleted`});load()}
  catch(err){onToast?.({type:'error',message:err.message})}
 }
 return <>
  <SectionHeader eyebrow="Tender workspace" title="RFPs" text="Track every request for proposal JSAN pursues — timelines, clarifications, technical response, pricing and both participation tracks." actions={canEdit?<Button icon="plus" onClick={openCreate}>Add RFP</Button>:null}/>
  <ErrorBanner error={error} onRetry={load}/>
  {!data&&!error&&<Spinner label="Loading RFPs"/>}
  {data&&<>
   <div className="mini-kpis">
    <div><span>RFPs tracked</span><strong>{data.items.length}</strong></div>
    {statuses.slice(0,3).map(s=><div key={s}><span>{s}</span><strong>{counts[s]||0}</strong></div>)}
   </div>
   <div className="toolbar-card">
    <Select value={statusFilter} onChange={e=>setStatusFilter(e.target.value)}>
     <option value="">All participation statuses</option>
     {statuses.map(s=><option key={s} value={s}>{s} ({counts[s]||0})</option>)}
    </Select>
    <button className="icon-btn" onClick={load} title="Refresh" aria-label="Refresh"><span aria-hidden>↻</span></button>
   </div>
   {items.length?<section className="panel table-panel">
    <Table keyField="id" rows={items} onRowClick={openEdit} columns={[
     {key:'name',label:'RFP',render:r=><div className="primary-cell"><strong>{r.name}</strong><span className="clamp-2">{r.description||'No description'}</span></div>},
     {key:'rfp_date',label:'Date of RFP',render:r=>dateText(r.rfp_date)},
     {key:'submission_eta',label:'Submission ETA',render:r=>dateText(r.submission_eta)},
     {key:'qa_status',label:'Q&A',render:r=><Pill tone={QA_TONE[r.qa_status]||'neutral'}>{r.qa_status}</Pill>},
     {key:'jsan_status',label:'JSAN participation',render:r=><Pill tone={STATUS_TONE[r.jsan_status]||'neutral'}>{r.jsan_status}</Pill>},
     {key:'vendor_status',label:'With vendor',render:r=><Pill tone={STATUS_TONE[r.vendor_status]||'neutral'}>{r.vendor_status}</Pill>},
     {key:'document_count',label:'Docs',align:'right',render:r=>r.document_count||0},
     ...(canEdit?[{key:'_actions',label:'Actions',render:r=><div className="row-actions" onClick={e=>e.stopPropagation()}><button className="icon-btn" title="Edit" aria-label={`Edit ${r.name}`} onClick={()=>openEdit(r)}><Icon name="edit" size={16}/></button><button className="icon-btn text-danger" title="Delete" aria-label={`Delete ${r.name}`} onClick={e=>removeRfp(e,r)}><Icon name="trash" size={16}/></button></div>}]:[])
    ]}/>
   </section>:<Empty title="No RFPs in this view" text="Change the filter, or add the first RFP you are pursuing."/>}
  </>}
  <Modal open={!!editor} onClose={closeEditor} title={editor?.id?editor.name:'Add RFP'} eyebrow={editor?.id?'RFP detail':'New tender'} size="xl">
   {editor&&<>
    <form onSubmit={save}>
     <RfpFields v={editor} set={(k,val)=>setEditor(d=>({...d,[k]:val}))} statuses={statuses} qaStatuses={qaStatuses} disabled={!canEdit} tab={editorTab} gotoTab={gotoTab}
      docsProps={editor.id?{rfp:editor,canEdit,canDownload,onChanged:onDocsChanged,onToast}:null}
      extraTabs={editor.id?<button type="button" className={editorTab==='Documents'?'active':''} onClick={()=>gotoTab('Documents')}>Documents{editor.document_count?` (${editor.document_count})`:''}</button>:null}/>
     {editorTab!=='Documents'&&<div className="modal-actions"><Button type="button" variant="ghost" onClick={closeEditor}>{editor.id?'Close':'Cancel'}</Button>{canEdit&&<Button type="submit" disabled={saving}>{saving?'Saving…':editor.id?'Save changes':'Add RFP'}</Button>}</div>}
    </form>
    {editorTab==='Documents'&&editor.id&&<RfpDocuments rfp={editor} category="all" canEdit={canEdit} canDownload={canDownload} onChanged={onDocsChanged} onToast={onToast}/>}
   </>}
  </Modal>
 </>
}

import React,{useEffect,useRef,useState} from 'react'
import { api } from '../lib/api'
import { Button,Modal,Spinner } from './UI'
import { Icon } from './Icons'
import { fetchAttachmentBlob,downloadAttachment,formatBytes,uploadMomFiles } from './MomAttachments'

// RFP documents accept a broad set of common business file types (not just .docx, unlike MoM
// attachments elsewhere in the app) — the server enforces the same allow-list. Every login with
// view access can open the in-page preview; only the authorised custodian (canDownload) also gets
// the Download action. `category` scopes the list to one RFP sub-tab, or 'all' to show every
// document regardless of category (the aggregate Documents tab).
const BASE='/api/rfps'
const MAX_FILES=10
const MAX_BYTES=10*1024*1024
const LABELS={general:'RFP documents',description:'Description documents',technical_response:'Technical response documents'}
const ACCEPT='.docx,.doc,.pdf,.xlsx,.xls,.pptx,.ppt,.csv,.txt,.rtf,.zip,.png,.jpg,.jpeg,.gif,.msg'
const ALLOWED_EXT=ACCEPT.split(',')
const CATEGORY_LABEL={general:'General',description:'Description',technical_response:'Technical response'}

function extOf(name){const m=/\.[^.]+$/.exec(name||'');return m?m[0].toLowerCase():''}

function checkRfpFiles(files,existingCount=0){
 const ok=[],errors=[]
 for(const f of files){
  const ext=extOf(f.name)
  if(!ALLOWED_EXT.includes(ext)) errors.push(`${f.name}: file type not supported`)
  else if(f.size===0) errors.push(`${f.name}: the file is empty`)
  else if(f.size>MAX_BYTES) errors.push(`${f.name}: larger than 10 MB`)
  else ok.push(f)
 }
 const room=Math.max(0,MAX_FILES-existingCount)
 if(ok.length>room){errors.push(`An RFP can have at most ${MAX_FILES} documents in total`);ok.splice(room)}
 return {ok,errors}
}

function FilePicker({files,onChange,onError}){
 const inputRef=useRef(null)
 const add=list=>{const {ok,errors}=checkRfpFiles([...files,...list]);if(errors.length)onError?.(errors.join('\n'));onChange(ok)}
 return <div className="docx-picker">
  <input ref={inputRef} type="file" accept={ACCEPT} multiple hidden onChange={e=>{add([...e.target.files]);e.target.value=''}}/>
  <button type="button" className="docx-drop" onClick={()=>inputRef.current?.click()} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();add([...e.dataTransfer.files])}}>
   <Icon name="note" size={18}/><span><strong>Attach a document</strong><small>Word, Excel, PowerPoint, PDF, image, text, zip · up to 10 MB each · click or drop files here</small></span>
  </button>
  {files.length>0&&<ul className="docx-files">{files.map((f,i)=><li key={f.name+i}><Icon name="note" size={14}/><span>{f.name}</span><small>{formatBytes(f.size)}</small><button type="button" className="icon-btn" aria-label={`Remove ${f.name}`} onClick={()=>onChange(files.filter((_,j)=>j!==i))}><Icon name="close" size={14}/></button></li>)}</ul>}
 </div>
}

// Renders whatever preview the file type supports; unsupported types fall back to a message
// (Download, where allowed, is still the way to actually open them).
function RfpFileViewer({rfp,attachment,onClose,onToast,canDownload}){
 const bodyRef=useRef(null); const styleRef=useRef(null)
 const [state,setState]=useState('loading'); const [error,setError]=useState(''); const [kind,setKind]=useState(null)
 const [blobUrl,setBlobUrl]=useState(null); const [text,setText]=useState('')
 useEffect(()=>{
  if(!attachment)return
  let cancelled=false; setState('loading'); setError(''); setBlobUrl(null); setText('')
  const ext=extOf(attachment.filename)
  ;(async()=>{
   try{
    const blob=await fetchAttachmentBlob(rfp.id,attachment.id,BASE)
    if(cancelled)return
    if(ext==='.docx'){
     setKind('docx')
     const {renderAsync}=await import('docx-preview')
     if(cancelled||!bodyRef.current)return
     bodyRef.current.innerHTML=''; styleRef.current.innerHTML=''
     await renderAsync(blob,bodyRef.current,styleRef.current,{className:'docx',inWrapper:true,ignoreWidth:false,breakPages:true,ignoreFonts:true,useBase64URL:true,renderAltChunks:false,renderComments:false,renderChanges:false,experimental:false})
     bodyRef.current.querySelectorAll('a').forEach(a=>{
      const href=a.getAttribute('href')||''
      if(/^(https?:|mailto:)/i.test(href)){a.target='_blank';a.rel='noopener noreferrer'}
      else if(!href.startsWith('#'))a.removeAttribute('href')
     })
     bodyRef.current.querySelectorAll('iframe,object,embed,script').forEach(n=>n.remove())
    }else if(ext==='.pdf'){
     setKind('pdf'); setBlobUrl(URL.createObjectURL(blob))
    }else if(['.png','.jpg','.jpeg','.gif'].includes(ext)){
     setKind('image'); setBlobUrl(URL.createObjectURL(blob))
    }else if(['.txt','.csv'].includes(ext)){
     setKind('text'); setText(await blob.text())
    }else{
     setKind('unsupported')
    }
    if(!cancelled)setState('ready')
   }catch(e){if(!cancelled){setState('error');setError(e.message||'This document could not be displayed')}}
  })()
  return()=>{cancelled=true}
 },[rfp?.id,attachment?.id])
 useEffect(()=>()=>{if(blobUrl)URL.revokeObjectURL(blobUrl)},[blobUrl])
 const download=async()=>{try{await downloadAttachment(rfp.id,attachment,BASE)}catch(e){onToast?.({type:'error',message:e.message})}}
 return <Modal open={!!attachment} onClose={onClose} title={attachment?.filename} eyebrow="RFP document" size="xl">
  <div className="docx-viewer-bar"><span>{attachment&&formatBytes(attachment.size_bytes)}{attachment?.uploaded_by_name?` · uploaded by ${attachment.uploaded_by_name}`:''}</span>{canDownload&&<Button type="button" variant="soft" icon="download" onClick={download}>Download</Button>}</div>
  {state==='loading'&&<Spinner label="Opening document"/>}
  {state==='error'&&<div className="error-banner"><div><strong>Preview unavailable</strong><span>{error}{canDownload?'. You can still download the file.':'.'}</span></div></div>}
  {state==='ready'&&kind==='unsupported'&&<p className="mom-attachments-empty">Preview isn't available for this file type.{canDownload?' Use Download to open it.':''}</p>}
  {state==='ready'&&kind==='pdf'&&<iframe title={attachment.filename} src={blobUrl} className="docx-viewer" style={{width:'100%',height:'70vh',border:0}}/>}
  {state==='ready'&&kind==='image'&&<img src={blobUrl} alt={attachment.filename} style={{maxWidth:'100%'}}/>}
  {state==='ready'&&kind==='text'&&<pre className="docx-viewer" style={{whiteSpace:'pre-wrap'}}>{text}</pre>}
  <div ref={styleRef}/>
  <div ref={bodyRef} className="docx-viewer" hidden={!(state==='ready'&&kind==='docx')}/>
 </Modal>
}

export default function RfpDocuments({rfp,category='general',canEdit,canDownload,onChanged,onToast}){
 const all=rfp?.documents||[]
 const documents=category==='all'?all:all.filter(d=>(d.category||'general')===category)
 const uploadCategory=category==='all'?'general':category
 const [viewing,setViewing]=useState(null); const [adding,setAdding]=useState(false); const [files,setFiles]=useState([]); const [busy,setBusy]=useState(false)
 const fail=message=>onToast?.({type:'error',message})
 // The server caps documents per RFP across all sub-tabs combined, not per sub-tab — match that here
 // so the "room left" check and the disabled-upload-button state don't drift from what the API allows.
 const upload=async()=>{
  const {ok,errors}=checkRfpFiles(files,all.length); if(errors.length)fail(errors.join('\n')); if(!ok.length)return
  setBusy(true)
  const {uploaded,failed}=await uploadMomFiles(rfp.id,ok,BASE,{category:uploadCategory})
  setBusy(false)
  if(uploaded.length)onToast?.({message:`${uploaded.length} document${uploaded.length>1?'s':''} uploaded`})
  if(failed.length)fail(failed.join('\n'))
  setFiles([]); setAdding(false); onChanged?.()
 }
 const remove=async doc=>{if(!confirm(`Remove "${doc.filename}" from this RFP?`))return;try{await api.delete(`${BASE}/${rfp.id}/attachments/${doc.id}`);onToast?.({message:'Document removed'});onChanged?.()}catch(e){fail(e.message)}}
 return <div className="mom-attachments">
  <div className="mom-attachments-head"><b>{category==='all'?'All documents':(LABELS[category]||'Documents')}</b>{canEdit&&!adding&&all.length<MAX_FILES&&<Button type="button" variant="text" icon="plus" onClick={()=>setAdding(true)}>Upload document</Button>}</div>
  {documents.length>0?<ul className="docx-files">{documents.map(doc=><li key={doc.id}>
   <Icon name="note" size={14}/>
   <button type="button" className="docx-name" onClick={()=>setViewing(doc)} title="View document">{doc.filename}</button>
   <small>{formatBytes(doc.size_bytes)}{doc.uploaded_by_name?` · ${doc.uploaded_by_name}`:''}{category==='all'?` · ${CATEGORY_LABEL[doc.category||'general']||doc.category}`:''}</small>
   <div className="row-actions">
    <button type="button" className="icon-btn" title="View" aria-label={`View ${doc.filename}`} onClick={()=>setViewing(doc)}><Icon name="eye" size={15}/></button>
    {canDownload
     ? <button type="button" className="icon-btn" title="Download" aria-label={`Download ${doc.filename}`} onClick={async()=>{try{await downloadAttachment(rfp.id,doc,BASE)}catch(e){fail(e.message)}}}><Icon name="download" size={15}/></button>
     : <span className="pill pill-neutral" title="Download is restricted to the authorised custodian">View only</span>}
    {canEdit&&doc.can_delete&&<button type="button" className="icon-btn text-danger" title="Remove" aria-label={`Remove ${doc.filename}`} onClick={()=>remove(doc)}><Icon name="trash" size={15}/></button>}
   </div>
  </li>)}</ul>:!adding&&<p className="mom-attachments-empty">No documents uploaded.</p>}
  {adding&&<div className="mom-attach-form"><FilePicker files={files} onChange={setFiles} onError={fail}/><div className="modal-actions"><Button type="button" variant="ghost" onClick={()=>{setAdding(false);setFiles([])}}>Cancel</Button><Button type="button" onClick={upload} disabled={!files.length||busy}>{busy?'Uploading…':'Upload'}</Button></div></div>}
  <RfpFileViewer rfp={rfp} attachment={viewing} onClose={()=>setViewing(null)} onToast={onToast} canDownload={canDownload}/>
 </div>
}

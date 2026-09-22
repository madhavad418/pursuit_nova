import React,{useEffect,useRef,useState} from 'react'
import { api } from '../lib/api'
import { Button,Modal,Spinner } from './UI'
import { Icon } from './Icons'

const MAX_BYTES=10*1024*1024
const MAX_FILES=10
const DOCX_ACCEPT='.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document'

export const formatBytes=n=>n<1024?`${n} B`:n<1024*1024?`${(n/1024).toFixed(0)} KB`:`${(n/1024/1024).toFixed(1)} MB`
const fileUrl=(momId,attId,base='/api/moms')=>`${api.base}${base}/${momId}/attachments/${attId}`

// Quick checks before upload; the server repeats all of them and also inspects the file contents.
export function checkDocxFiles(files,existingCount=0){
 const ok=[],errors=[]
 for(const f of files){
  if(!/\.docx$/i.test(f.name)) errors.push(`${f.name}: only Word .docx files can be attached`)
  else if(f.size===0) errors.push(`${f.name}: the file is empty`)
  else if(f.size>MAX_BYTES) errors.push(`${f.name}: larger than 10 MB`)
  else ok.push(f)
 }
 const room=Math.max(0,MAX_FILES-existingCount)
 if(ok.length>room){errors.push(`A MoM can have at most ${MAX_FILES} files`);ok.splice(room)}
 return {ok,errors}
}

// Uploads one by one so a single bad file does not block the rest. `extra` adds fixed form
// fields to every upload (e.g. {category:'description'} for RFP sub-tab documents).
export async function uploadMomFiles(momId,files,base='/api/moms',extra={}){
 const uploaded=[],failed=[]
 for(const f of files){
  const form=new FormData();form.append('file',f);Object.entries(extra).forEach(([k,v])=>form.append(k,v))
  try{uploaded.push(await api.raw(`${base}/${momId}/attachments`,{method:'POST',body:form}))}
  catch(e){failed.push(`${f.name}: ${e.message}`)}
 }
 return {uploaded,failed}
}

export function DocxPicker({files,onChange,onError}){
 const inputRef=useRef(null)
 const add=list=>{const {ok,errors}=checkDocxFiles([...files,...list]);if(errors.length)onError?.(errors.join('\n'));onChange(ok)}
 return <div className="docx-picker">
  <input ref={inputRef} type="file" accept={DOCX_ACCEPT} multiple hidden onChange={e=>{add([...e.target.files]);e.target.value=''}}/>
  <button type="button" className="docx-drop" onClick={()=>inputRef.current?.click()} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();add([...e.dataTransfer.files])}}>
   <Icon name="note" size={18}/><span><strong>Attach Word document</strong><small>.docx only · up to 10 MB each · click or drop files here</small></span>
  </button>
  {files.length>0&&<ul className="docx-files">{files.map((f,i)=><li key={f.name+i}><Icon name="note" size={14}/><span>{f.name}</span><small>{formatBytes(f.size)}</small><button type="button" className="icon-btn" aria-label={`Remove ${f.name}`} onClick={()=>onChange(files.filter((_,j)=>j!==i))}><Icon name="close" size={14}/></button></li>)}</ul>}
 </div>
}

// Generic file fetch (despite the name, not docx-specific) — used for both the docx viewer and,
// via fetchAttachmentBlob, any other file-type preview.
async function fetchDocx(momId,attId,base='/api/moms'){
 const r=await fetch(fileUrl(momId,attId,base),{credentials:'include'})
 if(!r.ok){let msg=`Could not open the file (${r.status})`;try{msg=(await r.json()).detail||msg}catch{};throw new Error(msg)}
 return r.blob()
}
export const fetchAttachmentBlob=fetchDocx

export async function downloadAttachment(momId,att,base='/api/moms'){
 const blob=await fetchDocx(momId,att.id,base)
 const url=URL.createObjectURL(blob)
 const a=document.createElement('a');a.href=url;a.download=att.filename;document.body.appendChild(a);a.click();a.remove()
 setTimeout(()=>URL.revokeObjectURL(url),10000)
}

// Renders the Word document in the page. Embedded HTML chunks are not rendered and links are limited to safe schemes.
export function DocxViewer({momId,attachment,onClose,onToast,base='/api/moms',canDownload=true}){
 const bodyRef=useRef(null); const styleRef=useRef(null)
 const [state,setState]=useState('loading'); const [error,setError]=useState('')
 useEffect(()=>{
  if(!attachment)return
  let cancelled=false; setState('loading'); setError('')
  ;(async()=>{
   try{
    const [blob,{renderAsync}]=await Promise.all([fetchDocx(momId,attachment.id,base),import('docx-preview')])
    if(cancelled||!bodyRef.current)return
    bodyRef.current.innerHTML=''; styleRef.current.innerHTML=''
    await renderAsync(blob,bodyRef.current,styleRef.current,{className:'docx',inWrapper:true,ignoreWidth:false,breakPages:true,ignoreFonts:true,useBase64URL:true,renderAltChunks:false,renderComments:false,renderChanges:false,experimental:false})
    bodyRef.current.querySelectorAll('a').forEach(a=>{
     const href=a.getAttribute('href')||''
     if(/^(https?:|mailto:)/i.test(href)){a.target='_blank';a.rel='noopener noreferrer'}
     else if(!href.startsWith('#'))a.removeAttribute('href')
    })
    bodyRef.current.querySelectorAll('iframe,object,embed,script').forEach(n=>n.remove())
    if(!cancelled)setState('ready')
   }catch(e){if(!cancelled){setState('error');setError(e.message||'This document could not be displayed')}}
  })()
  return()=>{cancelled=true}
 },[momId,attachment?.id])
 const download=async()=>{try{await downloadAttachment(momId,attachment,base)}catch(e){onToast?.({type:'error',message:e.message})}}
 return <Modal open={!!attachment} onClose={onClose} title={attachment?.filename} eyebrow="Minutes of Meeting document" size="xl">
  <div className="docx-viewer-bar"><span>{attachment&&formatBytes(attachment.size_bytes)}{attachment?.uploaded_by_name?` · uploaded by ${attachment.uploaded_by_name}`:''}</span>{canDownload&&<Button type="button" variant="soft" icon="download" onClick={download}>Download</Button>}</div>
  {state==='loading'&&<Spinner label="Opening document"/>}
  {state==='error'&&<div className="error-banner"><div><strong>Preview unavailable</strong><span>{error}. You can still download the file.</span></div></div>}
  <div ref={styleRef}/>
  <div ref={bodyRef} className="docx-viewer" hidden={state!=='ready'}/>
 </Modal>
}

export function MomAttachmentList({mom,canEdit,onChanged,onToast,base='/api/moms'}){
 const attachments=mom.attachments||[]
 const [viewing,setViewing]=useState(null); const [adding,setAdding]=useState(false); const [files,setFiles]=useState([]); const [busy,setBusy]=useState(false)
 const fail=message=>onToast?.({type:'error',message})
 const upload=async()=>{
  const {ok,errors}=checkDocxFiles(files,attachments.length); if(errors.length)fail(errors.join('\n')); if(!ok.length)return
  setBusy(true)
  const {uploaded,failed}=await uploadMomFiles(mom.id,ok,base)
  setBusy(false)
  if(uploaded.length)onToast?.({message:`${uploaded.length} file${uploaded.length>1?'s':''} attached`})
  if(failed.length)fail(failed.join('\n'))
  setFiles([]); setAdding(false); onChanged?.()
 }
 const remove=async att=>{if(!confirm(`Remove "${att.filename}" from this MoM?`))return;try{await api.delete(`${base}/${mom.id}/attachments/${att.id}`);onToast?.({message:'File removed'});onChanged?.()}catch(e){fail(e.message)}}
 const download=async att=>{try{await downloadAttachment(mom.id,att,base)}catch(e){fail(e.message)}}
 return <div className="mom-attachments">
  <div className="mom-attachments-head"><b>Documents</b>{canEdit&&!adding&&attachments.length<MAX_FILES&&<Button variant="text" icon="plus" onClick={()=>setAdding(true)}>Attach .docx</Button>}</div>
  {attachments.length>0?<ul className="docx-files">{attachments.map(att=><li key={att.id}>
   <Icon name="note" size={14}/>
   <button type="button" className="docx-name" onClick={()=>setViewing(att)} title="View document">{att.filename}</button>
   <small>{formatBytes(att.size_bytes)}{att.uploaded_by_name?` · ${att.uploaded_by_name}`:''}</small>
   <div className="row-actions">
    <button type="button" className="icon-btn" title="View" aria-label={`View ${att.filename}`} onClick={()=>setViewing(att)}><Icon name="eye" size={15}/></button>
    <button type="button" className="icon-btn" title="Download" aria-label={`Download ${att.filename}`} onClick={()=>download(att)}><Icon name="download" size={15}/></button>
    {att.can_delete&&<button type="button" className="icon-btn text-danger" title="Remove" aria-label={`Remove ${att.filename}`} onClick={()=>remove(att)}><Icon name="trash" size={15}/></button>}
   </div>
  </li>)}</ul>:!adding&&<p className="mom-attachments-empty">No documents attached.</p>}
  {adding&&<div className="mom-attach-form"><DocxPicker files={files} onChange={setFiles} onError={fail}/><div className="modal-actions"><Button variant="ghost" onClick={()=>{setAdding(false);setFiles([])}}>Cancel</Button><Button onClick={upload} disabled={!files.length||busy}>{busy?'Uploading…':'Upload'}</Button></div></div>}
  <DocxViewer momId={mom.id} attachment={viewing} onClose={()=>setViewing(null)} onToast={onToast} base={base}/>
 </div>
}

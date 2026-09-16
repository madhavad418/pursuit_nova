import React,{useEffect,useMemo,useRef,useState} from 'react'
import { api } from '../lib/api'
import { dateText } from '../lib/format'
import { Button,Empty,ErrorBanner,Field,Input,Modal,Pagination,Pill,SectionHeader,Select,Table,Textarea,temperatureTone } from '../components/UI'
import { Icon } from '../components/Icons'
import { navigate } from '../lib/router'
import { useAuth } from '../components/Auth'
import { ProspectEditor } from '../components/ProspectEditor'

const isAdminRole = (role) => role === 'Super Admin' || role === 'Admin'

const REGIONS=['North America','Europe','APAC','Middle East','Africa','Latin America','Global']
const emptyForm={mode:'new',company_id:'',company_name:'',vertical:'',website:'',linkedin_url:'',region:'',country:'',state:'',city:'',owner_id:'',temperature:'Warm',source:'LinkedIn',source_detail:'',next_follow_up:'',remarks:'',contact_name:'',designation:'',email:'',phone:'',contact_linkedin:''}
const FILTER_KEYS=['q','status','temperature','owner_id','region','followup','sort','dir']

// Column header menu: sort options when `sortKey` is set, a value filter when `options` ([{value,label}]) is set.
function ColumnMenu({label,sortKey,sort,dir,onSort,filterValue='',options,onFilter,sortLabels=['Sort A → Z','Sort Z → A']}){
 const [open,setOpen]=useState(null); const ref=useRef(null)
 // Menu is fixed-positioned so the table panel's overflow:hidden can't clip it; any scroll closes it
 useEffect(()=>{if(!open)return;const close=e=>{if(!ref.current?.contains(e.target))setOpen(null)};const esc=e=>{if(e.key==='Escape')setOpen(null)};const off=()=>setOpen(null);document.addEventListener('mousedown',close);document.addEventListener('keydown',esc);window.addEventListener('scroll',off,true);window.addEventListener('resize',off);return()=>{document.removeEventListener('mousedown',close);document.removeEventListener('keydown',esc);window.removeEventListener('scroll',off,true);window.removeEventListener('resize',off)}},[open])
 const toggle=e=>{e.stopPropagation();if(open)return setOpen(null);const b=e.currentTarget.getBoundingClientRect();setOpen({top:b.bottom+6,left:Math.min(b.left,window.innerWidth-240)})}
 const sorted=sort===sortKey; const filtered=!!filterValue
 const choose=fn=>{fn();setOpen(null)}
 return <div className="col-menu" ref={ref}>
  <button type="button" className={`col-menu-trigger${sorted||filtered?' active':''}`} onClick={toggle} aria-haspopup="menu" aria-expanded={!!open}>
   <span>{label}</span>
   {sorted&&<span className="col-menu-sort" aria-label={dir==='desc'?'sorted descending':'sorted ascending'}>{dir==='desc'?'↓':'↑'}</span>}
   {filtered&&<span className="col-menu-dot" aria-label="filtered"/>}
   <Icon name="filter" size={12}/>
  </button>
  {open&&<div className="col-menu-pop" role="menu" style={{top:open.top,left:open.left}} onClick={e=>e.stopPropagation()}>
   {sortKey&&<>
    <button type="button" role="menuitem" className={sorted&&dir==='asc'?'selected':''} onClick={()=>choose(()=>onSort(sortKey,'asc'))}>{sortLabels[0]}</button>
    <button type="button" role="menuitem" className={sorted&&dir==='desc'?'selected':''} onClick={()=>choose(()=>onSort(sortKey,'desc'))}>{sortLabels[1]}</button>
    {sorted&&<button type="button" role="menuitem" className="muted" onClick={()=>choose(()=>onSort('',''))}>Clear sort</button>}
   </>}
   {options&&<>
    {sortKey&&<div className="col-menu-sep">Filter</div>}
    <div className="col-menu-options">
     <button type="button" role="menuitemradio" aria-checked={!filterValue} className={!filterValue?'selected':''} onClick={()=>choose(()=>onFilter(''))}>All</button>
     {options.map(o=><button type="button" role="menuitemradio" aria-checked={String(filterValue)===String(o.value)} key={o.value} className={String(filterValue)===String(o.value)?'selected':''} onClick={()=>choose(()=>onFilter(o.value))}>{o.label}</button>)}
    </div>
   </>}
  </div>}
 </div>
}
export default function ProspectsPage({route,onToast}){
 const {user,has}=useAuth(); const [filters,setFilters]=useState({q:'',status:'',temperature:'',owner_id:'',region:'',followup:'',sort:'',dir:'',page:1}); const [data,setData]=useState(null); const [error,setError]=useState(null); const [open,setOpen]=useState(route?.query?.get('new')==='1'&&has('LEAD_CREATE')); const [form,setForm]=useState({...emptyForm,owner_id:String(user.id)}); const [users,setUsers]=useState([]); const [companyHits,setCompanyHits]=useState([]); const [views,setViews]=useState([]); const [viewOpen,setViewOpen]=useState(false); const [viewName,setViewName]=useState(''); const [saving,setSaving]=useState(false)
 const [importOpen,setImportOpen]=useState(false); const [importFile,setImportFile]=useState(null); const [importing,setImporting]=useState(false); const [importResult,setImportResult]=useState(null)
 const qs=useMemo(()=>{const p=new URLSearchParams({page:String(filters.page),page_size:'20'});FILTER_KEYS.forEach(k=>filters[k]&&p.set(k,filters[k]));return p.toString()},[filters])
 const load=async()=>{setError(null);try{const [d,v]=await Promise.all([api.get('/api/query/leads?'+qs),api.get('/api/saved-views?module=prospects')]);setData(d);setViews(v)}catch(e){setError(e)}}
 useEffect(()=>{load()},[qs]); useEffect(()=>{api.get('/api/users/assignable').then(setUsers).catch(()=>{})},[])
 useEffect(()=>{if(form.mode==='existing'&&form.company_name.trim().length>=2){const t=setTimeout(()=>api.get('/api/query/companies?q='+encodeURIComponent(form.company_name)+'&page_size=8').then(r=>setCompanyHits(r.items||[])),250);return()=>clearTimeout(t)}setCompanyHits([])},[form.mode,form.company_name])
 const set=(k,v)=>setForm(f=>({...f,[k]:v}))
 const create=async e=>{e.preventDefault();setSaving(true);try{const payload={lead:{owner_id:Number(form.owner_id||user.id),temperature:form.temperature,source:form.source,source_detail:form.source_detail,region:form.region,country:form.country,state:form.state,city:form.city,next_follow_up:form.next_follow_up||null,remarks:form.remarks},contacts:form.contact_name?[{name:form.contact_name,designation:form.designation,email:form.email,phone:form.phone,linkedin_url:form.contact_linkedin,is_primary:true}]:[]}; if(form.mode==='existing')payload.company_id=Number(form.company_id); else payload.company={name:form.company_name,vertical:form.vertical,website:form.website,linkedin_url:form.linkedin_url,region:form.region,country:form.country,state:form.state,city:form.city}; const r=await api.post('/api/leads/full',payload);onToast?.({message:`${r.lead.company_name} added to PursuitNova`});setOpen(false);setForm({...emptyForm,owner_id:String(user.id)});await load();navigate(`lead/${r.lead.id}`)}catch(e){onToast?.({type:'error',message:e.message})}finally{setSaving(false)}}
 const saveView=async()=>{if(!viewName.trim())return;await api.post('/api/saved-views',{module:'prospects',name:viewName.trim(),filters:Object.fromEntries(FILTER_KEYS.map(k=>[k,filters[k]]))});setViewOpen(false);setViewName('');load();onToast?.({message:'Saved view created'})}
 const applyView=v=>{let f={};try{f=JSON.parse(v.filters_json||'{}')}catch{};setFilters({...filters,...f,page:1})}
 const doImport=async()=>{
  if(!importFile)return;setImporting(true);setImportResult(null)
  try{
   const form=new FormData();form.append('file',importFile)
   const csrfToken=document.cookie.split(';').map(c=>c.trim()).find(c=>c.startsWith('csrf_'))?.split('=')[1]
   const res=await fetch('/api/leads/import',{method:'POST',body:form,headers:csrfToken?{'x-csrf-token':csrfToken}:{}})
   const data=await res.json()
   if(!res.ok) throw new Error(data.detail||'Import failed')
   setImportResult(data);if(data.imported>0)load()
   onToast?.({message:`${data.imported} prospect(s) imported`})
  }catch(err){setImportResult({imported:0,skipped:0,errors:[{row:0,message:err.message}],warnings:[]})}finally{setImporting(false)}
 }
 const downloadSample=()=>{window.open('/api/leads/import/sample','_blank')}
 const [editLeadId,setEditLeadId]=useState(null)
 const openEdit=(e,r)=>{e.stopPropagation();setEditLeadId(r.id)}
 const deleteLead=async(e,r)=>{e.stopPropagation();if(!confirm(`Delete prospect "${r.company_name}"? This will also remove all related meetings, actions and opportunities.`))return;try{await api.delete(`/api/leads/${r.id}`);onToast?.({message:`${r.company_name} deleted`});load()}catch(err){onToast?.({type:'error',message:err.message})}}
 const admin=isAdminRole(user.role)
 const onSort=(sort,dir)=>setFilters(f=>({...f,sort,dir,page:1}))
 const filterBy=k=>v=>setFilters(f=>({...f,[k]:v,page:1}))
 const menu=(label,sortKey,extra={})=>()=> <ColumnMenu label={label} sortKey={sortKey} sort={filters.sort} dir={filters.dir} onSort={onSort} {...extra}/>
 const facets=data?.facets||{}
 const columns=[
  {key:'company_name',label:'Prospect',header:menu('Prospect','company_name'),render:r=><div className="primary-cell"><strong>{r.company_name}</strong><span>{r.primary_contact||'No primary contact'} · {r.vertical}</span></div>},
  // Other columns: filter only, options are the values present in the data
  {key:'temperature',label:'Signal',header:menu('Signal',null,{filterValue:filters.temperature,onFilter:filterBy('temperature'),options:(facets.temperatures||[]).map(x=>({value:x,label:x}))}),render:r=><Pill tone={temperatureTone(r.temperature)}>{r.temperature}</Pill>},
  {key:'status',label:'Status',header:menu('Status',null,{filterValue:filters.status,onFilter:filterBy('status'),options:(facets.statuses||[]).map(x=>({value:x,label:x}))}),render:r=><Pill tone="neutral">{r.status}</Pill>},
  {key:'owner_name',label:'Owner',header:menu('Owner',null,{filterValue:filters.owner_id,onFilter:filterBy('owner_id'),options:(facets.owners||[]).map(o=>({value:o.id,label:o.name}))})},
  {key:'next_follow_up',label:'Next follow-up',header:menu('Next follow-up',null,{filterValue:filters.followup,onFilter:filterBy('followup'),options:[...(facets.follow_ups||[]).map(x=>({value:x,label:dateText(x)})),...(facets.has_empty_follow_up?[{value:'none',label:'No date'}]:[])]}),render:r=><span className={r.next_follow_up&&r.next_follow_up<new Date().toISOString().slice(0,10)?'text-danger':''}>{dateText(r.next_follow_up)}</span>},
  {key:'region',label:'Region',header:menu('Region',null,{filterValue:filters.region,onFilter:filterBy('region'),options:[...(facets.regions||[]).map(x=>({value:x,label:x})),...(facets.has_empty_region?[{value:'__none__',label:'No region'}]:[])]})},...([{key:'_actions',label:'Actions',render:r=><div className="row-actions" onClick={e=>e.stopPropagation()}><button className="icon-btn" title="Edit" aria-label={`Edit ${r.company_name}`} onClick={e=>openEdit(e,r)}><Icon name="edit" size={16}/></button>{admin&&<button className="icon-btn text-danger" title="Delete" aria-label={`Delete ${r.company_name}`} onClick={e=>deleteLead(e,r)}><Icon name="trash" size={16}/></button>}</div>}])]
 return <><SectionHeader eyebrow="Seller workspace" title="Prospects" text="Own the relationship, next action and commercial signal from first touch." actions={<><div className="saved-view-menu"><Select value="" onChange={e=>{const v=views.find(x=>String(x.id)===e.target.value);if(v)applyView(v)}}><option value="">Saved views ({views.length})</option>{views.map(v=><option key={v.id} value={v.id}>{v.name}</option>)}</Select></div><Button variant="soft" icon="filter" onClick={()=>setViewOpen(true)}>Save view</Button>{has('LEAD_CREATE')&&<><Button variant="soft" onClick={()=>{setImportOpen(true);setImportFile(null);setImportResult(null)}}>Import CSV</Button><Button icon="plus" onClick={()=>setOpen(true)}>New prospect</Button></>}</>}/><div className="mini-kpis"><div><span>Visible prospects</span><strong>{data?.total??'—'}</strong></div><div><span>Hot</span><strong className="text-danger">{data?.summary?.hot??'—'}</strong></div><div><span>Warm</span><strong className="text-warning">{data?.summary?.warm??'—'}</strong></div><div><span>Follow-ups overdue</span><strong>{data?.summary?.overdue_followups??'—'}</strong></div></div><div className="toolbar-card"><div className="search-input"><Icon name="search"/><Input placeholder="Search prospect, owner or remarks" value={filters.q} onChange={e=>setFilters(f=>({...f,q:e.target.value,page:1}))}/></div><Select value={filters.temperature} onChange={e=>setFilters(f=>({...f,temperature:e.target.value,page:1}))}><option value="">All signals</option><option>Hot</option><option>Warm</option><option>Cold</option></Select><Select value={filters.status} onChange={e=>setFilters(f=>({...f,status:e.target.value,page:1}))}><option value="">All statuses</option>{['New','Assigned','Contacted','Engaged','Qualified','Converted','On Hold','Unresponsive','Disqualified','Lost'].map(x=><option key={x}>{x}</option>)}</Select><button className="icon-btn" onClick={load}><Icon name="refresh"/></button></div><ErrorBanner error={error} onRetry={load}/>{data&&<section className="panel table-panel">{data.items?.length?<><Table columns={columns} rows={data.items} onRowClick={r=>navigate(`lead/${r.id}`)}/><Pagination page={data.page} pages={data.pages} onPage={page=>setFilters(f=>({...f,page}))}/></>:<Empty title="No prospects in this view" text="Change the filters or create the first prospect."/>}</section>}<Modal open={viewOpen} onClose={()=>setViewOpen(false)} title="Save current view" eyebrow="Personal productivity"><Field label="View name" required><Input autoFocus value={viewName} onChange={e=>setViewName(e.target.value)} placeholder="e.g. My hot prospects"/></Field><div className="filter-summary"><span>Temperature: <b>{filters.temperature||'Any'}</b></span><span>Status: <b>{filters.status||'Any'}</b></span><span>Search: <b>{filters.q||'None'}</b></span></div><div className="modal-actions"><Button variant="ghost" onClick={()=>setViewOpen(false)}>Cancel</Button><Button onClick={saveView}>Save view</Button></div></Modal><Modal open={open} onClose={()=>setOpen(false)} title="Create prospect" eyebrow="New pursuit" size="xl"><form onSubmit={create}><div className="segmented"><button type="button" className={form.mode==='new'?'active':''} onClick={()=>set('mode','new')}>New company</button><button type="button" className={form.mode==='existing'?'active':''} onClick={()=>set('mode','existing')}>Existing company</button></div><div className="form-section"><h3>Company</h3><div className="form-grid">{form.mode==='new'?<><Field label="Company name" required><Input required value={form.company_name} onChange={e=>set('company_name',e.target.value)}/></Field><Field label="Vertical" required><Input required value={form.vertical} onChange={e=>set('vertical',e.target.value)} placeholder="e.g. Telecommunications"/></Field><Field label="Website"><Input value={form.website} onChange={e=>set('website',e.target.value)} placeholder="https://"/></Field><Field label="LinkedIn company"><Input value={form.linkedin_url} onChange={e=>set('linkedin_url',e.target.value)} placeholder="https://linkedin.com/company/..."/></Field></>:<div className="company-lookup span-2"><Field label="Find existing company" required><Input value={form.company_name} onChange={e=>{set('company_name',e.target.value);set('company_id','')}} placeholder="Type company name…"/></Field>{companyHits.length>0&&<div className="lookup-results">{companyHits.map(c=><button type="button" key={c.id} className={String(form.company_id)===String(c.id)?'selected':''} onClick={()=>{set('company_id',String(c.id));set('company_name',c.name);setCompanyHits([])}}><strong>{c.name}</strong><span>{c.vertical} · {c.region||'No region'}</span></button>)}</div>}</div>}<Field label="Region"><Select value={form.region} onChange={e=>set('region',e.target.value)}><option value="">Select region</option>{REGIONS.map(x=><option key={x}>{x}</option>)}</Select></Field><Field label="Country"><Input value={form.country} onChange={e=>set('country',e.target.value)}/></Field><Field label="State"><Input value={form.state} onChange={e=>set('state',e.target.value)}/></Field><Field label="City"><Input value={form.city} onChange={e=>set('city',e.target.value)}/></Field></div></div><div className="form-section"><h3>Primary contact</h3><div className="form-grid"><Field label="Name"><Input value={form.contact_name} onChange={e=>set('contact_name',e.target.value)}/></Field><Field label="Designation"><Input value={form.designation} onChange={e=>set('designation',e.target.value)}/></Field><Field label="Email"><Input type="email" value={form.email} onChange={e=>set('email',e.target.value)}/></Field><Field label="Phone"><Input value={form.phone} onChange={e=>set('phone',e.target.value)}/></Field><Field label="LinkedIn"><Input value={form.contact_linkedin} onChange={e=>set('contact_linkedin',e.target.value)}/></Field></div></div><div className="form-section"><h3>Prospect ownership</h3><div className="form-grid"><Field label="Owner"><Select value={form.owner_id} onChange={e=>set('owner_id',e.target.value)}>{users.map(x=><option key={x.id} value={x.id}>{x.name} · {x.role}</option>)}</Select></Field><Field label="Signal"><Select value={form.temperature} onChange={e=>set('temperature',e.target.value)}><option>Hot</option><option>Warm</option><option>Cold</option></Select></Field><Field label="Source"><Select value={form.source} onChange={e=>set('source',e.target.value)}>{['LinkedIn','Referral','Event','Conference','Website','Existing Customer','Partner','Management Reference','Outbound','RFP / Tender','Other'].map(x=><option key={x}>{x}</option>)}</Select></Field><Field label="Source detail"><Input value={form.source_detail} onChange={e=>set('source_detail',e.target.value)}/></Field><Field label="Next follow-up"><Input type="date" value={form.next_follow_up} onChange={e=>set('next_follow_up',e.target.value)}/></Field><Field label="Remarks" className="span-2"><Textarea value={form.remarks} onChange={e=>set('remarks',e.target.value)}/></Field></div></div><div className="modal-actions"><Button type="button" variant="ghost" onClick={()=>setOpen(false)}>Cancel</Button><Button type="submit" disabled={saving}>{saving?'Creating…':'Create prospect'}</Button></div></form></Modal>
<ProspectEditor leadId={editLeadId} open={!!editLeadId} onClose={()=>setEditLeadId(null)} onSaved={load} onToast={onToast}/>
<Modal open={importOpen} onClose={()=>setImportOpen(false)} title="Import prospects from CSV" eyebrow="Bulk import" size="lg">
 <div className="import-section">
  <p style={{fontSize:13,color:'var(--muted)',margin:'0 0 12px'}}>Upload a CSV file to bulk-import prospects. Existing companies will be linked, not duplicated.</p>
  <Button variant="soft" onClick={downloadSample}>Download sample CSV</Button>
 </div>
 <div className="import-section">
  <Field label="Select CSV file"><input type="file" accept=".csv" onChange={e=>setImportFile(e.target.files?.[0]||null)}/></Field>
 </div>
 {importResult&&<div className="import-results">
  <div className="import-summary">
   <span className="text-success"><strong>{importResult.imported}</strong> imported</span>
   <span className="text-warning"><strong>{importResult.skipped}</strong> skipped</span>
   <span className="text-danger"><strong>{importResult.errors?.length||0}</strong> errors</span>
  </div>
  {importResult.errors?.length>0&&<div className="import-log import-errors"><h4>Errors</h4>{importResult.errors.map((e,i)=><div key={i} className="import-log-item error"><span>Row {e.row}</span><span>{e.message}</span></div>)}</div>}
  {importResult.warnings?.length>0&&<div className="import-log import-warnings"><h4>Warnings</h4>{importResult.warnings.map((w,i)=><div key={i} className="import-log-item warning"><span>Row {w.row}</span><span>{w.message}</span></div>)}</div>}
 </div>}
 <div className="modal-actions">
  <Button variant="ghost" onClick={()=>setImportOpen(false)}>Close</Button>
  <Button onClick={doImport} disabled={!importFile||importing}>{importing?'Importing…':'Import'}</Button>
 </div>
</Modal></>
}

import React,{useEffect,useState} from 'react'
import { api } from '../lib/api'
import { useAuth } from '../components/Auth'
import { Button,Empty,ErrorBanner,Field,Input,Modal,Pill,SectionHeader,Select,Textarea } from '../components/UI'
import { Icon } from '../components/Icons'

const CATEGORIES=['Business Development Manager','Business Development Lead','Presales Lead']
const monthLabel=m=>{const [y,mo]=m.split('-');return new Date(Number(y),Number(mo)-1).toLocaleString('default',{month:'long',year:'numeric'})}
function MonthPicker({value,onChange}){return <input type="month" className="month-picker" value={value} onChange={e=>onChange(e.target.value)}/>}
const statusPill=s=>{const map={draft:['neutral','Draft'],submitted:['warning','Submitted'],approved:['success','Approved'],rejected:['danger','Rejected']};const [tone,label]=map[s]||['neutral',s];return <Pill tone={tone}>{label}</Pill>}

function SubmissionSummary({submission,responseOnly=false,title='Overall KPI work'}){
 const approved=!responseOnly&&submission?.status==='approved'
 return <section className="kpi-summary-card">
  <header className="kpi-summary-header"><div><span className="kpi-summary-eyebrow">Performance summary</span><h3>{title}</h3></div>{submission&&statusPill(submission.status)}</header>
  <div className={`kpi-summary-body${approved?' has-result':''}`}>
   <div className="kpi-summary-copy">
    <div className="kpi-summary-message"><h4>Submitted response</h4><p>{submission?.summary||'No overall work summary was saved for this submission.'}</p></div>
    {approved&&<div className="kpi-summary-feedback"><h4>Approver feedback</h4><p>{submission.feedback||'No feedback provided.'}</p></div>}
   </div>
   {approved&&<aside className="kpi-summary-result"><span className="kpi-summary-eyebrow">Overall achievement</span><div className="kpi-summary-score">{submission.overall_percentage==null?'N/A':<>{submission.overall_percentage}<span>%</span></>}</div><div className="kpi-summary-result-rule"/><p>{submission.overall_percentage==null?'No positive targets were set for this period.':'Average across KPIs with a positive target. Missing achievements count as zero.'}</p></aside>}
  </div>
 </section>
}

function OverallReview({group,month,onSaved,onToast}){
 const [feedback,setFeedback]=useState(''); const [saving,setSaving]=useState(false)
 const submission=group.submission
 const approve=async()=>{
  setSaving(true)
  try{
   const path=submission?`/api/kpi/submissions/${submission.id}/review`:'/api/kpi/review-overall'
   await api.put(path,{feedback,user_id:group.user_id,category:group.category,month})
   onToast?.({message:'Overall KPI approval and feedback saved'});setFeedback('');onSaved()
  }catch(err){onToast?.({type:'error',message:err.message})}finally{setSaving(false)}
 }
 return <><SubmissionSummary submission={submission}/>{submission?.status!=='approved'&&<div style={{padding:20}}><Field label="Overall approver feedback" required><Textarea rows={4} value={feedback} onChange={e=>setFeedback(e.target.value)} placeholder="Give feedback on this person's overall KPI work and results."/></Field><Button disabled={saving||!feedback.trim()} onClick={approve}>{saving?'Saving approval...':'Submit overall approval'}</Button></div>}</>
}

/* ─── User view: fill in achieved targets ─── */
function MyKPIView({onToast}){
 const [month,setMonth]=useState(new Date().toISOString().slice(0,7))
 const [data,setData]=useState(null); const [error,setError]=useState(null); const [saving,setSaving]=useState(false)
 const [edits,setEdits]=useState({}); const [summary,setSummary]=useState('')
 const load=()=>{setError(null);api.get('/api/kpi/my?month='+month).then(d=>{setData(d);setEdits({});setSummary(d.submission?.summary||'')}).catch(setError)}
 useEffect(()=>{load()},[month])

 if(!data) return <ErrorBanner error={error} onRetry={load}/>
 if(!data.category) return <Empty title="No category assigned" text="Ask your admin to assign a KPI category to your profile in Admin Center."/>

 const setEdit=(tid,val)=>setEdits(e=>({...e,[tid]:val}))
 const hasEdits=Object.keys(edits).length>0

 const saveAll=async()=>{
  setSaving(true)
  try{
   for(const item of data.items){
    const val=edits[item.id]??item.actual_value
    if(item.actual_status==='approved'||val==null||val==='') continue
    await api.put('/api/kpi/actuals',{template_id:item.id,month,actual_value:Number(val),remarks:'',status:'draft'})
   }
   onToast?.({message:'Saved as draft'});load()
  }catch(err){onToast?.({type:'error',message:err.message})}finally{setSaving(false)}
 }

 const submitAll=async()=>{
  if(!confirm('Submit all KPIs for review? You won\'t be able to edit approved entries.')) return
  setSaving(true)
  try{
   for(const item of data.items){
    const val=edits[item.id]??item.actual_value
    if(item.actual_status==='approved'||val==null||val==='') continue
    await api.put('/api/kpi/actuals',{template_id:item.id,month,actual_value:Number(val),remarks:'',status:'draft'})
   }
   await api.post('/api/kpi/submit',{month,summary})
   onToast?.({message:'KPIs submitted for review'});load()
  }catch(err){onToast?.({type:'error',message:err.message})}finally{setSaving(false)}
 }

 // Group by KRA
 const groups=[];let lastKra=''
 for(const item of data.items){
  if(item.kra!==lastKra){groups.push({kra:item.kra,items:[]});lastKra=item.kra}
  groups[groups.length-1].items.push(item)
 }

 return <>
  <div className="kpi-toolbar">
   <MonthPicker value={month} onChange={setMonth}/>
   <Pill tone="info">{data.category}</Pill>
   <div style={{flex:1}}/>
   <Button variant="soft" onClick={saveAll} disabled={saving||!hasEdits}>{saving?'Saving…':'Save draft'}</Button>
  </div>
  <ErrorBanner error={error} onRetry={load}/>
  {groups.map(g=><section key={g.kra} className="panel kpi-group">
   <h3 className="kpi-kra-head">{g.kra}</h3>
   <table className="kpi-tbl"><thead><tr><th>KPI</th><th className="ctr">Target</th><th className="ctr">Achieved</th><th className="ctr">%</th><th className="ctr">Status</th></tr></thead><tbody>
    {g.items.map(item=>{
     const val=edits[item.id]??item.actual_value??''
     const locked=item.actual_status==='approved'||data.submission?.status==='approved'
     const pct=item.target_value>0&&val!==''?Math.round((Number(val)/item.target_value)*100):null
     return <tr key={item.id}>
      <td className="kpi-name">{item.kpi}{item.review_remarks&&<div className="kpi-review-note">Admin: {item.review_remarks}</div>}</td>
      <td className="ctr">{item.target_value||'—'}</td>
      <td className="ctr"><input type="number" min="0" value={val} disabled={locked} onChange={ev=>setEdit(item.id,ev.target.value)} className="kpi-input"/></td>
      <td className="ctr">{pct!=null?<span className={pct>=100?'text-success':pct>=70?'text-warning':'text-danger'}>{pct}%</span>:'—'}</td>
      <td className="ctr">{statusPill(item.actual_status)}</td>
     </tr>
    })}
   </tbody></table>
  </section>)}
  <section className="panel" style={{padding:20}}>
   <Field label="Overall KPI work and reasons for achieved targets" required><Textarea rows={5} value={summary} disabled={data.submission?.status==='approved'} onChange={e=>setSummary(e.target.value)} placeholder="Describe this month's work, achievements and reasons for meeting or missing targets."/></Field>
   <Button onClick={submitAll} disabled={saving||!summary.trim()||data.submission?.status==='approved'}>Submit overall KPI work</Button>
   <SubmissionSummary submission={data.submission}/>
  </section>
 </>
}

/* ─── Admin view: manage KPI templates + targets, add new KPIs ─── */
function AdminKPIView({onToast}){
 const [month,setMonth]=useState(new Date().toISOString().slice(0,7))
 const [category,setCategory]=useState(CATEGORIES[0])
 const [people,setPeople]=useState([]); const [person,setPerson]=useState(''); const [submissions,setSubmissions]=useState([])
 useEffect(()=>{api.get('/api/kpi/users-with-category').then(setPeople).catch(setError)},[])
 useEffect(()=>{setPerson('')},[category])
 const loadSubmissions=()=>api.get('/api/kpi/review?month='+month).then(setSubmissions).catch(setError)
 useEffect(()=>{setSubmissions([]);loadSubmissions()},[month])
 const [data,setData]=useState(null); const [error,setError]=useState(null)
 const [addOpen,setAddOpen]=useState(false); const [addForm,setAddForm]=useState({kra:'',kpi:'',target_value:''})
 const [addSaving,setAddSaving]=useState(false)
 const [editTarget,setEditTarget]=useState(null); const [editVal,setEditVal]=useState('')
 const [editItem,setEditItem]=useState(null); const [editForm,setEditForm]=useState({kra:'',kpi:'',target_value:''}); const [editSaving,setEditSaving]=useState(false)

 const load=()=>{setError(null);api.get(`/api/kpi/admin-sheet?category=${encodeURIComponent(category)}&month=${month}`).then(setData).catch(setError)}
 useEffect(()=>{load()},[category,month])

 const openAdd=()=>{setAddForm({kra:'',kpi:'',target_value:''});setAddOpen(true)}
 const saveAdd=async e=>{
  e.preventDefault();setAddSaving(true)
  try{
   await api.post('/api/kpi/templates',{category,kra:addForm.kra,kpi:addForm.kpi,month,target_value:addForm.target_value?Number(addForm.target_value):null})
   onToast?.({message:'KPI added'});setAddOpen(false);load()
  }catch(err){onToast?.({type:'error',message:err.message})}finally{setAddSaving(false)}
 }

 const deleteTemplate=async item=>{
  if(!confirm(`Delete KPI "${item.kpi}"? This removes all targets and actuals for it.`)) return
  try{await api.delete(`/api/kpi/templates/${item.id}`);onToast?.({message:'KPI deleted'});load()}catch(err){onToast?.({type:'error',message:err.message})}
 }

 const openEditTarget=item=>{setEditTarget(item);setEditVal(String(item.target_value||''))}
 const saveTarget=async()=>{
  try{
   await api.put('/api/kpi/targets',{template_id:editTarget.id,month,target_value:Number(editVal)})
   onToast?.({message:'Target updated'});setEditTarget(null);load()
  }catch(err){onToast?.({type:'error',message:err.message})}
 }

 const openEditItem=item=>{setEditForm({kra:item.kra,kpi:item.kpi,target_value:String(item.target_value||'')});setEditItem(item)}
 const saveEditItem=async e=>{
  e.preventDefault();setEditSaving(true)
  try{
   await api.put(`/api/kpi/templates/${editItem.id}`,{kra:editForm.kra,kpi:editForm.kpi})
   if(editForm.target_value!==''){
    await api.put('/api/kpi/targets',{template_id:editItem.id,month,target_value:Number(editForm.target_value)})
   }
   onToast?.({message:'KPI updated'});setEditItem(null);load()
  }catch(err){onToast?.({type:'error',message:err.message})}finally{setEditSaving(false)}
 }

 // Group by KRA
 const groups=[];let lastKra=''
 for(const item of (data?.items||[])){
  if(item.kra!==lastKra){groups.push({kra:item.kra,items:[]});lastKra=item.kra}
  groups[groups.length-1].items.push(item)
 }

 // Collect unique KRAs for the add form dropdown
 const existingKras=[...new Set((data?.items||[]).map(i=>i.kra))]

 return <>
  <div className="kpi-toolbar kpi-manage-toolbar">
   <Select className="input kpi-category-select" value={category} onChange={e=>setCategory(e.target.value)}>{CATEGORIES.map(c=><option key={c}>{c}</option>)}</Select>
   <MonthPicker value={month} onChange={setMonth}/>
   <Select className="input kpi-person-select" aria-label="Person" value={person} onChange={e=>setPerson(e.target.value)}><option value="">All people</option>{people.filter(u=>u.category===category).map(u=><option key={u.id} value={u.id}>{u.name}</option>)}</Select>
   <div className="kpi-add-action"><Button icon="plus" onClick={openAdd}>Add KPI</Button></div>
  </div>
  <ErrorBanner error={error} onRetry={load}/>
  {groups.length===0&&<Empty title="No KPIs defined" text={`No KPI templates found for ${category}. Click "Add KPI" to create one.`}/>}
  {groups.map(g=><section key={g.kra} className="panel kpi-group">
   <h3 className="kpi-kra-head">{g.kra}</h3>
   <table className="kpi-tbl"><thead><tr><th>KPI</th><th className="ctr">Target ({monthLabel(month).split(' ')[0]})</th><th className="ctr">User Achieved</th><th className="ctr"></th></tr></thead><tbody>
    {g.items.map(item=><tr key={item.id}>
     <td className="kpi-name">{item.kpi}</td>
     <td className="ctr">{item.target_value||<span className="text-muted">—</span>}</td>
     <td className="ctr">{item.actuals.length>0?<div className="kpi-actuals-list">{item.actuals.filter(a=>!person||String(a.user_id)===person).map(a=><span key={a.user_id} className="kpi-actual-chip"><strong>{a.actual_value}</strong><small>{a.user_name}</small>{statusPill(a.status)}</span>)}</div>:<span className="text-muted">—</span>}</td>
     <td className="ctr"><div className="row-actions center"><button className="icon-btn" title="Edit" aria-label="Edit KPI" onClick={()=>openEditItem(item)}><Icon name="edit" size={15}/></button><button className="icon-btn text-danger" title="Delete" aria-label="Delete KPI" onClick={()=>deleteTemplate(item)}><Icon name="trash" size={15}/></button></div></td>
    </tr>)}
   </tbody></table>
  </section>)}

  {submissions.filter(g=>g.category===category&&(!person||String(g.user_id)===person)).map(g=><section className="panel" key={`${g.user_id}-${g.category}`}><SubmissionSummary submission={g.submission} responseOnly title={`${g.user_name} overall KPI work response feedback`}/></section>)}
  {/* Add KPI modal */}
  <Modal open={addOpen} onClose={()=>setAddOpen(false)} title="Add KPI" eyebrow={category}>
   <form onSubmit={saveAdd}><div className="form-grid">
    <Field label="KRA (Key Result Area)" required>
     <Input list="kra-list" required value={addForm.kra} onChange={e=>setAddForm(f=>({...f,kra:e.target.value}))} placeholder="e.g. Sales Pipeline Management"/>
     <datalist id="kra-list">{existingKras.map(k=><option key={k} value={k}/>)}</datalist>
    </Field>
    <Field label="KPI (Key Performance Indicator)" required><Input required value={addForm.kpi} onChange={e=>setAddForm(f=>({...f,kpi:e.target.value}))} placeholder="e.g. Qualified sales opportunities created"/></Field>
    <Field label={`Target for ${monthLabel(month)}`}><Input type="number" min="0" value={addForm.target_value} onChange={e=>setAddForm(f=>({...f,target_value:e.target.value}))} placeholder="Optional"/></Field>
   </div>
   <div className="modal-actions"><Button type="button" variant="ghost" onClick={()=>setAddOpen(false)}>Cancel</Button><Button type="submit" disabled={addSaving}>{addSaving?'Adding…':'Add KPI'}</Button></div>
   </form>
  </Modal>

  {/* Edit KPI modal */}
  <Modal open={!!editItem} onClose={()=>setEditItem(null)} title="Edit KPI" eyebrow={category}>
   <form onSubmit={saveEditItem}><div className="form-grid">
    <Field label="KRA (Key Result Area)" required>
     <Input list="kra-edit-list" required value={editForm.kra} onChange={e=>setEditForm(f=>({...f,kra:e.target.value}))}/>
     <datalist id="kra-edit-list">{existingKras.map(k=><option key={k} value={k}/>)}</datalist>
    </Field>
    <Field label="KPI (Key Performance Indicator)" required><Input required value={editForm.kpi} onChange={e=>setEditForm(f=>({...f,kpi:e.target.value}))}/></Field>
    <Field label={`Target for ${monthLabel(month)}`}><Input type="number" min="0" value={editForm.target_value} onChange={e=>setEditForm(f=>({...f,target_value:e.target.value}))} placeholder="Enter target value"/></Field>
   </div>
   <div className="modal-actions"><Button type="button" variant="ghost" onClick={()=>setEditItem(null)}>Cancel</Button><Button type="submit" disabled={editSaving}>{editSaving?'Saving…':'Save changes'}</Button></div>
   </form>
  </Modal>

 </>
}

/* ─── Admin review: approve/reject submitted KPIs ─── */
function AdminReviewView({onToast}){
 const [month,setMonth]=useState(new Date().toISOString().slice(0,7))
 const [kpiUsers,setKpiUsers]=useState([]); const [selectedUser,setSelectedUser]=useState('')
 const [data,setData]=useState([]); const [error,setError]=useState(null)
 const [reviewModal,setReviewModal]=useState(null); const [reviewForm,setReviewForm]=useState({status:'approved',review_remarks:''})

 useEffect(()=>{api.get('/api/kpi/users-with-category').then(setKpiUsers).catch(()=>{})},[])
 const load=()=>{setError(null);let url='/api/kpi/review?month='+month;if(selectedUser)url+='&user_id='+selectedUser;api.get(url).then(setData).catch(setError)}
 useEffect(()=>{load()},[month,selectedUser])

 const openReview=item=>{setReviewForm({status:'approved',review_remarks:''});setReviewModal(item)}
 const submitReview=async()=>{
  try{
   await api.put(`/api/kpi/review/${reviewModal.id}`,{status:reviewForm.status,review_remarks:reviewForm.review_remarks})
   onToast?.({message:`KPI ${reviewForm.status}`});setReviewModal(null);load()
  }catch(err){onToast?.({type:'error',message:err.message})}
 }

 return <>
  <div className="kpi-toolbar">
   <MonthPicker value={month} onChange={setMonth}/>
   <Select value={selectedUser} onChange={e=>setSelectedUser(e.target.value)}><option value="">All users</option>{kpiUsers.map(u=><option key={u.id} value={u.id}>{u.name} · {u.category}</option>)}</Select>
  </div>
  <ErrorBanner error={error} onRetry={load}/>
  {data.length===0&&<Empty title="No submissions" text="No KPI submissions found for the selected month."/>}
  {data.map(ug=><section key={`${ug.user_id}-${ug.category}`} className="panel kpi-group">
   <div className="kpi-user-head"><div><h3>{ug.user_name}</h3><Pill tone="info">{ug.category}</Pill></div>

   </div>
   <table className="kpi-tbl"><thead><tr><th>KRA</th><th>KPI</th><th className="ctr">Target</th><th className="ctr">Achieved</th><th className="ctr">%</th><th className="ctr">Status</th><th></th></tr></thead><tbody>
    {ug.items.map(item=>{
     const pct=item.target_value>0?Math.round((item.actual_value/item.target_value)*100):null
     return <tr key={item.id}>
      <td className="kpi-kra-cell">{item.kra}</td>
      <td className="kpi-name">{item.kpi}{item.review_remarks&&<div className="kpi-review-note">Approver: {item.review_remarks}</div>}</td>
      <td className="ctr">{item.target_value||'—'}</td>
      <td className="ctr"><strong>{item.actual_value}</strong></td>
      <td className="ctr">{pct!=null?<span className={pct>=100?'text-success':pct>=70?'text-warning':'text-danger'}>{pct}%</span>:'—'}</td>
      <td className="ctr">{statusPill(item.status)}</td>
      <td>{item.status==='submitted'&&<Button variant="text" onClick={()=>openReview(item)}>Review</Button>}</td>
     </tr>
    })}
   </tbody></table>
   <OverallReview key={`${ug.user_id}-${ug.category}-${month}`} group={ug} month={month} onToast={onToast} onSaved={load}/>
  </section>)}
  <Modal open={!!reviewModal} onClose={()=>setReviewModal(null)} title="Review KPI" eyebrow={reviewModal?.kpi}>
   {reviewModal&&<div>
    <div className="kpi-review-summary">
     <div><strong>KRA:</strong> {reviewModal.kra}</div>
     <div><strong>KPI:</strong> {reviewModal.kpi}</div>
     <div><strong>Target:</strong> {reviewModal.target_value}</div>
     <div><strong>Achieved:</strong> {reviewModal.actual_value}</div>
     <div><strong>User remarks:</strong> {reviewModal.remarks||'None'}</div>
    </div>
    <Field label="Decision"><Select value={reviewForm.status} onChange={e=>setReviewForm(f=>({...f,status:e.target.value}))}><option value="approved">Approve</option><option value="rejected">Reject</option></Select></Field>
    <Field label="Review remarks"><Textarea value={reviewForm.review_remarks} onChange={e=>setReviewForm(f=>({...f,review_remarks:e.target.value}))} placeholder="Optional feedback"/></Field>
    <div className="modal-actions"><Button variant="ghost" onClick={()=>setReviewModal(null)}>Cancel</Button><Button onClick={submitReview}>{reviewForm.status==='approved'?'Approve':'Reject'}</Button></div>
   </div>}
  </Modal>
 </>
}

/* ─── Main KPI Page ─── */
export default function KPIPage({onToast}){
 const {user}=useAuth()
 const isAdmin=user?.role==='Super Admin'||user?.role==='Admin'
 const [tab,setTab]=useState(isAdmin?'manage':'my')

 return <>
  <SectionHeader eyebrow="Performance management" title="KPI Tracker" text="Track monthly KRA/KPI targets, update actuals and submit for review." actions={isAdmin?<div className="segmented"><button className={tab==='manage'?'active':''} onClick={()=>setTab('manage')}>Manage KPIs</button><button className={tab==='review'?'active':''} onClick={()=>setTab('review')}>Review team</button></div>:null}/>
  {isAdmin?(tab==='review'?<AdminReviewView onToast={onToast}/>:<><AdminKPIView onToast={onToast}/>{user.category&&<><h2>My KPI submission</h2><MyKPIView onToast={onToast}/></>}</>):<MyKPIView onToast={onToast}/>}
 </>
}

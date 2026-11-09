import React,{useEffect,useMemo,useState} from 'react'
import { api } from '../lib/api'
import { dateText,dateTimeText,money } from '../lib/format'
import { Button,Empty,ErrorBanner,Field,Input,Select,SectionHeader,Spinner } from '../components/UI'
import { Icon } from '../components/Icons'
import { useAuth } from '../components/Auth'

// Report generation. Every dataset is read through the same helper its own page uses, so a report
// shows exactly the records the viewer could already open — never more. The preview is capped and
// says so; the CSV is the whole thing and stays behind the export permission, as it always has.
const emptyFilters={dataset:'opportunities',date_from:'',date_to:'',status:'',owner_id:'',q:''}
// Columns holding money are right-aligned and formatted; everything else is rendered as stored.
const isMoney=key=>key==='amount'||key.startsWith('amount_')

export default function ReportsPage({route,onToast}){
 const {has}=useAuth()
 // Opened from a dashboard row, the page should already be on the report that was clicked rather
 // than on the default one — four rows that all land on the same view are four lies.
 const wanted=route?.query?.get('dataset')
 const [options,setOptions]=useState(null)
 const [filters,setFilters]=useState(()=>({...emptyFilters,...(wanted?{dataset:wanted}:{})}))
 const [data,setData]=useState(null); const [error,setError]=useState(null); const [busy,setBusy]=useState(false)
 const set=(k,v)=>setFilters(f=>({...f,[k]:v,...(k==='dataset'?{status:''}:{})}))

 useEffect(()=>{api.get('/api/reports/options').then(setOptions).catch(setError)},[])
 const qs=useMemo(()=>{const p=new URLSearchParams();Object.entries(filters).forEach(([k,v])=>v&&p.set(k,v));return p.toString()},[filters])
 const run=async()=>{setBusy(true);setError(null);try{setData(await api.get('/api/reports/run?'+qs))}catch(e){setError(e)}finally{setBusy(false)}}
 useEffect(()=>{if(options)run()},[qs,options])

 const dataset=options?.datasets?.find(d=>d.key===filters.dataset)
 // The browser does the download so the file is streamed rather than buffered through JS, and the
 // session cookie rides along exactly as it does for every other request.
 const download=()=>{window.location.href=`${api.base}/api/reports/run.csv?${qs}`;onToast?.({message:'Report download started'})}

 if(!options&&!error)return <Spinner label="Loading reports"/>
 return <>
  <SectionHeader eyebrow="Reporting" title="Report generation"
   text="Build a report from any record set you can already see, preview it, and take it away as CSV."
   actions={options?.can_export
     ?<Button icon="download" onClick={download} disabled={!data?.total}>Download CSV</Button>
     :<span className="subtle">Your role can build and read reports, but not export them.</span>}/>
  <ErrorBanner error={error} onRetry={run}/>
  <div className="toolbar-card report-toolbar">
   <Field label="Report"><Select value={filters.dataset} onChange={e=>set('dataset',e.target.value)}>
    {(options?.datasets||[]).map(d=><option key={d.key} value={d.key}>{d.label}</option>)}
   </Select></Field>
   <Field label="Created from"><Input type="date" value={filters.date_from} onChange={e=>set('date_from',e.target.value)}/></Field>
   <Field label="Created to"><Input type="date" value={filters.date_to} onChange={e=>set('date_to',e.target.value)}/></Field>
   <Field label="Status"><Select value={filters.status} onChange={e=>set('status',e.target.value)}>
    <option value="">Any status</option>{(dataset?.stages||[]).map(x=><option key={x}>{x}</option>)}
   </Select></Field>
   <Field label="Owner"><Select value={filters.owner_id} onChange={e=>set('owner_id',e.target.value)}>
    <option value="">Any owner</option>{(options?.owners||[]).map(o=><option key={o.id} value={o.id}>{o.name}</option>)}
   </Select></Field>
   <Field label="Search"><Input placeholder="Company, name or owner" value={filters.q} onChange={e=>set('q',e.target.value)}/></Field>
   <button className="icon-btn" title="Reset filters" onClick={()=>setFilters(emptyFilters)}><Icon name="refresh"/></button>
  </div>

  {data&&<section className="panel table-panel">
   <div className="inline-head">
    <div>
     <h3>{data.label}</h3>
     <p>{data.total===0?'No records match these filters.'
        :data.shown<data.total?`Showing the first ${data.shown} of ${data.total} records — the CSV contains all ${data.total}.`
        :`${data.total} ${data.total===1?'record':'records'}.`}</p>
    </div>
    <span className="subtle">Generated {dateTimeText(data.generated_at)}{data.fx_as_of&&` · ${data.currency} amounts at rates of ${dateText(data.fx_as_of)}`}</span>
   </div>
   {data.total
     ?<div className="report-scroll"><table className="report-table">
       <thead><tr>{data.columns.map(c=><th key={c.key} className={isMoney(c.key)?'num':undefined}>{c.label}</th>)}</tr></thead>
       <tbody>{data.rows.map((r,i)=><tr key={i}>{data.columns.map(c=>
         <td key={c.key} className={isMoney(c.key)?'num':undefined}>
          {isMoney(c.key)&&r[c.key]!==''&&r[c.key]!=null
            ? money(r[c.key],c.key==='amount'?r.currency:data.currency,false)
            : (r[c.key]??'—')}
         </td>)}</tr>)}</tbody>
      </table></div>
     :<Empty title="Nothing to report" text="Widen the dates, clear the filters, or pick another report."/>}
  </section>}
  {busy&&!data&&<Spinner label="Building report"/>}
 </>
}

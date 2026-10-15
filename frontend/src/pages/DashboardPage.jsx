import React,{useEffect,useState} from 'react'
import { api } from '../lib/api'
import { money } from '../lib/format'
import { Button,Empty,ErrorBanner,Spinner } from '../components/UI'
import { navigate } from '../lib/router'
import { useAuth } from '../components/Auth'
import { useViewCurrency } from '../lib/useViewCurrency'
import { CurrencyPicker } from '../components/CurrencyPicker'

// The dashboard reports the business by the currency each deal was booked in, and reports exactly
// two things about it: what has been won, and what is still in the pipeline. Everything else that
// used to sit on this page (forecast, funnel, owners, attention, trend) lives on its own page.
const SCOPE_LABEL={all:'All Business',team:'My Team'}
const projects=n=>`${n} ${n===1?'project':'projects'}`

export default function DashboardPage(){
 const {has,user}=useAuth(); const [data,setData]=useState(null); const [error,setError]=useState(null)
 const vc=useViewCurrency(data?.currency)
 const load=async()=>{setError(null);try{setData(await api.get('/api/dashboard/analytics'))}catch(e){setError(e)}}
 useEffect(()=>{load()},[])
 if(!data&&!error)return <Spinner label="Loading won and pipeline by currency"/>
 const corporate=data?.currency||vc.corporate; const currency=vc.view; const cv=vc.convert
 const rows=data?.currency_totals||[]; const fx=data?.fx||{}; const missingRates=fx.missing_rates||[]
 // Projects this page reports under neither Won nor Pipeline. An unrecognised status is a fault,
 // not a category: the record is in the database but counts towards nothing, which to whoever
 // entered it looks exactly like the tool losing their work. Named here so it can be corrected.
 const uncounted=data?.uncounted||{}; const unrecognised=uncounted.unrecognised||[]; const onHold=uncounted.on_hold||0
 // A corporate-currency total is only honest when every currency carrying value converts; one
 // unrated currency makes the sum a partial figure, and a partial figure must not pose as a whole.
 const complete=rows.every(r=>r.convertible||(!r.pipeline&&!r.won))
 const totalWon=complete?rows.reduce((n,r)=>n+(r.won_corporate||0),0):null
 const totalPipeline=complete?rows.reduce((n,r)=>n+(r.pipeline_corporate||0),0):null
 const wonCount=rows.reduce((n,r)=>n+r.won_count,0); const pipelineCount=rows.reduce((n,r)=>n+r.pipeline_count,0)
 return <>
  <section className="hero-dashboard">
   <div>
    <span className="eyebrow hero-eyebrow">Revenue Command Center · {SCOPE_LABEL[user?.scope_type]||'My Business'}</span>
    <h1>Projects won and <em>projects in pipeline.</em></h1>
    <p>Every figure in the currency the deal was booked in — nothing is blended.</p>
   </div>
   <div className="hero-actions">
    <CurrencyPicker fx={vc}/>
    {has('LEAD_CREATE')&&<Button icon="plus" onClick={()=>navigate('prospects?new=1')}>New prospect</Button>}
   </div>
  </section>
  <ErrorBanner error={error} onRetry={load}/>
  {data&&<>
   {missingRates.length>0&&<div className="warning-callout stacked">
    <strong>{missingRates.join(', ')} {missingRates.length===1?'has':'have'} no exchange rate</strong>
    <span>These amounts are reported below in their own currency, but cannot be folded into a {currency} total. Add a rate under Admin → Currency.</span>
   </div>}
   {unrecognised.length>0&&<div className="warning-callout stacked">
    <strong>{projects(unrecognised.length)} with a stage the app does not recognise</strong>
    <span>They are in the system, but a stage outside the app's own list leaves them missing from the figures below — or counted in the wrong one. Open each and set its stage. The exact stored value is quoted, so a stray space shows up.</span>
    <ul className="uncounted-list">{unrecognised.map(o=>
     <li key={o.id}>
      <button onClick={()=>navigate(`pipeline?opp=${o.id}`)}>{o.name}</button>
      <span>{o.company}</span>
      <code>{o.status?JSON.stringify(o.status):'(blank)'}</code>
      <b>{money(o.amount,o.currency,false)}</b>
     </li>)}
    </ul>
   </div>}
   <section className="panel region-currency">
    <div className="inline-head">
     <div>
      <h3>By currency</h3>
      <p>{projects(wonCount)} won · {projects(pipelineCount)} in pipeline{onHold>0&&` · ${onHold} on hold, not shown`}</p>
     </div>
     <span className="subtle">Corporate currency: {corporate}</span>
    </div>
    {rows.length?<>
     <div className="region-currency-grid">{rows.map(r=>
      <article key={r.currency} className={r.convertible?'region-card':'region-card is-unrated'}>
       <header><strong>{r.currency}</strong><span>{projects(r.won_count+r.pipeline_count)}</span></header>
       <div className="region-legs">
        <div className="region-leg">
         <span className="leg-code">Won</span>
         <div className="leg-figures leg-won"><b>{money(r.won,r.currency,false)}</b><small>{projects(r.won_count)} won</small></div>
        </div>
        <div className={r.convertible?'region-leg':'region-leg is-unrated'}>
         <span className="leg-code">Pipeline</span>
         <div className="leg-figures"><b>{money(r.pipeline,r.currency,false)}</b><small>{projects(r.pipeline_count)} in pipeline</small></div>
         {!r.convertible&&<span className="leg-flag" title={`No exchange rate is configured for ${r.currency}`}>no FX rate</span>}
        </div>
       </div>
       {r.convertible&&r.currency!==currency&&<footer>
        ≈ {money(cv(r.won_corporate),currency,false)} won · {money(cv(r.pipeline_corporate),currency,false)} pipeline in {currency}
       </footer>}
      </article>)}
     </div>
     <footer className="currency-total">
      {totalWon!=null
        ?<><span>All currencies in {currency}</span><strong>{money(cv(totalWon),currency,false)} won</strong><strong>{money(cv(totalPipeline),currency,false)} in pipeline</strong></>
        :<span className="text-warning">A combined {currency} total is unavailable — {missingRates.join(', ')} {missingRates.length===1?'has':'have'} no rate.</span>}
     </footer>
    </>:<Empty title="No projects yet" text="Won and pipeline figures appear here as soon as an opportunity is in your scope."/>}
   </section>
  </>}
 </>
}

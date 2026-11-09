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
 const {has,user}=useAuth(); const [data,setData]=useState(null); const [attention,setAttention]=useState(null); const [error,setError]=useState(null)
 const vc=useViewCurrency(data?.currency)
 // Attention is its own call because it answers a different question from the money panel and must
 // not hold it up; a failure there leaves the figures on screen rather than blanking the page.
 const load=async()=>{setError(null);try{setData(await api.get('/api/dashboard/analytics'))}catch(e){setError(e)}
  try{setAttention(await api.get('/api/dashboard/attention'))}catch{setAttention(null)}}
 useEffect(()=>{load()},[])
 if(!data&&!error)return <Spinner label="Loading won and pipeline by currency"/>
 const corporate=data?.currency||vc.corporate; const currency=vc.view; const cv=vc.convert
 const rows=data?.currency_totals||[]; const fx=data?.fx||{}; const missingRates=fx.missing_rates||[]
 // Prospects and Partnerships are two separate books. This panel reports both; Opportunity
 // Pipeline, Forecast and Leadership report prospects only. So the partnership share is named on
 // every figure it touches — without it the combined total simply disagreed with those pages and the
 // same deal read as counted twice. Named, the two reconcile: this panel minus the partnership share
 // is exactly what those pages show.
 const partnerRows=data?.partner_currency_totals||[]
 const partnerBy=Object.fromEntries(partnerRows.map(r=>[r.currency,r]))
 const partnerWon=partnerRows.reduce((n,r)=>n+r.won_count,0)
 const partnerPipeline=partnerRows.reduce((n,r)=>n+r.pipeline_count,0)
 const hasPartners=partnerWon+partnerPipeline>0
 // Projects this page reports under neither Won nor Pipeline. An unrecognised status is a fault,
 // not a category: the record is in the database but counts towards nothing, which to whoever
 // entered it looks exactly like the tool losing their work. Named here so it can be corrected.
 const uncounted=data?.uncounted||{}; const unrecognised=uncounted.unrecognised||[]; const onHold=uncounted.on_hold||0
 // The two buckets are addressed differently: the prospect board opens a deal by its own id, while
 // a partnership deal is reached through its Partnership 360. Ids are only unique within a bucket,
 // so sending a partnership id to `pipeline?opp=` would silently open an unrelated prospect deal —
 // and the list rows are keyed by bucket and id together for the same reason.
 // Two lines, either of which may be absent: the corporate-currency equivalent when the viewer is
 // looking in another currency, and the partnership share when this currency has one.
 const cardFooter=r=>{
  const p=partnerBy[r.currency]; const conv=r.convertible&&r.currency!==currency
  if(!conv&&!p) return null
  return <footer>
   {conv&&<div>≈ {money(cv(r.won_corporate),currency,false)} won · {money(cv(r.pipeline_corporate),currency,false)} pipeline in {currency}</div>}
   {p&&<div>of which partnerships: {money(p.won,r.currency,false)} won · {money(p.pipeline,r.currency,false)} pipeline</div>}
  </footer>
 }
 const openUncounted=o=>navigate(o.bucket==='partnership'?`partnership/${o.partnership_id}`:`pipeline?opp=${o.id}`)
 // A corporate-currency total is only honest when every currency carrying value converts; one
 // unrated currency makes the sum a partial figure, and a partial figure must not pose as a whole.
 const complete=rows.every(r=>r.convertible||(!r.pipeline&&!r.won))
 const totalWon=complete?rows.reduce((n,r)=>n+(r.won_corporate||0),0):null
 const totalPipeline=complete?rows.reduce((n,r)=>n+(r.pipeline_corporate||0),0):null
 const wonCount=rows.reduce((n,r)=>n+r.won_count,0); const pipelineCount=rows.reduce((n,r)=>n+r.pipeline_count,0)
 // Lost sits beside won because a win rate is only legible against what it was measured on. It is
 // reported, never folded into the headline totals — it is business that went away, not business
 // held. `complete` already guarantees every leg converts before any corporate total is shown.
 const lostCount=rows.reduce((n,r)=>n+(r.lost_count||0),0)
 const totalLost=complete?rows.reduce((n,r)=>n+(r.lost_corporate||0),0):null
 const winRate=wonCount+lostCount>0?Math.round(100*wonCount/(wonCount+lostCount)):null
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
     <li key={`${o.bucket}-${o.id}`}>
      <button onClick={()=>openUncounted(o)}>{o.name}</button>
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
      <p>{projects(wonCount)} won · {projects(lostCount)} lost · {projects(pipelineCount)} in pipeline{onHold>0&&` · ${onHold} on hold, not shown`}{winRate!=null&&` · ${winRate}% win rate`}</p>
      {hasPartners&&<p className="subtle">Prospects and partnerships together. Of these, {partnerWon} won and {partnerPipeline} in pipeline come from partnerships — Opportunity Pipeline, Forecast and Leadership count prospects only, so their totals are lower by exactly that much.</p>}
     </div>
     <span className="subtle">Corporate currency: {corporate}</span>
    </div>
    {rows.length?<>
     <div className="region-currency-grid">{rows.map(r=>
      <article key={r.currency} className={r.convertible?'region-card':'region-card is-unrated'}>
       <header><strong>{r.currency}</strong><span>{projects(r.won_count+r.pipeline_count+(r.lost_count||0))}</span></header>
       <div className="region-legs">
        <div className="region-leg">
         <span className="leg-code">Won</span>
         <div className="leg-figures leg-won"><b>{money(r.won,r.currency,false)}</b><small>{projects(r.won_count)} won</small></div>
        </div>
        {(r.lost_count||0)>0&&<div className="region-leg">
         <span className="leg-code">Lost</span>
         <div className="leg-figures leg-lost"><b>{money(r.lost,r.currency,false)}</b><small>{projects(r.lost_count)} lost</small></div>
        </div>}
        <div className={r.convertible?'region-leg':'region-leg is-unrated'}>
         <span className="leg-code">Pipeline</span>
         <div className="leg-figures"><b>{money(r.pipeline,r.currency,false)}</b><small>{projects(r.pipeline_count)} in pipeline</small></div>
         {!r.convertible&&<span className="leg-flag" title={`No exchange rate is configured for ${r.currency}`}>no FX rate</span>}
        </div>
       </div>
       {cardFooter(r)}
      </article>)}
     </div>
     <footer className="currency-total">
      {totalWon!=null
        ?<><span>{hasPartners?`Prospects + partnerships, in ${currency}`:`All currencies in ${currency}`}</span><strong>{money(cv(totalWon),currency,false)} won</strong>{lostCount>0&&<strong className="total-lost">{money(cv(totalLost),currency,false)} lost</strong>}<strong>{money(cv(totalPipeline),currency,false)} in pipeline</strong></>
        :<span className="text-warning">A combined {currency} total is unavailable — {missingRates.join(', ')} {missingRates.length===1?'has':'have'} no rate.</span>}
     </footer>
    </>:<Empty title="No projects yet" text="Won and pipeline figures appear here as soon as an opportunity is in your scope."/>}
   </section>

   {/* Three places to go next. Every figure here is the one the panel above already reports, or a
       count taken over the whole set rather than the capped list, so nothing on this page disagrees
       with anything else on it. Each row opens the page that owns it, already filtered. */}
   <div className="dash-next">
    <section className="panel dash-card">
     <div className="inline-head"><div><h3>Key highlights</h3><p>The same figures as above, in {currency}.</p></div></div>
     <ul className="dash-rows">
      <li><button onClick={()=>navigate('pipeline?status=Closed Won&mode=list')}>
       <span>Won</span><b className="val-won">{totalWon==null?'—':money(cv(totalWon),currency,false)}</b><small>{projects(wonCount)}</small></button></li>
      <li><button onClick={()=>navigate('pipeline')}>
       <span>In pipeline</span><b>{totalPipeline==null?'—':money(cv(totalPipeline),currency,false)}</b><small>{projects(pipelineCount)}</small></button></li>
      <li><button onClick={()=>navigate('pipeline?status=Closed Lost&mode=list')}>
       <span>Lost</span><b className="val-lost">{totalLost==null?'—':money(cv(totalLost),currency,false)}</b><small>{projects(lostCount)}</small></button></li>
      <li><button onClick={()=>navigate('leadership')}>
       <span>Win rate</span><b>{winRate==null?'—':`${winRate}%`}</b><small>{wonCount} of {wonCount+lostCount} decided</small></button></li>
     </ul>
    </section>

    <section className="panel dash-card">
     <div className="inline-head"><div><h3>Key supports</h3><p>Work waiting on a person today.</p></div></div>
     {attention?<ul className="dash-rows">
      <li><button onClick={()=>navigate('actions')}>
       <span>Overdue actions</span><b className={attention.counts.overdue_actions?'text-danger':undefined}>{attention.counts.overdue_actions}</b><small>past their due date</small></button></li>
      <li><button onClick={()=>navigate('pipeline')}>
       <span>Follow-ups overdue</span><b className={attention.counts.followups_overdue?'text-warning':undefined}>{attention.counts.followups_overdue}</b><small>open deals past follow-up</small></button></li>
      <li><button onClick={()=>navigate('pipeline')}>
       <span>Closing within 7 days</span><b>{attention.counts.closing_soon}</b><small>expected close is near</small></button></li>
     </ul>:<p className="dash-quiet">Attention items are unavailable just now.</p>}
    </section>

    {has('REPORT_VIEW')&&<section className="panel dash-card">
     <div className="inline-head"><div><h3>Reports</h3><p>Build a report and take it away as CSV.</p></div></div>
     <ul className="dash-rows">
      <li><button onClick={()=>navigate('reports?dataset=opportunities')}><span>Opportunity pipeline</span><b>→</b><small>prospect deals</small></button></li>
      <li><button onClick={()=>navigate('reports?dataset=partner_opportunities')}><span>Partnership opportunities</span><b>→</b><small>partner deals</small></button></li>
      <li><button onClick={()=>navigate('reports?dataset=prospects')}><span>Prospects</span><b>→</b><small>the prospect book</small></button></li>
      <li><button onClick={()=>navigate('reports?dataset=partnerships')}><span>Partnerships</span><b>→</b><small>the partner book</small></button></li>
     </ul>
    </section>}
   </div>
  </>}
 </>
}

import React,{useEffect,useMemo,useRef,useState} from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { feature } from 'topojson-client'
import world from 'world-atlas/countries-110m.json'

// Country shapes are bundled so the map needs no external tile server (the app's CSP blocks those).
const LAND=feature(world,world.objects.countries)
LAND.features=LAND.features.filter(f=>f.id!=='010') // drop Antarctica
// Rings that cross the date line (Russia, Fiji) otherwise draw a band across the whole map
const unwrapRing=ring=>{if(ring.some(([x])=>x>150)&&ring.some(([x])=>x<-150))ring.forEach(p=>{if(p[0]<0)p[0]+=360})}
LAND.features.forEach(f=>{const g=f.geometry;if(!g)return;const polys=g.type==='Polygon'?[g.coordinates]:g.coordinates;polys.forEach(poly=>poly.forEach(unwrapRing))})

const GEO={
  'USA':[39.8,-98.6],'UK':[54.0,-2.0],'India':[20.6,79.0],'Germany':[51.2,10.4],'France':[46.6,2.2],
  'Australia':[-25.3,133.8],'Canada':[56.1,-106.3],'Japan':[36.2,138.3],'Singapore':[1.35,103.8],
  'UAE':[23.4,53.8],'Brazil':[-14.2,-51.9],'South Korea':[35.9,127.8],'China':[35.9,104.2],
  'Mexico':[23.6,-102.6],'Netherlands':[52.1,5.3],'Sweden':[60.1,18.6],'Norway':[60.5,8.5],
  'Switzerland':[46.8,8.2],'Italy':[41.9,12.5],'Spain':[40.5,-3.7],'Ireland':[53.4,-8.2],
  'Israel':[31.0,34.9],'New Zealand':[-40.9,174.9],'South Africa':[-30.6,22.9],
  'Saudi Arabia':[23.9,45.1],'Qatar':[25.3,51.2],'Poland':[51.9,19.1],'Denmark':[56.3,9.5],
  'Finland':[61.9,25.7],'Belgium':[50.5,4.5],'Austria':[47.5,14.6],'Portugal':[39.4,-8.2],
  'Czech Republic':[49.8,15.5],'Thailand':[15.9,101.0],'Malaysia':[4.2,101.98],
  'Indonesia':[-0.8,113.9],'Philippines':[12.9,121.8],'Vietnam':[14.1,108.3],
  'Colombia':[4.6,-74.3],'Argentina':[-38.4,-63.6],'Chile':[-35.7,-71.5],'Peru':[-9.2,-75.0],
  'Egypt':[26.8,30.8],'Nigeria':[9.1,8.7],'Kenya':[-0.02,37.9],'Morocco':[31.8,-7.1],
  'Turkey':[39.0,35.2],'Russia':[61.5,105.3],'Taiwan':[23.7,121.0],'Hong Kong':[22.4,114.1],
  'United States':[39.8,-98.6],'United Kingdom':[54.0,-2.0],'England':[52.4,-1.5],
  'North America':[39.8,-98.6],'Europe':[50.1,9.7],'APAC':[20.0,100.0],
  'Middle East':[25.0,45.0],'Africa':[0.0,25.0],'Latin America':[-15.0,-60.0],
}
const CONTINENTS=[['NORTH AMERICA',[45,-102]],['SOUTH AMERICA',[-18,-60]],['EUROPE',[50,15]],['AFRICA',[5,20]],['ASIA',[48,90]],['AUSTRALIA',[-38,134]]]
const HQ=[51.49,-0.31] // JSAN Global Headquarters, Brentford UK (same hub as the jsan.com contact map)

// Free-text country/city values -> Natural Earth country names used by world-atlas
const ALIAS={'usa':'United States of America','us':'United States of America','united states':'United States of America','america':'United States of America',
  'uk':'United Kingdom','england':'United Kingdom','scotland':'United Kingdom','wales':'United Kingdom','great britain':'United Kingdom','britain':'United Kingdom',
  'uae':'United Arab Emirates','dubai':'United Arab Emirates','abu dhabi':'United Arab Emirates','czech republic':'Czechia','holland':'Netherlands',
  'london':'United Kingdom','manchester':'United Kingdom','brentford':'United Kingdom','birmingham':'United Kingdom',
  'bangalore':'India','bengaluru':'India','hyderabad':'India','mumbai':'India','delhi':'India','chennai':'India','pune':'India','south india':'India',
  'riyadh':'Saudi Arabia','jeddah':'Saudi Arabia','bangkok':'Thailand','doha':'Qatar','sydney':'Australia','melbourne':'Australia','toronto':'Canada',
  'new york':'United States of America','singapore':'Singapore','hong kong':'China'}
const ATLAS_BY_LOWER=Object.fromEntries(LAND.features.map(f=>[String(f.properties?.name||'').toLowerCase(),f.properties?.name]))
// Marker position for any atlas country: centre of its largest polygon's bounding box
const CENTRE={}
LAND.features.forEach(f=>{const g=f.geometry;if(!g)return;const polys=g.type==='Polygon'?[g.coordinates]:g.coordinates;let best=null,area=-1
  polys.forEach(p=>{const xs=p[0].map(c=>c[0]),ys=p[0].map(c=>c[1]);const a=(Math.max(...xs)-Math.min(...xs))*(Math.max(...ys)-Math.min(...ys));if(a>area){area=a;best=[(Math.max(...ys)+Math.min(...ys))/2,(Math.max(...xs)+Math.min(...xs))/2]}})
  if(best)CENTRE[f.properties.name]=best})
const toAtlas=v=>{const k=String(v||'').trim().toLowerCase().replace(/\s+/g,' ');if(!k)return null;return ALIAS[k]||ATLAS_BY_LOWER[k]||null}

// One location value can name several countries ("UK and Australia") or a city ("Manchester")
function resolveCountries(country,region){
  const parts=String(country||'').split(/\s+and\s+|[,/&|;]+/i).map(s=>s.trim()).filter(Boolean)
  const found=[...new Set(parts.map(toAtlas).filter(Boolean))]
  if(found.length) return found
  const r=toAtlas(region)
  return r?[r]:[]
}
function coordsFor(name){
  const g=Object.keys(GEO).find(k=>toAtlas(k)===name)
  return g?GEO[g]:CENTRE[name]||null
}

// Curved arc bowing towards the pole, like the great-circle "delivery links" in the reference
function arc(a,b){
  const mid=[(a[0]+b[0])/2,(a[1]+b[1])/2]
  const dLat=b[0]-a[0],dLng=b[1]-a[1]
  let pLat=dLng,pLng=-dLat // perpendicular
  if(pLat<0){pLat=-pLat;pLng=-pLng}
  const k=0.2
  const ctrl=[mid[0]+pLat*k,mid[1]+pLng*k]
  const pts=[]
  for(let t=0;t<=1.0001;t+=0.05){pts.push([(1-t)*(1-t)*a[0]+2*(1-t)*t*ctrl[0]+t*t*b[0],(1-t)*(1-t)*a[1]+2*(1-t)*t*ctrl[1]+t*t*b[1]])}
  return pts
}

const dotHtml=size=>`<span class="pmap-marker" style="width:${size}px;height:${size}px"></span>`

const WORLD_CENTER=[28,12]
// Zoom at which one world copy exactly fills the panel width, like the reference map
const fitWidthZoom=el=>Math.log2(Math.max(el.clientWidth,256)/256)

export default function ProspectMap({locations=[],regionCounts=[],totalLeads=0,focus=''}){
  const containerRef=useRef(null)
  const mapInstance=useRef(null)
  const pointsRef=useRef([])
  const [expanded,setExpanded]=useState(false)

  // Merge location rows by resolved country
  const byCountry=useMemo(()=>{
    const out={}
    for(const loc of locations){
      for(const name of resolveCountries(loc.country,loc.region)){
        const e=out[name]||(out[name]={country:name,leads:0,opportunities:0})
        e.leads+=loc.leads||0; e.opportunities+=loc.opportunities||0
      }
    }
    return out
  },[locations])

  useEffect(()=>{
    if(!containerRef.current) return
    if(mapInstance.current){mapInstance.current.remove();mapInstance.current=null}

    const worldZoom=fitWidthZoom(containerRef.current)
    const map=L.map(containerRef.current,{
      center:WORLD_CENTER,zoom:worldZoom,zoomSnap:0,minZoom:worldZoom,maxZoom:6,
      zoomControl:false,attributionControl:false,
      maxBounds:[[-62,-180],[84,190]],maxBoundsViscosity:1,
    })
    mapInstance.current=map
    pointsRef.current=[]

    // Countries with prospects are filled blue; the rest stay dark with fine borders (as in the reference)
    const active=new Set(Object.keys(byCountry))
    L.geoJSON(LAND,{interactive:false,style:f=>active.has(f.properties?.name)
      ?{fillColor:'#164a82',fillOpacity:1,color:'#4f7fb3',weight:0.6,opacity:0.7}
      :{fillColor:'#021a3d',fillOpacity:1,color:'#9db8d9',weight:0.5,opacity:0.3}}).addTo(map)

    CONTINENTS.forEach(([name,pos])=>L.marker(pos,{interactive:false,icon:L.divIcon({className:'pmap-continent',html:name.replace(' ','<br>'),iconSize:[120,40],iconAnchor:[60,20]})}).addTo(map))

    const points=[]
    for(const e of Object.values(byCountry)){
      const c=coordsFor(e.country)
      if(c) points.push({...e,lat:c[0],lng:c[1]})
    }
    pointsRef.current=points

    points.forEach(p=>{
      if(Math.abs(p.lat-HQ[0])>1||Math.abs(p.lng-HQ[1])>1)
        L.polyline(arc(HQ,[p.lat,p.lng]),{color:'#27c6ef',weight:1.3,opacity:0.75,dashArray:'6 6',interactive:false}).addTo(map)
    })

    points.forEach(p=>{
      const size=15 // uniform markers, as in the reference
      L.marker([p.lat,p.lng],{icon:L.divIcon({className:'pmap-dot',html:dotHtml(size),iconSize:[size,size],iconAnchor:[size/2,size/2]})})
        .addTo(map)
        .bindTooltip(`<strong>${p.country}</strong><br/>${p.leads} prospect${p.leads!==1?'s':''} · ${p.opportunities} opportunit${p.opportunities!==1?'ies':'y'}`,{className:'pmap-tip',direction:'top',offset:[0,-8]})
    })

    if(points.length){
      L.marker(HQ,{icon:L.divIcon({className:'pmap-dot',html:dotHtml(15),iconSize:[15,15],iconAnchor:[7.5,7.5]})})
        .addTo(map).bindTooltip('<strong>JSAN Global HQ</strong><br/>Brentford, UK',{className:'pmap-tip',direction:'top',offset:[0,-8]})
      // Whole world by default (as in the reference); zoom to the prospects only when a region is filtered
      if(focus) map.fitBounds(L.latLngBounds(points.map(p=>[p.lat,p.lng])),{padding:[90,90],maxZoom:4})
    }

    return()=>{if(mapInstance.current){mapInstance.current.remove();mapInstance.current=null}}
  },[byCountry,focus])

  // Expand / minimise: after the panel changes size, re-measure and show the same view again
  useEffect(()=>{
    const m=mapInstance.current,el=containerRef.current
    if(m&&el){
      m.invalidateSize({animate:false})
      const z=fitWidthZoom(el);m.setMinZoom(z)
      const pts=pointsRef.current
      if(focus&&pts.length) m.fitBounds(L.latLngBounds(pts.map(p=>[p.lat,p.lng])),{padding:[90,90],maxZoom:4,animate:false})
      else m.setView(WORLD_CENTER,z,{animate:false})
    }
    if(!expanded) return
    const onKey=e=>{if(e.key==='Escape')setExpanded(false)}
    const prevOverflow=document.body.style.overflow
    document.body.style.overflow='hidden'
    window.addEventListener('keydown',onKey)
    return()=>{window.removeEventListener('keydown',onKey);document.body.style.overflow=prevOverflow}
  },[expanded])

  return <div className={`pmap-wrap${expanded?' is-expanded':''}`} role={expanded?'dialog':undefined} aria-modal={expanded||undefined} aria-label={expanded?'Prospect geography map':undefined}>
    <div ref={containerRef} className="pmap-canvas"/>
    <div className="pmap-info">
      <div className="pmap-info-label">Global Network</div>
      <div className="pmap-info-num">{totalLeads}<span>prospects</span></div>
      <div className="pmap-info-sub">Prospect region count</div>
    </div>
    <div className="pmap-controls">
      <button type="button" className="pmap-expand" onClick={()=>setExpanded(x=>!x)} title={expanded?'Minimise map':'Expand map'} aria-label={expanded?'Minimise map':'Expand map'} aria-pressed={expanded}>
        {expanded
          ?<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" x2="21" y1="10" y2="3"/><line x1="3" x2="10" y1="21" y2="14"/></svg>
          :<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" x2="14" y1="3" y2="10"/><line x1="3" x2="10" y1="21" y2="14"/></svg>}
      </button>
      <button type="button" onClick={()=>mapInstance.current?.zoomIn()} title="Zoom in" aria-label="Zoom in">+</button>
      <button type="button" onClick={()=>mapInstance.current?.zoomOut()} title="Zoom out" aria-label="Zoom out">&minus;</button>
    </div>
    <div className="pmap-legend" aria-label="Prospects by region">
      <span><i className="pmap-legend-dot"/>Prospect</span>
      {regionCounts.map(r=><span key={r.region} className="pmap-legend-region">{r.region}<b>{r.leads}</b></span>)}
    </div>
  </div>
}

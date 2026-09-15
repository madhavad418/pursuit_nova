import React,{useEffect,useRef} from 'react'
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
const CONTINENTS=[['NORTH AMERICA',[45,-102]],['SOUTH AMERICA',[-18,-60]],['EUROPE',[50,15]],['AFRICA',[5,20]],['ASIA',[48,90]],['AUSTRALIA',[-25,134]]]
const HQ=[51.49,-0.31] // JSAN Global Headquarters, Brentford UK (same hub as the jsan.com contact map)

function resolveCoords(country,region){
  const find=v=>{if(!v)return null;const k=Object.keys(GEO).find(x=>x.toLowerCase()===String(v).trim().toLowerCase());return k?GEO[k]:null}
  return find(country)||find(region)
}

// Gently curved arc between two points, like the reference "delivery links"
function arc(a,b){
  const mid=[(a[0]+b[0])/2,(a[1]+b[1])/2]
  const dx=b[1]-a[1],dy=b[0]-a[0]
  const ctrl=[mid[0]+dx*0.18,mid[1]-dy*0.18]
  const pts=[]
  for(let t=0;t<=1.0001;t+=0.05){pts.push([(1-t)*(1-t)*a[0]+2*(1-t)*t*ctrl[0]+t*t*b[0],(1-t)*(1-t)*a[1]+2*(1-t)*t*ctrl[1]+t*t*b[1]])}
  return pts
}

const dotHtml=size=>`<span class="pmap-marker" style="width:${size}px;height:${size}px"></span>`

const WORLD_CENTER=[28,12]
// Zoom at which one world copy exactly fills the panel width, like the reference map
const fitWidthZoom=el=>Math.log2(Math.max(el.clientWidth,256)/256)

export default function ProspectMap({locations=[],totalLeads=0,focus=''}){
  const containerRef=useRef(null)
  const mapInstance=useRef(null)

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

    L.geoJSON(LAND,{interactive:false,style:{fillColor:'#15477f',fillOpacity:1,color:'#5f8fc4',weight:0.6,opacity:0.45}}).addTo(map)

    CONTINENTS.forEach(([name,pos])=>L.marker(pos,{interactive:false,icon:L.divIcon({className:'pmap-continent',html:name.replace(' ','<br>'),iconSize:[120,40],iconAnchor:[60,20]})}).addTo(map))

    const points=[]
    for(const loc of locations){
      const c=resolveCoords(loc.country,loc.region)
      if(c) points.push({...loc,lat:c[0],lng:c[1]})
    }

    points.forEach(p=>{
      if(Math.abs(p.lat-HQ[0])>1||Math.abs(p.lng-HQ[1])>1)
        L.polyline(arc(HQ,[p.lat,p.lng]),{color:'#27c6ef',weight:1.3,opacity:0.75,dashArray:'6 6',interactive:false}).addTo(map)
    })

    points.forEach(p=>{
      const size=Math.min(16,11+Math.floor((p.leads||0)/2))
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
  },[locations,focus])

  const reset=()=>{const m=mapInstance.current;if(m&&containerRef.current)m.setView(WORLD_CENTER,fitWidthZoom(containerRef.current))}

  return <div className="pmap-wrap">
    <div ref={containerRef} className="pmap-canvas"/>
    <div className="pmap-info">
      <div className="pmap-info-label">Global Network</div>
      <div className="pmap-info-num">{totalLeads}<span>prospects</span></div>
      <div className="pmap-info-sub">{locations.length} {locations.length===1?'country':'countries'}</div>
    </div>
    <div className="pmap-controls">
      <button onClick={reset} title="Reset view" aria-label="Reset view">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" x2="14" y1="3" y2="10"/><line x1="3" x2="10" y1="21" y2="14"/></svg>
      </button>
      <button onClick={()=>mapInstance.current?.zoomIn()} title="Zoom in" aria-label="Zoom in">+</button>
      <button onClick={()=>mapInstance.current?.zoomOut()} title="Zoom out" aria-label="Zoom out">&minus;</button>
    </div>
    <div className="pmap-legend">
      <span><i className="pmap-legend-dot"/>Prospect</span>
      <span><i className="pmap-legend-line"/>HQ link</span>
    </div>
  </div>
}

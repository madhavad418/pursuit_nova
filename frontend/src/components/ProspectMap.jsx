import React,{useEffect,useRef} from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

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
  'North America':[39.8,-98.6],'Europe':[50.1,9.7],'APAC':[20.0,100.0],
  'Middle East':[25.0,45.0],'Africa':[0.0,25.0],'Latin America':[-15.0,-60.0],
  'Global':[20.0,0.0],'Unassigned':[20.0,0.0],
}

function resolveCoords(country,region){
  if(country&&GEO[country]) return GEO[country]
  if(region&&GEO[region]) return GEO[region]
  const key=Object.keys(GEO).find(k=>k.toLowerCase()===(country||'').toLowerCase())
  if(key) return GEO[key]
  const rkey=Object.keys(GEO).find(k=>k.toLowerCase()===(region||'').toLowerCase())
  if(rkey) return GEO[rkey]
  return null
}

// Cyan dot with white center — matches reference
function dotSvg(size){
  const r=size/2
  return `<svg width="${size+8}" height="${size+8}" viewBox="0 0 ${size+8} ${size+8}" xmlns="http://www.w3.org/2000/svg">
    <circle cx="${r+4}" cy="${r+4}" r="${r+3}" fill="rgba(0,212,255,0.15)"/>
    <circle cx="${r+4}" cy="${r+4}" r="${r}" fill="#00d4ff" stroke="white" stroke-width="2"/>
  </svg>`
}

export default function ProspectMap({locations=[],totalLeads=0}){
  const containerRef=useRef(null)
  const mapInstance=useRef(null)

  useEffect(()=>{
    if(!containerRef.current) return
    if(mapInstance.current){mapInstance.current.remove();mapInstance.current=null}

    const map=L.map(containerRef.current,{
      center:[20,15],zoom:2,minZoom:2,maxZoom:6,
      zoomControl:false,attributionControl:false,
      scrollWheelZoom:true,dragging:true,
      backgroundColor:'#0a1628'
    })
    mapInstance.current=map

    // OSM tiles with heavy dark-blue filter to match the reference
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
      maxZoom:19,attribution:''
    }).addTo(map)

    // Resolve locations to coordinates
    const points=[]
    for(const loc of locations){
      const coords=resolveCoords(loc.country,loc.region)
      if(coords) points.push({...loc,lat:coords[0],lng:coords[1]})
    }

    const hq=[17.4,78.5] // Hyderabad HQ

    // Draw dashed connection lines from HQ
    points.forEach(p=>{
      if(Math.abs(p.lat-hq[0])>1||Math.abs(p.lng-hq[1])>1){
        L.polyline([hq,[p.lat,p.lng]],{
          color:'#00d4ff',weight:1.2,opacity:0.35,dashArray:'8,10'
        }).addTo(map)
      }
    })

    // Add prospect dots
    points.forEach(p=>{
      const size=Math.min(14,8+p.leads)
      const icon=L.divIcon({
        className:'pmap-dot',
        html:dotSvg(size),
        iconSize:[size+8,size+8],iconAnchor:[(size+8)/2,(size+8)/2]
      })
      L.marker([p.lat,p.lng],{icon}).addTo(map).bindTooltip(
        `<strong>${p.country}</strong><br/>${p.leads} prospect${p.leads!==1?'s':''}<br/>${p.opportunities} opportunit${p.opportunities!==1?'ies':'y'}`,
        {className:'pmap-tip',direction:'top',offset:[0,-8]}
      )
    })

    // HQ marker (larger, brighter glow)
    if(points.length>0){
      const hqIcon=L.divIcon({
        className:'pmap-dot',
        html:`<svg width="24" height="24" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
          <circle cx="12" cy="12" r="10" fill="rgba(0,212,255,0.2)"/>
          <circle cx="12" cy="12" r="6" fill="#00d4ff" stroke="white" stroke-width="2.5"/>
        </svg>`,
        iconSize:[24,24],iconAnchor:[12,12]
      })
      L.marker(hq,{icon:hqIcon}).addTo(map).bindTooltip('JSAN HQ',{className:'pmap-tip',direction:'top',offset:[0,-12]})
    }

    // Fit to show all points
    if(points.length>1){
      const bounds=L.latLngBounds(points.map(p=>[p.lat,p.lng]))
      bounds.extend(hq)
      map.fitBounds(bounds,{padding:[50,50],maxZoom:4})
    } else if(points.length===1){
      map.setView([points[0].lat,points[0].lng],4)
    }

    return()=>{if(mapInstance.current){mapInstance.current.remove();mapInstance.current=null}}
  },[locations])

  const uniqueCountries=locations.length

  return <div className="pmap-wrap">
    <div ref={containerRef} className="pmap-canvas"/>
    {/* Top-left overlay */}
    <div className="pmap-info">
      <div className="pmap-info-label">Global Network</div>
      <div className="pmap-info-num">{totalLeads}<span>prospects</span></div>
      <div className="pmap-info-sub">{uniqueCountries} countries</div>
    </div>
    {/* Right-side controls */}
    <div className="pmap-controls">
      <button onClick={()=>mapInstance.current?.setZoom(2)} title="Reset view">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" x2="14" y1="3" y2="10"/><line x1="3" x2="10" y1="21" y2="14"/></svg>
      </button>
      <button onClick={()=>mapInstance.current?.zoomIn()} title="Zoom in">+</button>
      <button onClick={()=>mapInstance.current?.zoomOut()} title="Zoom out">&minus;</button>
    </div>
    {/* Bottom-left legend */}
    <div className="pmap-legend">
      <span><i className="pmap-legend-dot"/>Prospect</span>
      <span><i className="pmap-legend-line"/>HQ link</span>
    </div>
  </div>
}

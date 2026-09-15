import React,{useEffect,useRef} from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// Country/region -> approximate center coordinates
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
  // Regions as fallbacks
  'North America':[39.8,-98.6],'Europe':[50.1,9.7],'APAC':[20.0,100.0],
  'Middle East':[25.0,45.0],'Africa':[0.0,25.0],'Latin America':[-15.0,-60.0],
  'Global':[20.0,0.0],'Unassigned':[20.0,0.0],
}

function resolveCoords(country,region){
  if(country&&GEO[country]) return GEO[country]
  if(region&&GEO[region]) return GEO[region]
  // Fuzzy match
  const key=Object.keys(GEO).find(k=>k.toLowerCase()===(country||'').toLowerCase())
  if(key) return GEO[key]
  const rkey=Object.keys(GEO).find(k=>k.toLowerCase()===(region||'').toLowerCase())
  if(rkey) return GEO[rkey]
  return null
}

export default function ProspectMap({locations=[],totalLeads=0}){
  const mapRef=useRef(null)
  const mapInstance=useRef(null)

  useEffect(()=>{
    if(!mapRef.current) return
    if(mapInstance.current){mapInstance.current.remove();mapInstance.current=null}

    const map=L.map(mapRef.current,{
      center:[25,15],zoom:2,minZoom:1,maxZoom:6,
      zoomControl:false,attributionControl:false,
      scrollWheelZoom:true,dragging:true,
    })
    mapInstance.current=map

    // Dark tile layer
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{
      subdomains:'abcd',maxZoom:19
    }).addTo(map)

    // Resolve locations to coordinates
    const points=[]
    for(const loc of locations){
      const coords=resolveCoords(loc.country,loc.region)
      if(coords) points.push({...loc,lat:coords[0],lng:coords[1]})
    }

    // Draw connection lines from HQ (India) to each location
    const hq=[17.4,78.5] // Hyderabad
    points.forEach(p=>{
      if(Math.abs(p.lat-hq[0])>1||Math.abs(p.lng-hq[1])>1){
        L.polyline([hq,[p.lat,p.lng]],{
          color:'#00d4ff',weight:1,opacity:0.25,dashArray:'6,8'
        }).addTo(map)
      }
    })

    // Add glowing markers
    points.forEach(p=>{
      const size=Math.min(12,6+p.leads*2)
      const icon=L.divIcon({
        className:'prospect-map-dot',
        html:`<div style="width:${size}px;height:${size}px;background:#00d4ff;border-radius:50%;box-shadow:0 0 ${size}px 3px rgba(0,212,255,0.7);"></div>`,
        iconSize:[size,size],iconAnchor:[size/2,size/2]
      })
      const marker=L.marker([p.lat,p.lng],{icon}).addTo(map)
      marker.bindTooltip(
        `<strong>${p.country}</strong><br>${p.leads} prospect${p.leads!==1?'s':''}<br>${p.opportunities} opportunit${p.opportunities!==1?'ies':'y'}`,
        {className:'prospect-map-tooltip',direction:'top',offset:[0,-6]}
      )
    })

    // HQ marker (slightly larger, different glow)
    if(points.length>0){
      const hqIcon=L.divIcon({
        className:'prospect-map-dot',
        html:'<div style="width:10px;height:10px;background:#00d4ff;border-radius:50%;box-shadow:0 0 14px 5px rgba(0,212,255,0.9);border:2px solid rgba(255,255,255,0.4);"></div>',
        iconSize:[14,14],iconAnchor:[7,7]
      })
      L.marker(hq,{icon:hqIcon}).addTo(map).bindTooltip('JSAN HQ — Hyderabad',{className:'prospect-map-tooltip',direction:'top',offset:[0,-8]})
    }

    // Fit bounds if we have points
    if(points.length>1){
      const bounds=L.latLngBounds(points.map(p=>[p.lat,p.lng]))
      bounds.extend(hq)
      map.fitBounds(bounds,{padding:[40,40],maxZoom:4})
    }

    return()=>{if(mapInstance.current){mapInstance.current.remove();mapInstance.current=null}}
  },[locations])

  const uniqueCountries=locations.length

  return <div className="prospect-map-wrap">
    <div ref={mapRef} className="prospect-map"/>
    <div className="prospect-map-overlay-tl">
      <div className="prospect-map-label">Prospect Network</div>
      <div className="prospect-map-stat">
        <span className="prospect-map-number">{totalLeads}</span>
        <span className="prospect-map-unit">prospects</span>
      </div>
      <div className="prospect-map-stat-sm">{uniqueCountries} countries</div>
    </div>
    <div className="prospect-map-legend">
      <span><i className="prospect-map-legend-dot"/>Prospect location</span>
      <span><i className="prospect-map-legend-line"/>HQ link</span>
    </div>
  </div>
}

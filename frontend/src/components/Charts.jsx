import React from 'react'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, BarChart, Bar, PieChart, Pie, Cell } from 'recharts'
import { money } from '../lib/format'

const COLORS = ['#0879b9','#12a7a1','#35b6df','#1f5f8d','#77c7c3','#80bfe4','#0f8f8a']
const grid = '#e6eef4'
const axis = { fill:'#6b7f8f', fontSize:11 }
const tooltipStyle = { border:'1px solid #dce8f0', borderRadius:12, boxShadow:'0 12px 32px rgba(19,69,99,.12)' }

export function RevenueTrend({ data=[], currency='USD' }) {
  return <ResponsiveContainer width="100%" height={270}><LineChart data={data} margin={{top:10,right:10,left:0,bottom:0}}><CartesianGrid vertical={false} stroke={grid}/><XAxis dataKey="period" tick={axis} axisLine={false} tickLine={false}/><YAxis tick={axis} axisLine={false} tickLine={false} tickFormatter={v=>money(v,currency)}/><Tooltip contentStyle={tooltipStyle} formatter={(v,n)=>[money(v,currency,false), n==='pipeline'?'Pipeline':'Closed Won']}/><Line type="monotone" dataKey="pipeline" stroke="#0879b9" strokeWidth={3} dot={{r:3,fill:'#0879b9'}}/><Line type="monotone" dataKey="won" stroke="#12a7a1" strokeWidth={3} dot={{r:3,fill:'#12a7a1'}}/></LineChart></ResponsiveContainer>
}
export function ForecastBars({ data=[], currency='USD' }) {
  return <ResponsiveContainer width="100%" height={270}><BarChart data={data} margin={{top:10,right:8,left:0,bottom:0}}><CartesianGrid vertical={false} stroke={grid}/><XAxis dataKey="name" tick={axis} axisLine={false} tickLine={false}/><YAxis tick={axis} axisLine={false} tickLine={false} tickFormatter={v=>money(v,currency)}/><Tooltip contentStyle={tooltipStyle} formatter={v=>money(v,currency,false)}/><Bar dataKey="value" radius={[7,7,0,0]}>{data.map((_,i)=><Cell key={i} fill={COLORS[i%COLORS.length]}/>)}</Bar></BarChart></ResponsiveContainer>
}
export function HorizontalBars({ data=[], dataKey='value', nameKey='name', currency, height=260 }) {
  return <ResponsiveContainer width="100%" height={height}><BarChart data={data} layout="vertical" margin={{top:0,right:16,left:16,bottom:0}}><CartesianGrid horizontal={false} stroke={grid}/><XAxis type="number" tick={axis} axisLine={false} tickLine={false} tickFormatter={v=>currency?money(v,currency):v}/><YAxis type="category" dataKey={nameKey} width={112} tick={axis} axisLine={false} tickLine={false}/><Tooltip contentStyle={tooltipStyle} formatter={v=>currency?money(v,currency,false):v}/><Bar dataKey={dataKey} fill="#0879b9" radius={[0,6,6,0]}/></BarChart></ResponsiveContainer>
}
export function Donut({ data=[], valueKey='count' }) {
  const total=data.reduce((s,x)=>s+Number(x[valueKey]||0),0)
  return <div className="donut-wrap"><ResponsiveContainer width="100%" height={240}><PieChart><Pie data={data} dataKey={valueKey} nameKey="name" innerRadius={68} outerRadius={96} paddingAngle={3}>{data.map((_,i)=><Cell key={i} fill={COLORS[i%COLORS.length]}/>)}</Pie><Tooltip contentStyle={tooltipStyle}/></PieChart></ResponsiveContainer><div className="donut-center"><strong>{total}</strong><span>Total</span></div></div>
}
export function Legend({ items=[] }) { return <div className="chart-legend">{items.map((x,i)=><span key={x.name}><i style={{background:COLORS[i%COLORS.length]}}/>{x.name}<b>{x.count ?? x.value ?? ''}</b></span>)}</div> }

import React,{Suspense,useEffect,useState,lazy} from 'react'
import { AuthProvider,useAuth } from './components/Auth'
import LoginPage from './components/LoginPage'
import AppShell from './components/AppShell'
import { Empty,Spinner,Toast } from './components/UI'
import { useHashRoute,navigate } from './lib/router'

const DashboardPage=lazy(()=>import('./pages/DashboardPage'))
const ProspectsPage=lazy(()=>import('./pages/ProspectsPage'))
const Lead360Page=lazy(()=>import('./pages/Lead360Page'))
const ActionsPage=lazy(()=>import('./pages/ActionsPage'))
const PipelinePage=lazy(()=>import('./pages/PipelinePage'))
const ForecastPage=lazy(()=>import('./pages/ForecastPage'))
const LeadershipPage=lazy(()=>import('./pages/LeadershipPage'))
const AdminPage=lazy(()=>import('./pages/AdminPage'))
// Pages whose data needs a role permission; without it the page explains instead of failing.
const PAGE_PERMS=[['/prospects','LEAD_VIEW'],['/lead/','LEAD_VIEW'],['/pipeline','OPPORTUNITY_VIEW'],['/forecast','FORECAST_VIEW'],['/leadership','REPORT_VIEW'],['/admin','ROLE_ADMIN']]

// Keeps a crash in one page from blanking the whole app; remounts (and so resets) on navigation.
class PageBoundary extends React.Component{
 constructor(props){super(props);this.state={error:null}}
 static getDerivedStateFromError(error){return {error}}
 componentDidCatch(error,info){console.error('Page crashed',error,info?.componentStack)}
 render(){if(!this.state.error)return this.props.children;return <div className="empty-state"><strong>This page ran into a problem</strong><span>{String(this.state.error?.message||this.state.error)}</span><button className="btn btn-primary" onClick={()=>window.location.reload()}><span>Reload</span></button></div>}
}

function Product(){
 const {user,loading,has}=useAuth(); const route=useHashRoute(); const [toast,setToast]=useState(null)
 useEffect(()=>{if(user&&route.path==='/')navigate('dashboard')},[user,route.path])
 useEffect(()=>{const key=e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();document.querySelector('.command-search')?.click()}};window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key)},[])
 if(loading)return <div className="boot-screen"><img src="/jsan-logo.jpg"/><Spinner label="Opening PursuitNova"/></div>
 if(!user)return <LoginPage/>
 let page
 if(route.path==='/dashboard')page=<DashboardPage/>
 else if(route.path==='/prospects')page=<ProspectsPage route={route} onToast={setToast}/>
 else if(route.path.startsWith('/lead/'))page=<Lead360Page id={Number(route.path.split('/')[2])} onToast={setToast}/>
 else if(route.path==='/actions')page=<ActionsPage onToast={setToast}/>
 else if(route.path==='/pipeline')page=<PipelinePage route={route} onToast={setToast}/>
 else if(route.path==='/forecast')page=<ForecastPage onToast={setToast}/>
 else if(route.path==='/leadership')page=<LeadershipPage/>
 else if(route.path==='/admin')page=<AdminPage onToast={setToast}/>
 else page=<DashboardPage/>
 const need=PAGE_PERMS.find(([prefix])=>route.path.startsWith(prefix))?.[1]
 if(need&&!has(need))page=<Empty title="Not available for your role" text="Your role does not include access to this page. Ask your admin to add it to your role."/>
 return <><AppShell route={route}><PageBoundary key={route.path}><Suspense fallback={<Spinner label="Loading workspace"/>}>{page}</Suspense></PageBoundary></AppShell><Toast toast={toast} onClose={()=>setToast(null)}/></>
}
export default function App(){return <AuthProvider><Product/></AuthProvider>}

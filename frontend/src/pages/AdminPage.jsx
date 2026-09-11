import React,{useEffect,useState} from 'react'
import { api } from '../lib/api'
import { useAuth } from '../components/Auth'
import { Button,ErrorBanner,Field,Input,Modal,Pill,SectionHeader,Select,Table } from '../components/UI'

const SCOPES={all:'Entire organisation',team:'Own work + reporting team',self:'Own work only',assigned:'Assigned work only'}
const NEW_USER={name:'',email:'',password:'',role:'',manager_id:'',title:'',region:''}
const NEW_ROLE={name:'',scope_type:'team',rank:'',permissions:[]}
// Everything a typical BD lead needs to work their prospects and pipeline; new roles start from this.
const LEAD_STARTER=['LEAD_VIEW','LEAD_CREATE','LEAD_EDIT','COMPANY_VIEW','COMPANY_EDIT','CONTACT_EDIT','MEETING_EDIT','ACTION_EDIT','OPPORTUNITY_VIEW','OPPORTUNITY_EDIT','FORECAST_VIEW','REPORT_VIEW','DOCUMENT_EDIT']
const PAGE_PERMS=[['LEAD_VIEW','Prospects'],['OPPORTUNITY_VIEW','Opportunity Pipeline'],['FORECAST_VIEW','Forecast'],['REPORT_VIEW','Leadership Analytics']]
const permGrid={display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(230px,1fr))',gap:'8px 16px',marginTop:8}
const permItem={display:'flex',gap:8,alignItems:'flex-start',fontSize:13,lineHeight:1.35}

export default function AdminPage({onToast}){
 const {user,has}=useAuth(); const isSuper=user?.scope_type==='all'
 const [users,setUsers]=useState([]); const [roleData,setRoleData]=useState(null); const [ms,setMs]=useState(null); const [metrics,setMetrics]=useState(null); const [currency,setCurrency]=useState(null); const [error,setError]=useState(null)
 const [userModal,setUserModal]=useState(null); const [userForm,setUserForm]=useState(NEW_USER)
 const [roleModal,setRoleModal]=useState(null); const [roleForm,setRoleForm]=useState(NEW_ROLE)
 const load=async()=>{setError(null);try{const [u,r,m,c]=await Promise.all([has('USER_ADMIN')?api.get('/api/users'):Promise.resolve([]),api.get('/api/admin/roles'),api.get('/api/integrations/microsoft/status'),api.get('/api/admin/currency')]);setUsers(u);setRoleData(r);setMs(m);setCurrency(c);try{setMetrics(await api.get('/api/monitoring/metrics'))}catch{setMetrics(null)}}catch(e){setError(e)}}
 useEffect(()=>{load()},[])
 const roles=roleData?.roles||[]; const assignable=roles.filter(r=>r.assignable)
 const fail=err=>onToast?.({type:'error',message:err.message})
 const setU=(k,v)=>setUserForm(f=>({...f,[k]:v})); const setR=(k,v)=>setRoleForm(f=>({...f,[k]:v}))

 const openNewUser=()=>{setUserForm({...NEW_USER,role:assignable[0]?.name||'',manager_id:user.id});setUserModal('create')}
 const openEditUser=r=>{setUserForm({id:r.id,name:r.name,role:r.role,manager_id:r.manager_id||'',title:r.title||'',region:r.region||'',active:r.active,password:''});setUserModal('edit')}
 const saveUser=async e=>{e.preventDefault();const {id,...f}=userForm;const manager_id=f.manager_id?Number(f.manager_id):null
  try{
   if(userModal==='create'){await api.post('/api/users',{...f,manager_id});onToast?.({message:`${f.name} added`})}
   else{const original=users.find(x=>x.id===id);const payload={manager_id,title:f.title,region:f.region,active:f.active};if(f.role!==original?.role)payload.role=f.role;if(f.password)payload.password=f.password;await api.put(`/api/users/${id}`,payload);onToast?.({message:'User updated'})}
   setUserModal(null);load()
  }catch(err){fail(err)}}

 const grantable=code=>roleData?.grantable?.includes(code)
 const openNewRole=()=>{setRoleForm({...NEW_ROLE,scope_type:roleData?.scopes?.includes('team')?'team':'self',permissions:LEAD_STARTER.filter(grantable)});setRoleModal('create')}
 const copyFrom=id=>{const r=roles.find(x=>String(x.id)===id);if(r)setR('permissions',r.permissions.filter(grantable))}
 const missingPages=PAGE_PERMS.filter(([code])=>!roleForm.permissions.includes(code)).map(([,label])=>label)
 const openEditRole=r=>{setRoleForm({id:r.id,name:r.name,scope_type:r.scope_type,rank:r.rank,permissions:r.permissions});setRoleModal('edit')}
 const togglePerm=code=>setRoleForm(f=>({...f,permissions:f.permissions.includes(code)?f.permissions.filter(x=>x!==code):[...f.permissions,code]}))
 const grantableCodes=(roleData?.permission_catalog||[]).map(p=>p.code).filter(grantable)
 const allSelected=grantableCodes.length>0&&grantableCodes.every(c=>roleForm.permissions.includes(c))
 const someSelected=grantableCodes.some(c=>roleForm.permissions.includes(c))
 const toggleAll=()=>setRoleForm(f=>({...f,permissions:allSelected?f.permissions.filter(c=>!grantable(c)):[...new Set([...f.permissions,...grantableCodes])]}))
 const saveRole=async e=>{e.preventDefault();const {id,...f}=roleForm;const payload={...f,rank:f.rank===''?null:Number(f.rank)}
  try{if(roleModal==='create')await api.post('/api/admin/roles',payload);else await api.put(`/api/admin/roles/${id}`,payload);onToast?.({message:`Role ${f.name} saved`});setRoleModal(null);load()}catch(err){fail(err)}}
 const deleteRole=async r=>{if(!window.confirm(`Delete the ${r.name} role?`))return;try{await api.delete(`/api/admin/roles/${r.id}`);onToast?.({message:`Role ${r.name} deleted`});load()}catch(err){fail(err)}}

 const userCols=[{key:'name',label:'User',render:r=><div className="primary-cell"><strong>{r.name}</strong><span>{r.email}</span></div>},{key:'role',label:'Role'},{key:'title',label:'Title'},{key:'manager_name',label:'Reporting manager',render:r=>r.manager_name||'—'},{key:'region',label:'Region'},{key:'active',label:'Status',render:r=><Pill tone={r.active?'success':'neutral'}>{r.active?'Active':'Inactive'}</Pill>},{key:'edit',label:'',render:r=>(isSuper||r.id!==user.id)&&<Button variant="text" onClick={()=>openEditUser(r)}>Edit</Button>}]
 const roleCols=[{key:'name',label:'Role',render:r=><div className="primary-cell"><strong>{r.name}</strong><span>{r.user_count} {r.user_count===1?'user':'users'}{r.created_by==null?' · shared':''}</span></div>},{key:'scope_type',label:'Can see',render:r=>SCOPES[r.scope_type]||r.scope_type},{key:'rank',label:'Level',align:'right'},{key:'permissions',label:'Permissions',align:'right',render:r=>r.permissions.length},{key:'actions',label:'',render:r=>r.editable?<div style={{display:'flex',gap:4,justifyContent:'flex-end'}}><Button variant="text" onClick={()=>openEditRole(r)}>Edit</Button><Button variant="text" onClick={()=>deleteRole(r)} disabled={r.user_count>0} title={r.user_count>0?'Move its users to another role first':''}>Delete</Button></div>:<Pill>Protected</Pill>}]
 const editedUser=users.find(x=>x.id===userForm.id)
 const roleOptions=editedUser&&!assignable.some(r=>r.name===editedUser.role)?[{name:editedUser.role,locked:true},...assignable]:assignable

 return <><SectionHeader eyebrow="Platform governance" title="Admin Center" text={isSuper?'You can see and manage every organisation, user and role.':'You manage the users and roles in your own organisation. Other admins’ teams are not visible to you.'}/><ErrorBanner error={error} onRetry={load}/>
 <div className="admin-grid"><article className="panel admin-status"><h3>Microsoft 365</h3><Pill tone={ms?.connected?'success':ms?.configured?'warning':'neutral'}>{ms?.connected?'Connected':ms?.configured?'Configured':'Not configured'}</Pill><p>{ms?.connected?`Connected as ${ms.account?.connected_email}`:'Configure Microsoft Graph credentials to enable Outlook, Calendar and Teams sync.'}</p>{ms?.configured&&!ms?.connected&&<Button onClick={()=>window.location.href='/api/integrations/microsoft/connect'}>Connect account</Button>}</article><article className="panel admin-status"><h3>Application health</h3><strong>{metrics?`${metrics.avg_latency_ms} ms`:'Restricted'}</strong><p>{metrics?`${metrics.requests} requests · ${metrics.errors} errors · ${metrics.database}`:'Monitoring metrics require Audit View permission.'}</p></article><article className="panel admin-status"><h3>Corporate currency</h3><strong>{currency?.corporate_currency||'—'}</strong><p>Leadership forecasts normalize original deal values into the corporate reporting currency.</p></article></div>
 {has('USER_ADMIN')&&<section className="panel table-panel"><div className="inline-head"><div><h3>Users & reporting hierarchy</h3><p>A user sees their own work and the work of everyone who reports to them. Peers cannot see each other’s work.</p></div><Button icon="plus" onClick={openNewUser} disabled={!assignable.length}>Add user</Button></div><Table columns={userCols} rows={users}/></section>}
 <section className="panel table-panel"><div className="inline-head"><div><h3>Roles</h3><p>{isSuper?'Shared roles are available to every admin. Roles an admin creates stay inside that admin’s organisation.':'Create roles for your team. Shared roles are maintained by Super Admins.'}</p></div><Button icon="plus" onClick={openNewRole}>New role</Button></div><Table columns={roleCols} rows={roles}/></section>

 <Modal open={!!userModal} onClose={()=>setUserModal(null)} title={userModal==='create'?'Add user':'Update user'} eyebrow={userModal==='edit'?userForm.name:'New team member'}><form onSubmit={saveUser}>
  {userModal==='create'&&<div className="form-grid"><Field label="Full name" required><Input required value={userForm.name} onChange={e=>setU('name',e.target.value)}/></Field><Field label="Work email" required><Input required type="email" value={userForm.email} onChange={e=>setU('email',e.target.value)}/></Field><Field label="Temporary password" required><Input required type="password" minLength={8} value={userForm.password} onChange={e=>setU('password',e.target.value)}/></Field></div>}
  <div className="form-grid"><Field label="Role" required><Select required value={userForm.role} onChange={e=>setU('role',e.target.value)}>{roleOptions.map(r=><option key={r.name} value={r.name} disabled={r.locked}>{r.name}{r.locked?' (current)':''}</option>)}</Select></Field><Field label="Reporting manager" required={!isSuper}><Select value={userForm.manager_id||''} onChange={e=>setU('manager_id',e.target.value)}>{isSuper&&<option value="">No manager</option>}{users.filter(x=>x.id!==userForm.id).map(x=><option key={x.id} value={x.id}>{x.name} · {x.role}</option>)}</Select></Field><Field label="Title"><Input value={userForm.title||''} onChange={e=>setU('title',e.target.value)}/></Field><Field label="Region"><Input value={userForm.region||''} onChange={e=>setU('region',e.target.value)}/></Field>{userModal==='edit'&&<Field label="Status"><Select value={userForm.active?'1':'0'} onChange={e=>setU('active',e.target.value==='1')}><option value="1">Active</option><option value="0">Inactive</option></Select></Field>}{userModal==='edit'&&<Field label="Set new password" hint="Leave empty to keep their current password. Minimum 8 characters."><Input type="password" minLength={8} autoComplete="new-password" value={userForm.password||''} onChange={e=>setU('password',e.target.value)}/></Field>}</div>
  <div className="modal-actions"><Button type="button" variant="ghost" onClick={()=>setUserModal(null)}>Cancel</Button><Button type="submit">{userModal==='create'?'Add user':'Save user'}</Button></div></form></Modal>

 <Modal size="lg" open={!!roleModal} onClose={()=>setRoleModal(null)} title={roleModal==='create'?'New role':'Edit role'} eyebrow={roleModal==='edit'?roleForm.name:'Role design'}><form onSubmit={saveRole}>
  <div className="form-grid"><Field label="Role name" required><Input required value={roleForm.name} onChange={e=>setR('name',e.target.value)} placeholder="e.g. BD Lead"/></Field><Field label="Can see" required hint="Nobody ever sees a peer’s work; “team” adds the people who report to them."><Select value={roleForm.scope_type} onChange={e=>setR('scope_type',e.target.value)}>{(roleData?.scopes||[]).map(s=><option key={s} value={s}>{SCOPES[s]||s}</option>)}</Select></Field><Field label="Level" hint={`Lower number = more senior. Leave empty to place it below existing roles${roleData?.min_rank>1?`; must be ${roleData.min_rank} or higher`:''}.`}><Input type="number" min={roleData?.min_rank||1} value={roleForm.rank??''} onChange={e=>setR('rank',e.target.value)}/></Field></div>
  <div className="form-grid"><Field label="Copy permissions from" hint="Optional: start from an existing role, then adjust below."><Select value="" onChange={e=>copyFrom(e.target.value)}><option value="">Choose a role…</option>{roles.filter(r=>r.id!==roleForm.id).map(r=><option key={r.id} value={r.id}>{r.name}</option>)}</Select></Field></div>
  {missingPages.length>0&&<div className="warning-callout"><strong>Limited access</strong><span>Users with this role will not be able to open: {missingPages.join(', ')}.</span></div>}
  <Field label="Permissions" hint={isSuper?undefined:'You can only grant permissions you hold yourself.'}><div style={permGrid}><label style={{...permItem,gridColumn:'1 / -1',paddingBottom:8,borderBottom:'1px solid rgba(127,127,127,.25)'}}><input type="checkbox" checked={allSelected} ref={el=>{if(el)el.indeterminate=someSelected&&!allSelected}} onChange={toggleAll}/><strong style={{fontWeight:600}}>Select all permissions</strong><small style={{opacity:.7,marginLeft:'auto'}}>{roleForm.permissions.filter(grantable).length} of {grantableCodes.length} selected</small></label>{(roleData?.permission_catalog||[]).map(p=>{const allowed=roleData.grantable.includes(p.code);return <label key={p.code} style={{...permItem,opacity:allowed?1:.45}}><input type="checkbox" disabled={!allowed} checked={roleForm.permissions.includes(p.code)} onChange={()=>togglePerm(p.code)}/><span><strong style={{display:'block',fontWeight:600}}>{p.description}</strong><small style={{opacity:.7}}>{p.code}</small></span></label>})}</div></Field>
  <div className="modal-actions"><Button type="button" variant="ghost" onClick={()=>setRoleModal(null)}>Cancel</Button><Button type="submit">Save role</Button></div></form></Modal></>
}

import React, { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { api, login as apiLogin, logout as apiLogout, refreshCsrf } from '../lib/api'

const AuthContext = createContext(null)
export function AuthProvider({ children }) {
  const [user,setUser]=useState(null); const [loading,setLoading]=useState(true)
  useEffect(()=>{ api.get('/api/auth/me').then(async u=>{setUser(u); try{await refreshCsrf()}catch{}}).catch(()=>setUser(null)).finally(()=>setLoading(false)) },[])
  const value=useMemo(()=>({user,loading,has:(p)=>user?.permissions?.includes(p), async login(email,password,otp){const r=await apiLogin(email,password,otp);setUser(r.user);return r}, async logout(){await apiLogout();setUser(null)}}),[user,loading])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
export function useAuth(){return useContext(AuthContext)}

// src/components/Header.tsx
'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Bell, LogOut, User, AlertCircle, Clock } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import api from '@/lib/api'

export default function Header({ title }: { title: string }) {
  const { user, signOut }  = useAuth()
  const [alerts, setAlerts] = useState<number>(0)
  const [refresh, setRefresh] = useState<string>('')
  const [stale, setStale]     = useState(false)

  useEffect(() => {
    // Fetch active alert count
    api.get('/api/alerts?resolved=false')
      .then(r => setAlerts(r.data.length))
      .catch(() => {})

    // Check last refresh
    api.get('/api/dashboard/summary')
      .then(r => {
        const last = r.data.last_data_refresh
        if (last) {
          const dt  = new Date(last)
          const hrs = (Date.now() - dt.getTime()) / 3600000
          setRefresh(dt.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }))
          setStale(hrs > 26)
        }
      })
      .catch(() => {})
  }, [])

  return (
    <header className="h-24 flex items-center justify-between px-6 sm:px-10 bg-white/90 dark:bg-slate-950/90 backdrop-blur-md sticky top-0 z-30 pt-6">
      <div>
        <h1 className="text-3xl font-bold text-slate-900 dark:text-white tracking-tight">{title}</h1>
        {refresh && (
          <div className={`flex items-center gap-1.5 text-[11px] ${stale ? 'text-amber-400' : 'text-slate-500'}`}>
            <Clock size={10} />
            Last refresh: {refresh}
            {stale && <span className="text-amber-400 font-medium">(stale!)</span>}
          </div>
        )}
      </div>

      {stale && (
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs">
          <AlertCircle size={12} />
          Data may be outdated — check pipeline
        </div>
      )}

      <div className="flex items-center gap-3">
        {/* Alerts bell */}
        <Link href="/alerts" className="relative p-2 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors">
          <Bell size={18} className="text-slate-500 dark:text-slate-400" />
          {alerts > 0 && (
            <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1
                             rounded-full bg-rose-500 text-[10px] font-bold text-white
                             flex items-center justify-center">
              {alerts > 99 ? '99+' : alerts}
            </span>
          )}
        </Link>

        {/* User */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-200/40 dark:border-slate-800/60 shadow-sm transition-all">
          <div className="w-6 h-6 rounded-full bg-emerald-500/20 border border-emerald-500/30
                          flex items-center justify-center">
            <User size={12} className="text-emerald-500 dark:text-emerald-400" />
          </div>
          <div className="hidden sm:block">
            <p className="text-xs font-medium text-slate-900 dark:text-white leading-tight">{user?.email?.split('@')[0]}</p>
            <p className="text-[10px] text-slate-500 leading-tight capitalize">{user?.role?.replace('_', ' ')}</p>
          </div>
        </div>

        {/* Logout */}
        <button
          onClick={signOut}
          className="p-2 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors text-slate-500 hover:text-slate-900 dark:hover:text-white"
          title="Sign out"
        >
          <LogOut size={16} />
        </button>
      </div>
    </header>
  )
}

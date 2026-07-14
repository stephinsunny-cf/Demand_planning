// src/app/admin/page.tsx
'use client'
import { useState, useEffect, useRef } from 'react'
import Layout from '@/components/Layout'
import LoadingSpinner from '@/components/LoadingSpinner'
import api from '@/lib/api'
import { useRole } from '@/hooks/useRole'
import { useRouter } from 'next/navigation'
import {
  Users, Settings, Play, CheckCircle2, XCircle,
  AlertCircle, RefreshCw, Shield, ChevronDown,
} from 'lucide-react'
import { clsx } from 'clsx'

interface PipelineJob {
  job_name:       string
  last_run:       string
  last_completed: string
  status:         string
  rows_processed: number
  error_message:  string
}

export default function AdminPage() {
  const { isAdmin, loading: authLoading }  = useRole()
  const router       = useRouter()
  const [jobs,       setJobs]         = useState<PipelineJob[]>([])
  const [loading,    setLoading]      = useState(true)
  const [triggering, setTriggering]   = useState(false)
  const [thresholds, setThresholds]   = useState({ stockout_alert_pct: 10, low_stock_days: 2, forecast_spike_pct: 50 })
  const [savingTh,   setSavingTh]     = useState(false)

  useEffect(() => {
    if (authLoading) return
    if (!isAdmin) { router.push('/dashboard'); return }
    fetchJobs()
  }, [isAdmin, authLoading])

  const fetchJobs = async () => {
    setLoading(true)
    const [jobsR, thrR] = await Promise.all([
      api.get('/api/admin/pipeline-status').catch(() => ({ data: [] })),
      api.get('/api/admin/thresholds').catch(() => ({ data: {} })),
    ])
    setJobs(jobsR.data)
    setThresholds(prev => ({ ...prev, ...thrR.data }))
    setLoading(false)
  }

  const triggerPipeline = async () => {
    setTriggering(true)
    await api.post('/api/admin/pipeline/trigger').catch(console.error)
    setTimeout(() => { setTriggering(false); fetchJobs() }, 2000)
  }

  const saveThresholds = async () => {
    setSavingTh(true)
    await api.put('/api/admin/thresholds', thresholds).catch(console.error)
    setSavingTh(false)
  }

  const statusIcon = (status: string) => {
    if (status === 'SUCCESS') return <CheckCircle2 size={14} className="text-emerald-400" />
    if (status === 'ERROR')   return <XCircle       size={14} className="text-rose-400" />
    if (status === 'SKIPPED') return <AlertCircle   size={14} className="text-amber-400" />
    return <RefreshCw size={14} className="text-slate-500 dark:text-slate-400" />
  }

  if (authLoading) {
    return <Layout title="Admin Panel"><LoadingSpinner /></Layout>
  }

  if (!isAdmin) return null

  return (
    <Layout title="Admin Panel">
      <div className="space-y-8">
        {/* Pipeline Status */}
        <div className="card p-6 rounded-2xl">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
                <RefreshCw size={18} className="text-emerald-400" />
              </div>
              <h2 className="text-base font-semibold text-slate-900 dark:text-white">Pipeline Status</h2>
            </div>
            <div className="flex items-center gap-3">
              <button onClick={fetchJobs}
                className="p-2 rounded-lg hover:bg-slate-100 dark:bg-slate-800 text-slate-500 hover:text-slate-900 dark:text-white transition-colors">
                <RefreshCw size={14} />
              </button>
              <button onClick={triggerPipeline} disabled={triggering}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400
                           text-slate-900 dark:text-white text-sm font-medium disabled:opacity-50 transition-all">
                <Play size={14} />
                {triggering ? 'Triggering...' : 'Run Pipeline Now'}
              </button>
            </div>
          </div>

          {loading ? <LoadingSpinner /> : (
            <div className="grid gap-3">
              {jobs.length === 0 && (
                <p className="text-slate-500 text-sm text-center py-8">
                  No pipeline runs recorded yet. Run the pipeline to see status here.
                </p>
              )}
              {jobs.map(job => (
                <div key={job.job_name}
                  className="flex items-center justify-between p-4 rounded-xl bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800">
                  <div className="flex items-center gap-3">
                    {statusIcon(job.status)}
                    <div>
                      <p className="text-sm font-medium text-slate-900 dark:text-white">{job.job_name}</p>
                      <p className="text-xs text-slate-500">
                        {job.last_run ? `Last run: ${new Date(job.last_run).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}` : 'Never run'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 text-xs">
                    <div className="text-right">
                      <p className="text-slate-500 dark:text-slate-400">{job.rows_processed?.toLocaleString() || 0} rows</p>
                      <p className={clsx('font-medium', {
                        'text-emerald-400': job.status === 'SUCCESS',
                        'text-rose-400':    job.status === 'ERROR',
                        'text-amber-400':   job.status === 'SKIPPED',
                        'text-slate-500 dark:text-slate-400':   !['SUCCESS','ERROR','SKIPPED'].includes(job.status),
                      })}>{job.status}</p>
                    </div>
                    {job.error_message && (
                      <div className="max-w-xs text-rose-400 text-xs truncate" title={job.error_message}>
                        {job.error_message}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Alert Thresholds */}
        <div className="card p-6 rounded-2xl">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2.5 rounded-xl bg-violet-500/10 border border-violet-500/20">
              <Settings size={18} className="text-violet-400" />
            </div>
            <h2 className="text-base font-semibold text-slate-900 dark:text-white">Alert Thresholds</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[
              { key: 'stockout_alert_pct',  label: 'Stockout Alert (%)',   unit: '%',   min: 1,  max: 50  },
              { key: 'low_stock_days',       label: 'Low Stock Threshold',  unit: 'days', min: 0.5, max: 14 },
              { key: 'forecast_spike_pct',   label: 'Demand Spike Alert',   unit: '%',   min: 10, max: 200 },
            ].map(({ key, label, unit, min, max }) => (
              <div key={key} className="bg-white dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-xl p-4">
                <label className="text-xs text-slate-500 block mb-1">{label}</label>
                <div className="flex items-center gap-2">
                  <input
                    type="number" min={min} max={max} step="0.5"
                    value={thresholds[key as keyof typeof thresholds]}
                    onChange={e => setThresholds(prev => ({ ...prev, [key]: parseFloat(e.target.value) }))}
                    className="flex-1 bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-900 dark:text-white
                               focus:outline-none focus:border-emerald-500"
                  />
                  <span className="text-xs text-slate-500">{unit}</span>
                </div>
              </div>
            ))}
          </div>
          <div className="flex justify-end mt-4">
            <button onClick={saveThresholds} disabled={savingTh}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-violet-500 hover:bg-violet-400
                         text-slate-900 dark:text-white text-sm font-medium disabled:opacity-50 transition-all">
              <Shield size={14} />
              {savingTh ? 'Saving...' : 'Save Thresholds'}
            </button>
          </div>
        </div>

        {/* Users */}
        <UserManagement />
      </div>
    </Layout>
  )
}

function RoleDropdown({ value, onChange, disabled }: { value: string, onChange: (v: string) => void, disabled: boolean }) {
  const [isOpen, setIsOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const options = [
    { label: 'Viewer (Read Only)', value: 'viewer' },
    { label: 'Editor (Write Access)', value: 'editor' },
    { label: 'Super Admin', value: 'super_admin' },
  ]
  const selected = options.find(o => o.value === value)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setIsOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-between gap-2 bg-white border-2 border-cyan-500 rounded-xl px-3 py-1.5 text-sm font-medium text-slate-700 focus:outline-none focus:ring-4 focus:ring-cyan-500/20 transition-all shadow-sm hover:border-cyan-400 disabled:opacity-50 min-w-[160px]"
      >
        <span className="truncate">{selected?.label || 'Select Role'}</span>
        <ChevronDown size={14} className={`text-slate-500 transition-transform flex-shrink-0 ${isOpen ? 'rotate-180' : ''}`} />
      </button>
      {isOpen && (
        <div className="absolute right-0 z-50 mt-2 w-52 bg-white border border-slate-200 rounded-xl shadow-xl overflow-hidden">
          <div className="p-1">
            {options.map(opt => {
              const isSelected = opt.value === value
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => { onChange(opt.value); setIsOpen(false) }}
                  className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors text-left
                    ${isSelected ? 'bg-emerald-500/10 text-emerald-700 font-medium' : 'text-slate-700 hover:bg-slate-50'}`}
                >
                  <div className={`w-4 h-4 rounded-full border flex items-center justify-center flex-shrink-0 transition-colors
                    ${isSelected ? 'bg-emerald-500 border-emerald-500' : 'border-slate-300 bg-white'}`}>
                    {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
                  </div>
                  {opt.label}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

function UserManagement() {
  const [users, setUsers] = useState<Record<string, any>[]>([])
  const [updatingId, setUpdatingId] = useState<string | null>(null)
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviting, setInviting] = useState(false)
  const [inviteMsg, setInviteMsg] = useState('')

  const fetchUsers = () => {
    api.get('/api/admin/users').then(r => setUsers(r.data)).catch(() => {})
  }

  useEffect(() => { fetchUsers() }, [])

  const updateRole = async (userId: string, newRole: string) => {
    setUpdatingId(userId)
    await api.put(`/api/admin/users/${userId}`, { role: newRole }).catch(console.error)
    fetchUsers()
    setUpdatingId(null)
  }

  const inviteUser = async () => {
    if (!inviteEmail) return
    setInviting(true)
    setInviteMsg('')
    try {
      await api.post('/api/admin/users', { email: inviteEmail, role: 'viewer' })
      setInviteMsg(`✓ Invite sent to ${inviteEmail}`)
      setInviteEmail('')
      fetchUsers()
    } catch {
      setInviteMsg('✗ Failed to send invite. Please check the email and try again.')
    }
    setInviting(false)
    setTimeout(() => setInviteMsg(''), 5000)
  }

  return (
    <div className="card p-6 rounded-2xl">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-sky-500/10 border border-sky-500/20">
            <Users size={18} className="text-sky-400" />
          </div>
          <h2 className="text-base font-semibold text-slate-900">Users ({users.length})</h2>
        </div>

        <div className="flex flex-col items-end gap-1">
          <div className="flex items-center gap-2">
            <input
              type="email"
              placeholder="Invite by email..."
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && inviteUser()}
              className="w-52 px-3 py-1.5 text-sm rounded-xl bg-white border-2 border-slate-200 text-slate-900 focus:outline-none focus:border-cyan-500 transition-colors"
            />
            <button
              onClick={inviteUser}
              disabled={inviting || !inviteEmail}
              className="px-4 py-1.5 text-sm font-medium rounded-xl bg-sky-500 hover:bg-sky-400 text-white disabled:opacity-50 transition-colors"
            >
              {inviting ? 'Sending...' : 'Invite'}
            </button>
          </div>
          {inviteMsg && (
            <p className={`text-xs ${inviteMsg.startsWith('✓') ? 'text-emerald-600' : 'text-rose-500'}`}>
              {inviteMsg}
            </p>
          )}
        </div>
      </div>

      <div className="grid gap-2">
        {users.length === 0 && (
          <p className="text-slate-400 text-sm text-center py-8">No users found. Use the Invite button above to add your team!</p>
        )}
        {users.map((u, i) => (
          <div key={String(u.id || i)} className="flex items-center justify-between p-4 rounded-xl bg-white border border-slate-100 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-sky-500/10 border border-sky-500/20 flex items-center justify-center">
                <span className="text-sky-500 text-sm font-bold">
                  {String(u.email || '?').charAt(0).toUpperCase()}
                </span>
              </div>
              <div>
                <p className="text-sm font-medium text-slate-900">{String(u.email)}</p>
                <p className="text-xs text-slate-400">Member since {String(u.created_at || '').slice(0, 10)}</p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <RoleDropdown
                value={String(u.role)}
                onChange={(newRole) => updateRole(String(u.id), newRole)}
                disabled={updatingId === u.id}
              />
              {updatingId === u.id && <RefreshCw size={14} className="animate-spin text-slate-400" />}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

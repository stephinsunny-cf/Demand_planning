// src/app/alerts/page.tsx
'use client'
import { useState, useEffect } from 'react'
import Layout from '@/components/Layout'
import AlertBadge from '@/components/AlertBadge'
import LoadingSpinner from '@/components/LoadingSpinner'
import { useCachedApi } from '@/hooks/useCachedApi'
import { Clock, CheckCircle, RefreshCw, X } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { clsx } from 'clsx'

interface Alert {
  alert_id:   string
  alert_type: string
  severity:   string
  message:    string
  sku:        string
  outlet:     string
  ingredient: string
  created_at: string
  resolved:   number
}

export default function AlertsPage() {
  const [severity, setSeverity] = useState('')
  const [showResolved, setShowResolved] = useState(false)
  
  const params = new URLSearchParams({ resolved: String(showResolved) }).toString()
  const { data: cachedAlerts, loading, error, mutate } = useCachedApi<Alert[]>(`/api/alerts?${params}`)
  const alerts = cachedAlerts || []

  useEffect(() => {
    const interval = setInterval(() => mutate(true), 5 * 60 * 1000)
    return () => clearInterval(interval)
  }, [mutate])

  const resolve = async (alertId: string) => {
    try {
      // dynamic import api because we deleted the standard import
      const api = (await import('@/lib/api')).default
      await api.post(`/api/alerts/${alertId}/resolve`)
      mutate(true)
    } catch (e) {
      console.error(e)
    }
  }

  const severityBorder = (s: string) => ({
    CRITICAL: 'border-l-rose-500',
    WARNING:  'border-l-amber-500',
    INFO:     'border-l-sky-500',
  }[s] || 'border-l-slate-600')

  const counts = { CRITICAL: 0, WARNING: 0, INFO: 0 }
  for (const a of alerts) { if (a.severity in counts) counts[a.severity as keyof typeof counts]++ }

  const filteredAlerts = alerts.filter(a => !severity || a.severity === severity)

  return (
    <Layout title="Alerts">
      {/* Tabs + toggle */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div className="flex gap-1 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-1">
          {[
            { label: 'All',      val: '' },
            { label: `Critical (${counts.CRITICAL})`, val: 'CRITICAL' },
            { label: `Warning (${counts.WARNING})`,   val: 'WARNING'  },
            { label: `Info (${counts.INFO})`,         val: 'INFO'     },
          ].map(({ label, val }) => (
            <button
              key={val}
              onClick={() => setSeverity(val)}
              className={clsx(
                'px-4 py-1.5 rounded-lg text-sm font-medium transition-all',
                severity === val
                  ? 'bg-emerald-500 text-slate-900 dark:text-white shadow-lg shadow-emerald-500/20'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:text-white',
              )}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400 cursor-pointer">
            <input
              type="checkbox"
              checked={showResolved}
              onChange={e => setShowResolved(e.target.checked)}
              className="rounded border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800"
            />
            Show resolved
          </label>
          <button onClick={() => mutate(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-700
                       text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:text-white text-sm border border-slate-300 dark:border-slate-700 transition-all">
            <RefreshCw size={13} />
            Refresh
          </button>
        </div>
      </div>

      {loading ? <LoadingSpinner /> : (
        <div className="space-y-3">
          {filteredAlerts.length === 0 && (
            <div className="card p-16 rounded-2xl text-center">
              <CheckCircle className="w-12 h-12 text-emerald-400 mx-auto mb-3" />
              <p className="text-slate-900 dark:text-white font-medium mb-1">No alerts</p>
              <p className="text-slate-500 text-sm">All systems are healthy</p>
            </div>
          )}

          {filteredAlerts.map(alert => (
            <div
              key={alert.alert_id}
              className={clsx(
                'card p-5 rounded-2xl border-l-4 transition-all',
                severityBorder(alert.severity),
                alert.resolved ? 'opacity-50' : '',
              )}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <AlertBadge severity={alert.severity} />
                    {alert.sku && (
                      <span className="text-xs font-mono bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 px-2 py-0.5 rounded text-slate-500 dark:text-slate-400">
                        {alert.sku}
                      </span>
                    )}
                    {alert.outlet && alert.outlet !== alert.sku && (
                      <span className="text-xs text-slate-500">{alert.outlet}</span>
                    )}
                    {alert.ingredient && alert.ingredient !== alert.sku && (
                      <span className="text-xs font-mono bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 px-2 py-0.5 rounded text-amber-400">
                        {alert.ingredient}
                      </span>
                    )}
                  </div>

                  <p className="text-sm text-slate-700 dark:text-slate-200 leading-relaxed">{alert.message}</p>

                  <div className="flex items-center gap-1.5 mt-2 text-xs text-slate-600">
                    <Clock size={10} />
                    {formatDistanceToNow(new Date(alert.created_at), { addSuffix: true })}
                  </div>
                </div>

                {!alert.resolved && (
                  <button
                    onClick={() => resolve(alert.alert_id)}
                    className="flex-shrink-0 p-2 rounded-lg hover:bg-slate-100 dark:bg-slate-800 text-slate-500 hover:text-emerald-400 transition-all"
                    title="Mark as resolved"
                  >
                    <X size={16} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </Layout>
  )
}

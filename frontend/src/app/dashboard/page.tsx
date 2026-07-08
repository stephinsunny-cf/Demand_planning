// src/app/dashboard/page.tsx
'use client'
import { useState, useEffect } from 'react'
import Layout from '@/components/Layout'
import KPICard from '@/components/KPICard'
import AlertBadge from '@/components/AlertBadge'
import LoadingSpinner from '@/components/LoadingSpinner'
import api from '@/lib/api'
import { ShoppingCart, Bell, AlertTriangle, Target, Clock, CheckCircle2 } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

interface DashboardData {
  total_orders_today:        number
  active_alerts_count:       number
  critical_alerts_count:     number
  skus_at_risk:              number
  forecast_accuracy_percent: number
  last_data_refresh:         string | null
  recent_alerts:             Alert[]
}

interface Alert {
  alert_id:   string
  severity:   string
  message:    string
  sku:        string
  outlet:     string
  created_at: string
  resolved:   number
}

export default function DashboardPage() {
  const [data,    setData]    = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchData = () => {
    api.get('/api/dashboard/summary')
      .then(r => setData(r.data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 5 * 60 * 1000) // refresh every 5 min
    return () => clearInterval(interval)
  }, [])

  const resolveAlert = async (alertId: string) => {
    await api.post(`/api/alerts/${alertId}/resolve`)
    fetchData()
  }

  return (
    <Layout title="Dashboard">
      {loading ? (
        <LoadingSpinner size="lg" />
      ) : (
        <div className="space-y-6">

          {/* KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
            <KPICard
              title="Orders Today"
              value={data?.total_orders_today?.toLocaleString() ?? '—'}
              subtitle="Completed & delivered"
              icon={<ShoppingCart size={18} />}
              color="emerald"
              trend={5}
            />
            <KPICard
              title="Active Alerts"
              value={data?.active_alerts_count ?? 0}
              subtitle={data?.critical_alerts_count ? `${data.critical_alerts_count} critical` : 'All clear'}
              icon={<Bell size={18} />}
              color={data?.critical_alerts_count ? 'rose' : 'amber'}
            />
            <KPICard
              title="SKUs at Risk"
              value={data?.skus_at_risk ?? 0}
              subtitle="May stock out in 3 days"
              icon={<AlertTriangle size={18} />}
              color="amber"
            />
            <KPICard
              title="Forecast Accuracy"
              value={`${data?.forecast_accuracy_percent?.toFixed(1) ?? '—'}%`}
              subtitle="This week's MAPE score"
              icon={<Target size={18} />}
              color="violet"
              trend={2}
            />
          </div>

          {/* Alert Feed */}
          <div className="card rounded-2xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold text-slate-900 dark:text-white">Recent Alerts</h2>
              <span className="text-xs text-slate-500">Auto-refreshes every 5 min</span>
            </div>

            <div className="space-y-2">
              {data?.recent_alerts?.length === 0 && (
                <div className="flex items-center gap-3 py-8 justify-center text-slate-500">
                  <CheckCircle2 size={20} className="text-emerald-400" />
                  No active alerts — all systems healthy
                </div>
              )}
              {data?.recent_alerts?.map((alert) => (
                <div
                  key={alert.alert_id}
                  className="flex items-start gap-3 p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800 shadow-sm dark:shadow-none transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md dark:hover:border-slate-700"
                >
                  {/* Left color bar */}
                  <div className={`w-1 self-stretch rounded-full flex-shrink-0
                    ${alert.severity === 'CRITICAL' ? 'bg-rose-500' :
                      alert.severity === 'WARNING'  ? 'bg-amber-500' : 'bg-sky-500'}`} />

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <AlertBadge severity={alert.severity} />
                      {alert.sku && (
                        <span className="text-xs text-slate-500 font-mono">{alert.sku}</span>
                      )}
                    </div>
                    <p className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed">{alert.message}</p>
                    <div className="flex items-center gap-1.5 mt-1.5 text-xs text-slate-600">
                      <Clock size={10} />
                      {formatDistanceToNow(new Date(alert.created_at), { addSuffix: true })}
                    </div>
                  </div>

                  {alert.resolved === 0 && (
                    <button
                      onClick={() => resolveAlert(alert.alert_id)}
                      className="flex-shrink-0 text-xs px-3 py-1.5 rounded-lg
                                 bg-slate-100 dark:bg-slate-800 hover:bg-slate-700 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:text-white
                                 border border-slate-300 dark:border-slate-700 transition-all"
                    >
                      Resolve
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Quick nav */}
          <div>
            <h2 className="text-sm font-medium text-slate-500 mb-3">Quick Access</h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { href: '/forecast',    label: 'View Forecasts' },
                { href: '/supply',      label: 'Supply Plan' },
                { href: '/warehouse',   label: 'Warehouse Status' },
                { href: '/procurement', label: 'Procurement' },
              ].map(({ href, label }) => (
                <a
                  key={href}
                  href={href}
                  className="flex items-center justify-center py-3 px-4 rounded-xl text-sm font-medium bg-white dark:bg-slate-900 border border-slate-100 dark:border-slate-800 text-slate-600 dark:text-slate-300 shadow-sm dark:shadow-none transition-all duration-200 hover:text-slate-900 dark:hover:text-white hover:bg-slate-50 dark:hover:bg-slate-800 dark:hover:border-slate-700 hover:-translate-y-0.5 hover:shadow-md"
                >
                  {label}
                </a>
              ))}
            </div>
          </div>
        </div>
      )}
    </Layout>
  )
}

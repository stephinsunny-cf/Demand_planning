// src/app/dashboard/page.tsx
'use client'
import { useState, useEffect } from 'react'
import Layout from '@/components/Layout'
import KPICard from '@/components/KPICard'
import AlertBadge from '@/components/AlertBadge'
import LoadingSpinner from '@/components/LoadingSpinner'
import api from '@/lib/api'
import { ShoppingCart, Bell, AlertTriangle, Target, Clock, CheckCircle2, TrendingUp, Package, Truck, AlertCircle } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'

interface DashboardData {
  total_orders_today:        number
  active_alerts_count:       number
  critical_alerts_count:     number
  skus_at_risk:              number
  revenue_at_risk:           number
  forecast_accuracy_percent: number
  last_data_refresh:         string | null
  recent_alerts:             Alert[]
  total_open_pos:            number
  overdue_pos:               number
  top_movers:                { sku: string; total_qty: number }[]
  warehouse_sufficiency_pct: number
  vendor_performance:        { vendor: string; total_pos: number; overdue_pos: number; delay_rate_pct: number }[]
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
        <LoadingSpinner />
      ) : (
        <div className="space-y-6">

          {/* KPI Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">
            <KPICard
              title="Items Sold Today"
              value={data?.total_orders_today?.toLocaleString() ?? '—'}
              subtitle="Completed & delivered"
              icon={<ShoppingCart size={18} />}
              color="emerald"
              trend={5}
            />
            <KPICard
              title="Total Open POs"
              value={data?.total_open_pos ?? 0}
              subtitle={data?.overdue_pos ? `${data.overdue_pos} POs overdue` : 'No overdue POs'}
              icon={<Truck size={18} />}
              color={data?.overdue_pos ? 'rose' : 'emerald'}
            />
            <KPICard
              title="Active Alerts"
              value={data?.active_alerts_count ?? 0}
              subtitle={data?.critical_alerts_count ? `${data.critical_alerts_count} critical` : 'All clear'}
              icon={<Bell size={18} />}
              color={data?.critical_alerts_count ? 'rose' : 'amber'}
            />
            <KPICard
              title="Revenue at Risk"
              value={`₹${(data?.revenue_at_risk ?? 0).toLocaleString(undefined, {maximumFractionDigits: 0})}`}
              subtitle={`${data?.skus_at_risk ?? 0} SKUs (Est. @ 33% Food Cost)`}
              icon={<AlertTriangle size={18} />}
              color="rose"
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

          {/* Operational Pulse Row */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Top Moving SKUs */}
            <div className="card rounded-2xl p-6 flex flex-col">
              <h2 className="text-base font-semibold text-slate-900 dark:text-white flex items-center gap-2 mb-4">
                <TrendingUp size={18} className="text-emerald-500" />
                Top Moving SKUs
              </h2>
              <div className="space-y-3 flex-1">
                {data?.top_movers?.length ? (
                  data.top_movers.map((mover, i) => (
                    <div key={mover.sku} className="flex items-center justify-between p-2 hover:bg-slate-50 dark:hover:bg-slate-800/50 rounded-lg transition-colors">
                      <div className="flex items-center gap-3">
                        <span className="text-xs font-bold text-slate-400 w-4">{i + 1}.</span>
                        <span className="text-sm font-medium text-slate-700 dark:text-slate-300 font-mono">{mover.sku}</span>
                      </div>
                      <span className="text-sm font-semibold text-slate-900 dark:text-white">
                        {mover.total_qty.toLocaleString()}
                      </span>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-slate-500 text-center py-4">No sales data in last 48h</p>
                )}
              </div>
            </div>

            {/* Warehouse Transfer Status */}
            <div className="card rounded-2xl p-6 flex flex-col justify-center">
              <h2 className="text-base font-semibold text-slate-900 dark:text-white flex items-center gap-2 mb-2">
                <Package size={18} className="text-indigo-500" />
                Warehouse Sufficiency
              </h2>
              <p className="text-xs text-slate-500 mb-6">Shortages resolved via internal transfer</p>
              
              <div className="relative pt-1">
                <div className="flex mb-2 items-center justify-between">
                  <div>
                    <span className="text-xs font-semibold inline-block py-1 px-2 uppercase rounded-full text-indigo-600 bg-indigo-200">
                      Internal Cover
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-xs font-semibold inline-block text-indigo-600">
                      {(data?.warehouse_sufficiency_pct ?? 0).toFixed(1)}%
                    </span>
                  </div>
                </div>
                <div className="overflow-hidden h-2 mb-4 text-xs flex rounded bg-indigo-100">
                  <div style={{ width: `${Math.min(100, data?.warehouse_sufficiency_pct ?? 0)}%` }} className="shadow-none flex flex-col text-center whitespace-nowrap text-white justify-center bg-indigo-500"></div>
                </div>
              </div>
            </div>

            {/* Vendor Performance */}
            <div className="card rounded-2xl p-6 flex flex-col">
              <h2 className="text-base font-semibold text-slate-900 dark:text-white flex items-center gap-2 mb-4">
                <AlertCircle size={18} className="text-rose-500" />
                Vendor Delays
              </h2>
              <div className="space-y-3 flex-1">
                {data?.vendor_performance?.length ? (
                  <>
                    {data.vendor_performance.map((vp) => (
                      <div key={vp.vendor} className="flex flex-col p-2 hover:bg-slate-50 dark:hover:bg-slate-800/50 rounded-lg transition-colors">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm font-medium text-slate-700 dark:text-slate-300 truncate pr-2">{vp.vendor}</span>
                          <span className="text-xs font-bold text-rose-500 bg-rose-50 dark:bg-rose-500/10 px-2 py-0.5 rounded">
                            {vp.delay_rate_pct.toFixed(0)}% delay rate
                          </span>
                        </div>
                        <span className="text-xs text-slate-500">
                          {vp.overdue_pos} overdue out of {vp.total_pos} open POs
                        </span>
                      </div>
                    ))}
                    {data.vendor_performance.length < 3 && (
                      <p className="text-xs text-slate-400 text-center mt-4 pt-2 border-t border-slate-100 dark:border-slate-800">
                        Other vendors do not meet volume criteria
                      </p>
                    )}
                  </>
                ) : (
                  <p className="text-sm text-slate-500 text-center py-4">No vendor delays tracked</p>
                )}
              </div>
            </div>
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

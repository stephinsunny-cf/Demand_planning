// src/app/sales/page.tsx
'use client'
import { useState, useEffect } from 'react'
import Layout from '@/components/Layout'
import KPICard from '@/components/KPICard'
import DatePicker from '@/components/DatePicker'
import DataTable from '@/components/DataTable'
import ExportButton from '@/components/ExportButton'
import LoadingSpinner from '@/components/LoadingSpinner'
import api from '@/lib/api'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { IndianRupee, Package, ShoppingBag, Layers } from 'lucide-react'

export default function SalesPage() {
  const [summary,   setSummary]   = useState<Record<string, unknown>>({})
  const [rows,      setRows]      = useState<Record<string, unknown>[]>([])
  const [trend,     setTrend]     = useState<Record<string, unknown>[]>([])
  const [loading,   setLoading]   = useState(true)
  const [startDate, setStartDate] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() - 30); return d.toISOString().slice(0, 10)
  })
  const [endDate, setEndDate]   = useState(new Date().toISOString().slice(0, 10))
  const [brand,   setBrand]     = useState('')
  const [sku,     setSku]       = useState('')

  const fetchData = async () => {
    setLoading(true)
    const params = new URLSearchParams({
      start_date: startDate,
      end_date:   endDate,
      ...(brand && { brand }),
      ...(sku   && { sku   }),
    })
    const [summaryResp, rowsResp] = await Promise.all([
      api.get(`/api/sales/summary?${params}`).catch(() => ({ data: {} })),
      api.get(`/api/sales?${params}`).catch(() => ({ data: [] })),
    ])
    setSummary(summaryResp.data)
    setRows(rowsResp.data)

    // Aggregate daily trend for chart
    const byDate: Record<string, { qty: number; rev: number }> = {}
    for (const r of rowsResp.data as Record<string, unknown>[]) {
      const d = String(r.date)
      if (!byDate[d]) byDate[d] = { qty: 0, rev: 0 }
      byDate[d].qty += Number(r.qty_sold)
      byDate[d].rev += Number(r.revenue)
    }
    setTrend(Object.entries(byDate).sort(([a], [b]) => a.localeCompare(b)).map(([date, v]) => ({
      date, qty: Math.round(v.qty), revenue: Math.round(v.rev)
    })))
    setLoading(false)
  }

  useEffect(() => { fetchData() }, [])

  const columns = [
    { key: 'outlet',      label: 'Outlet',      sortable: true },
    { key: 'brand',       label: 'Brand',       sortable: true },
    { key: 'sku',         label: 'SKU',         sortable: true },
    { key: 'order_count', label: 'Orders',      sortable: true },
    { key: 'qty_sold',    label: 'Qty Sold',    sortable: true, render: (v: unknown) => Number(v).toFixed(0) },
    { key: 'revenue',     label: 'Revenue (₹)', sortable: true, render: (v: unknown) => `₹${Number(v).toLocaleString('en-IN')}` },
  ]

  return (
    <Layout title="Sales Analytics">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-6 card p-4 rounded-xl relative z-40">
        <DatePicker label="From" value={startDate} onChange={setStartDate} />
        <DatePicker label="To" value={endDate} onChange={setEndDate} />
        <div className="flex flex-col gap-1.5">
           <label className="text-xs font-medium text-slate-500">Brand</label>
           <input placeholder="Search..." value={brand} onChange={e => setBrand(e.target.value)}
             className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-200 placeholder-slate-600 focus:outline-none focus:border-emerald-500 w-32" />
        </div>
        <div className="flex flex-col gap-1.5">
           <label className="text-xs font-medium text-slate-500">SKU</label>
           <input placeholder="Search..." value={sku} onChange={e => setSku(e.target.value)}
             className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-200 placeholder-slate-600 focus:outline-none focus:border-emerald-500 w-36" />
        </div>
        <div className="flex flex-col gap-1.5 self-end">
           <button onClick={fetchData}
             className="px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-white text-sm font-medium transition-colors h-9">
             Apply
           </button>
        </div>
        <div className="ml-auto self-end h-9 flex items-center"><ExportButton data={rows} filename="sales" sheetName="Sales Data" /></div>
      </div>

      {loading ? <LoadingSpinner /> : (
        <div className="space-y-6">
          {/* Summary cards */}
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
            <KPICard title="Total Revenue"  value={`₹${Number(summary.total_revenue || 0).toLocaleString('en-IN')}`} icon={<IndianRupee size={18} />} color="emerald" />
            <KPICard title="Total Orders"   value={Number(summary.total_orders || 0).toLocaleString()} icon={<ShoppingBag size={18} />} color="sky" />
            <KPICard title="Avg Order Value" value={`₹${Number(summary.avg_order_value || 0).toLocaleString('en-IN')}`} icon={<IndianRupee size={18} />} color="violet" />
            <KPICard title="Unique SKUs"    value={summary.unique_skus as number || 0} icon={<Layers size={18} />} color="amber" />
          </div>

          {/* Charts */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            {/* Sales trend */}
            <div className="card p-6 rounded-2xl">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-4">Daily Sales Trend</h3>
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={trend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 11 }} tickFormatter={v => v.slice(5)} />
                  <YAxis tick={{ fill: '#64748b', fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }}
                    labelStyle={{ color: '#94a3b8' }}
                  />
                  <Legend />
                  <Line type="monotone" dataKey="qty" stroke="#34d399" strokeWidth={2} dot={false} name="Qty Sold" />
                  <Line type="monotone" dataKey="revenue" stroke="#818cf8" strokeWidth={2} dot={false} name="Revenue ₹" />
                </LineChart>
              </ResponsiveContainer>
            </div>

            {/* Top SKUs */}
            <div className="card p-6 rounded-2xl">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-4">Top 10 SKUs by Volume</h3>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={(summary.top_skus as Record<string, unknown>[] || []).slice(0, 10)} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                  <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} />
                  <YAxis dataKey="sku" type="category" tick={{ fill: '#94a3b8', fontSize: 11 }} width={120} />
                  <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }} />
                  <Bar dataKey="total_qty" fill="#34d399" radius={[0, 4, 4, 0]} name="Qty Sold" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Table */}
          <div className="card p-6 rounded-2xl">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-4">Sales Detail ({rows.length} rows)</h3>
            <DataTable columns={columns} data={rows} searchKeys={['sku', 'outlet', 'brand', 'city']} />
          </div>
        </div>
      )}
    </Layout>
  )
}

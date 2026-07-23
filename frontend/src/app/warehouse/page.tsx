// src/app/warehouse/page.tsx
'use client'
import { useState, useEffect } from 'react'
import Layout from '@/components/Layout'
import DataTable from '@/components/DataTable'
import StatusPill from '@/components/StatusPill'
import ExportButton from '@/components/ExportButton'
import LoadingSpinner from '@/components/LoadingSpinner'
import { useCachedApi } from '@/hooks/useCachedApi'
import { Package, AlertTriangle, CheckCircle, Clock } from 'lucide-react'

export default function WarehousePage() {
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  
  const params = new URLSearchParams({ ...(status && { status }) }).toString()
  const { data: cachedRows, loading, error, mutate } = useCachedApi<Record<string, unknown>[]>(`/api/warehouse?${params}`)
  const rows = cachedRows || []

  const counts = {
    total:  rows.length,
    RED:    rows.filter(r => r.status === 'RED').length,
    YELLOW: rows.filter(r => r.status === 'YELLOW').length,
    GREEN:  rows.filter(r => r.status === 'GREEN').length,
  }

  const filtered = search
    ? rows.filter(r => String(r.ingredient).toLowerCase().includes(search.toLowerCase()))
    : rows

  const columns = [
    { key: 'ingredient',       label: 'Ingredient',       sortable: true },
    { key: 'unit',             label: 'Unit',             sortable: false },
    { key: 'total_qty_needed', label: 'Demand (3 days)',  sortable: true, render: (v: unknown) => Number(v).toLocaleString() },
    { key: 'warehouse_stock',  label: 'Warehouse Stock',  sortable: true, render: (v: unknown) => Number(v).toLocaleString() },
    { key: 'net_requirement',  label: 'Net Requirement',  sortable: true, render: (v: unknown) => {
      const n = Number(v)
      return <span className={n > 0 ? 'text-rose-400 font-medium' : 'text-slate-500 dark:text-slate-400'}>{n > 0 ? `+${n.toLocaleString()}` : n.toLocaleString()}</span>
    }},
    { key: 'status', label: 'Status', sortable: true, render: (v: unknown) => <StatusPill status={String(v)} /> },
  ]

  return (
    <Layout title="Warehouse View">
      {/* Summary Cards */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
        {[
          { label: 'Total Ingredients', value: counts.total,  icon: Package,      color: 'sky',     s: '' },
          { label: 'In Shortage',        value: counts.RED,   icon: AlertTriangle, color: 'rose',    s: 'RED' },
          { label: 'Low Stock',          value: counts.YELLOW,icon: Clock,         color: 'amber',   s: 'YELLOW' },
          { label: 'Sufficient',         value: counts.GREEN, icon: CheckCircle,   color: 'emerald', s: 'GREEN' },
        ].map(({ label, value, icon: Icon, color, s }) => (
          <button key={s}
            onClick={() => { setStatus(status === s ? '' : s); mutate(true) }}
            className={`flex items-center gap-4 p-4 rounded-2xl border transition-all hover:scale-[1.02] text-left
              bg-${color}-500/10 border-${color}-500/20`}>
            <Icon size={22} className={`text-${color}-400`} />
            <div>
              <p className={`text-2xl font-bold text-${color}-400`}>{value}</p>
              <p className="text-xs text-slate-500">{label}</p>
            </div>
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 mb-4 card p-4 rounded-xl">
        <input placeholder="Search ingredient..." value={search} onChange={e => setSearch(e.target.value)}
          className="bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-900 dark:text-white
                     placeholder-slate-600 focus:outline-none focus:border-emerald-500 w-48" />
        <div className="flex rounded-lg overflow-hidden border border-slate-300 dark:border-slate-700">
          {['', 'RED', 'YELLOW', 'GREEN'].map(s => (
            <button key={s || 'ALL'} onClick={() => { setStatus(s); mutate(true) }}
              className={`px-3 py-1.5 text-xs font-medium transition-colors
                ${status === s ? 'bg-emerald-500 text-slate-900 dark:text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-700'}`}>
              {s || 'ALL'}
            </button>
          ))}
        </div>
        <div className="ml-auto">
          <ExportButton data={filtered} filename="warehouse_report" sheetName="Warehouse" />
        </div>
      </div>

      <div className="card p-6 rounded-2xl">
        {loading ? <LoadingSpinner /> : (
          <DataTable columns={columns} data={filtered} searchable={false} />
        )}
      </div>
    </Layout>
  )
}

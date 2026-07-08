// src/app/supply/page.tsx
'use client'
import { useState, useEffect } from 'react'
import Layout from '@/components/Layout'
import DataTable from '@/components/DataTable'
import StatusPill from '@/components/StatusPill'
import ExportButton from '@/components/ExportButton'
import LoadingSpinner from '@/components/LoadingSpinner'
import api from '@/lib/api'
import { Truck, AlertTriangle, CheckCircle, Clock } from 'lucide-react'

export default function SupplyPage() {
  const [allRows,  setAllRows] = useState<Record<string, unknown>[]>([])
  const [loading,  setLoading] = useState(true)
  const [kitchen,  setKitchen] = useState('')
  const [status,   setStatus]  = useState('')
  const [kitchens, setKitchens]= useState<string[]>([])

  const fetchData = async () => {
    setLoading(true)
    const r = await api.get(`/api/supply`).catch(() => ({ data: [] }))
    const data = r.data as Record<string, unknown>[]
    setAllRows(data)
    setKitchens([...new Set(data.map(d => String(d.kitchen)))].sort())
    setLoading(false)
  }

  useEffect(() => { fetchData() }, [])

  const counts = {
    RED:    allRows.filter(r => r.status === 'RED').length,
    YELLOW: allRows.filter(r => r.status === 'YELLOW').length,
    GREEN:  allRows.filter(r => r.status === 'GREEN').length,
  }

  const filteredRows = allRows.filter(r => {
    if (kitchen && r.kitchen !== kitchen) return false
    if (status && r.status !== status) return false
    return true
  })

  const columns = [
    { key: 'sku',                  label: 'SKU',                sortable: true },
    { key: 'kitchen',              label: 'Kitchen',            sortable: true },
    { key: 'forecast_3day',        label: '3-Day Forecast',     sortable: true, render: (v: unknown) => Number(v).toFixed(1) },
    { key: 'stock_qty',            label: 'Current Stock',      sortable: true, render: (v: unknown) => Number(v).toFixed(1) },
    { key: 'safety_stock_qty',     label: 'Safety Stock',       sortable: true, render: (v: unknown) => Number(v).toFixed(1) },
    { key: 'replenishment_needed', label: 'Replenishment',      sortable: true, render: (v: unknown) => Number(v).toFixed(1) },
    { key: 'status',               label: 'Status',             sortable: true, render: (v: unknown) => <StatusPill status={String(v)} /> },
  ]

  return (
    <Layout title="Supply Planning">
      <div className="grid grid-cols-3 gap-4 mb-6">
        {[
          { 
            label: 'Urgent (RED)',   
            value: counts.RED,    
            icon: AlertTriangle, 
            status: 'RED',
            bg: 'bg-rose-500/10', border: 'border-rose-500/20', hoverBorder: 'hover:border-rose-500/40', ring: 'ring-rose-500/40', text: 'text-rose-500'
          },
          { 
            label: 'Low (YELLOW)',   
            value: counts.YELLOW, 
            icon: Clock,         
            status: 'YELLOW',
            bg: 'bg-amber-500/10', border: 'border-amber-500/20', hoverBorder: 'hover:border-amber-500/40', ring: 'ring-amber-500/40', text: 'text-amber-500'
          },
          { 
            label: 'Sufficient',     
            value: counts.GREEN,  
            icon: CheckCircle,   
            status: 'GREEN',
            bg: 'bg-emerald-500/10', border: 'border-emerald-500/20', hoverBorder: 'hover:border-emerald-500/40', ring: 'ring-emerald-500/40', text: 'text-emerald-500'
          },
        ].map(({ label, value, icon: Icon, status: s, bg, border, hoverBorder, ring, text }) => (
          <button
            key={s}
            onClick={() => setStatus(status === s ? '' : s)}
            className={`flex items-center gap-4 p-4 rounded-2xl border transition-all hover:scale-[1.02] text-left
              ${bg} ${border} ${hoverBorder}
              ${status === s ? `ring-1 ${ring}` : ''}`}
          >
            <Icon size={24} className={text} />
            <div>
              <p className={`text-2xl font-bold ${text}`}>{value}</p>
              <p className="text-xs text-slate-500">{label}</p>
            </div>
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-4 card p-4 rounded-xl">
        <select value={kitchen} onChange={e => setKitchen(e.target.value)}
          className="bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-900 dark:text-white
                     focus:outline-none focus:border-emerald-500">
          <option value="">All Kitchens</option>
          {kitchens.map(k => <option key={k} value={k}>{k}</option>)}
        </select>

        <div className="flex rounded-lg overflow-hidden border border-slate-300 dark:border-slate-700">
          {['', 'RED', 'YELLOW', 'GREEN'].map(s => (
            <button key={s || 'ALL'} onClick={() => setStatus(s)}
              className={`px-3 py-1.5 text-xs font-medium transition-colors
                ${status === s ? 'bg-emerald-500 text-slate-900 dark:text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-700'}`}>
              {s || 'ALL'}
            </button>
          ))}
        </div>

        <div className="ml-auto">
          <ExportButton data={filteredRows} filename="supply_plan" sheetName="Supply Plan" />
        </div>
      </div>

      {/* Table */}
      <div className="card p-6 rounded-2xl">
        {loading ? <LoadingSpinner /> : (
          <DataTable columns={columns} data={filteredRows} searchKeys={['sku', 'kitchen']} />
        )}
      </div>
    </Layout>
  )
}

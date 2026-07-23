// src/app/sales/page.tsx
'use client'
import { useState, useEffect } from 'react'
import Layout from '@/components/Layout'
import KPICard from '@/components/KPICard'
import DatePicker from '@/components/DatePicker'
import DataTable from '@/components/DataTable'
import ExportButton from '@/components/ExportButton'
import LoadingSpinner from '@/components/LoadingSpinner'
import { useCachedApi } from '@/hooks/useCachedApi'
import { IndianRupee, ShoppingBag, Layers, Activity, AlertTriangle } from 'lucide-react'

export default function SalesPage() {
  const [tab, setTab] = useState<'consumption' | 'pos'>('consumption')
  const [startDate, setStartDate] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() - 30); return d.toISOString().slice(0, 10)
  })
  const [endDate, setEndDate] = useState(new Date().toISOString().slice(0, 10))
  const [brand, setBrand] = useState('')
  const [sku, setSku] = useState('')

  const params = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
    ...(brand && { brand }),
    ...(sku && { sku }),
  }).toString()
  
  const endpointPrefix = tab === 'pos' ? '/api/sales/pos' : '/api/sales'
  
  const { data: summaryData, loading: summaryLoading, error: summaryError, mutate: mutateSummary } = useCachedApi<Record<string, unknown>>(`${endpointPrefix}/summary?${params}`)
  const { data: rowsData, loading: rowsLoading, error: rowsError, mutate: mutateRows } = useCachedApi<Record<string, unknown>[]>(`${endpointPrefix}?${params}`)

  const handleApply = () => {
    mutateSummary(true)
    mutateRows(true)
  }

  const loading = summaryLoading || rowsLoading
  const error = summaryError || rowsError
  const summary = summaryData || {}
  const rows = rowsData || []

  const posColumns = [
    { key: 'outlet', label: 'Outlet', sortable: true },
    { key: 'brand', label: 'Brand', sortable: true },
    { key: 'sku', label: 'Dish / SKU', sortable: true },
    { key: 'order_count', label: 'Orders', sortable: true },
    { key: 'qty_sold', label: 'Qty Sold', sortable: true, render: (v: unknown) => Number(v).toFixed(0) },
    { key: 'revenue', label: 'Revenue (₹)', sortable: true, render: (v: unknown) => `₹${Number(v).toLocaleString('en-IN')}` },
  ]

  const consumptionColumns = [
    { key: 'outlet', label: 'Kitchen Outlet', sortable: true },
    { key: 'brand', label: 'Brand', sortable: true },
    { key: 'sku', label: 'Raw Ingredient', sortable: true },
    { key: 'order_count', label: 'Usage Frequency', sortable: true },
    { key: 'qty_sold', label: 'Qty Consumed', sortable: true, render: (v: unknown) => Number(v).toFixed(2) },
    { key: 'revenue', label: 'Cost Value (₹)', sortable: true, render: (v: unknown) => `₹${Number(v).toLocaleString('en-IN')}` },
  ]

  return (
    <Layout title="Sales Analytics">
      {/* Tab Switcher */}
      <div className="flex gap-4 mb-6 border-b border-slate-200 dark:border-slate-800 pb-2">
        <button
          onClick={() => setTab('consumption')}
          className={`pb-2 px-1 font-medium transition-colors ${tab === 'consumption' ? 'text-emerald-500 border-b-2 border-emerald-500' : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}
        >
          Kitchen Consumption (SupplyNote)
        </button>
        <button
          onClick={() => setTab('pos')}
          className={`pb-2 px-1 font-medium transition-colors ${tab === 'pos' ? 'text-emerald-500 border-b-2 border-emerald-500' : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}
        >
          Dish Sales (UrbanPiper)
        </button>
      </div>

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
           <label className="text-xs font-medium text-slate-500">{tab === 'pos' ? 'Dish Name' : 'Ingredient'}</label>
           <input placeholder="Search..." value={sku} onChange={e => setSku(e.target.value)}
             className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-200 placeholder-slate-600 focus:outline-none focus:border-emerald-500 w-36" />
        </div>
        <div className="flex flex-col gap-1.5 self-end">
           <button onClick={handleApply}
             className="px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-white text-sm font-medium transition-colors h-9">
             Apply
           </button>
        </div>
        <div className="ml-auto self-end h-9 flex items-center">
          <ExportButton data={rows} filename={`sales_${tab}`} sheetName={`${tab} Data`} />
        </div>
      </div>

      {error ? (
        <div className="flex flex-col items-center justify-center py-20 px-4 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400 shadow-sm">
          <AlertTriangle size={40} className="mb-4 text-rose-500" />
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">Couldn't load sales data</h2>
          <p className="text-sm text-center max-w-md">
            The server encountered an unexpected error while retrieving this data. Please try adjusting your filters or contact support if the issue persists.
          </p>
          <button 
            onClick={() => window.location.reload()}
            className="mt-6 px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg text-sm font-medium transition-colors"
          >
            Refresh Page
          </button>
        </div>
      ) : loading ? <LoadingSpinner /> : (
        <div className="space-y-6">
          {/* Summary cards - dynamic based on tab */}
          {tab === 'pos' ? (
            <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
              <KPICard title="Total POS Revenue" value={`₹${Number(summary.total_revenue || 0).toLocaleString('en-IN')}`} icon={<IndianRupee size={18} />} color="emerald" />
              <KPICard title="Total POS Orders" value={Number(summary.total_orders || 0).toLocaleString()} icon={<ShoppingBag size={18} />} color="sky" />
              <KPICard title="Avg Order Value" value={`₹${Number(summary.avg_order_value || 0).toLocaleString('en-IN')}`} icon={<IndianRupee size={18} />} color="violet" />
              <KPICard title="Unique Dishes Sold" value={summary.unique_skus as number || 0} icon={<Layers size={18} />} color="amber" />
            </div>
          ) : (
            <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
              <KPICard title="Ingredient Cost Value" value={`₹${Number(summary.total_revenue || 0).toLocaleString('en-IN')}`} icon={<IndianRupee size={18} />} color="rose" />
              <KPICard title="Total Consumption Events" value={Number(summary.total_orders || 0).toLocaleString()} icon={<Activity size={18} />} color="orange" />
              <KPICard title="Avg Ingredient Cost" value={`₹${Number(summary.avg_order_value || 0).toLocaleString('en-IN')}`} icon={<IndianRupee size={18} />} color="violet" />
              <KPICard title="Unique Ingredients Used" value={summary.unique_skus as number || 0} icon={<Layers size={18} />} color="amber" />
            </div>
          )}

          {/* Table */}
          <div className="card p-6 rounded-2xl">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-4">
              {tab === 'pos' ? 'POS Dish Sales Detail' : 'Kitchen Ingredient Consumption Detail'} ({rows.length} rows)
            </h3>
            <DataTable columns={tab === 'pos' ? posColumns : consumptionColumns} data={rows} searchKeys={['sku', 'outlet', 'brand', 'city']} />
          </div>
        </div>
      )}
    </Layout>
  )
}

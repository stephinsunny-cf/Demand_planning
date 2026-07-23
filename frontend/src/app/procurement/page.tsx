// src/app/procurement/page.tsx
'use client'
import { useState, useEffect } from 'react'
import Layout from '@/components/Layout'
import ExportButton from '@/components/ExportButton'
import LoadingSpinner from '@/components/LoadingSpinner'
import api from '@/lib/api'
import { getCached, setCached } from '@/lib/pageCache'
import { useCachedApi } from '@/hooks/useCachedApi'
import { ShoppingCart, Zap, IndianRupee, Users } from 'lucide-react'
import { clsx } from 'clsx'

interface ProcRow {
  vendor_name:      string
  ingredient:       string
  net_requirement:  number
  po_qty:           number
  recommended_qty:  number
  moq:              number
  unit:             string
  price:            number
  estimated_cost:   number
  urgency:          string
  expected_delivery: string
}

export default function ProcurementPage() {
  const [urgency, setUrgency]= useState('')
  const params = new URLSearchParams({ ...(urgency && { urgency }) }).toString()
  const { data: cachedRows, loading, error, mutate } = useCachedApi<ProcRow[]>(`/api/procurement?${params}`)
  const rows = cachedRows || []

  const markOrdered = async (ingredient: string) => {
    await api.post(`/api/procurement/${encodeURIComponent(ingredient)}/mark_ordered`)
    mutate(true)
  }

  // Group by vendor
  const grouped: Record<string, ProcRow[]> = {}
  for (const r of rows) {
    if (!grouped[r.vendor_name]) grouped[r.vendor_name] = []
    grouped[r.vendor_name].push(r)
  }

  const totalValue  = rows.reduce((s, r) => s + (r.estimated_cost || 0), 0)
  const urgentCount = rows.filter(r => r.urgency === 'URGENT').length

  return (
    <Layout title="Procurement Recommendations">
      {/* Summary */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {[
          { label: 'Vendors',        value: Object.keys(grouped).length, icon: Users,        color: 'sky'   },
          { label: 'URGENT Items',   value: urgentCount,                 icon: Zap,          color: 'rose'  },
          { label: 'Total Est. Value', value: `₹${totalValue.toLocaleString('en-IN')}`, icon: IndianRupee, color: 'emerald' },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className={`flex items-center gap-4 p-4 rounded-2xl border bg-${color}-500/10 border-${color}-500/20`}>
            <Icon size={22} className={`text-${color}-400`} />
            <div>
              <p className={`text-2xl font-bold text-${color}-400`}>{value}</p>
              <p className="text-xs text-slate-500">{label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 mb-4 card p-4 rounded-xl">
        <div className="flex rounded-lg overflow-hidden border border-slate-300 dark:border-slate-700">
          {['', 'URGENT', 'NORMAL'].map(u => (
            <button key={u || 'ALL'} onClick={() => { setUrgency(u); mutate(true) }}
              className={`px-3 py-1.5 text-xs font-medium transition-colors
                ${urgency === u ? 'bg-emerald-500 text-slate-900 dark:text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-700'}`}>
              {u || 'ALL'}
            </button>
          ))}
        </div>
        <div className="ml-auto">
          <ExportButton data={rows as unknown as Record<string, unknown>[]} filename="procurement_recommendations" sheetName="Procurement" />
        </div>
      </div>

      {loading ? <LoadingSpinner /> : (
        <div className="space-y-6">
          {Object.entries(grouped).map(([vendor, items]) => {
            const vendorTotal = items.reduce((s, r) => s + (r.estimated_cost || 0), 0)
            const hasUrgent = items.some(r => r.urgency === 'URGENT')
            return (
              <div key={vendor} className="card p-6 rounded-2xl">
                {/* Vendor header */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20
                                    flex items-center justify-center">
                      <ShoppingCart size={16} className="text-emerald-400" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-slate-900 dark:text-white">{vendor}</h3>
                      <p className="text-xs text-slate-500">{items.length} items · Est. ₹{vendorTotal.toLocaleString('en-IN')}</p>
                    </div>
                  </div>
                  {hasUrgent && (
                    <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs font-semibold">
                      <Zap size={11} /> URGENT
                    </span>
                  )}
                </div>

                {/* Items table */}
                <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60">
                        {['Ingredient', 'Shortage', 'Open POs', 'Recommended', 'MOQ', 'Unit', 'Price', 'Est. Cost', 'Delivery', 'Urgency', ''].map(h => (
                          <th key={h} className="px-3 py-2.5 text-left text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((row, i) => (
                        <tr key={i} className={clsx('border-b border-slate-200 dark:border-slate-800/50 hover:bg-slate-100 dark:bg-slate-800/20', row.urgency === 'URGENT' && 'bg-rose-500/5')}>
                          <td className="px-3 py-2.5 text-slate-900 dark:text-white font-medium">{row.ingredient}</td>
                          <td className="px-3 py-2.5 text-rose-400">{Number(row.net_requirement).toLocaleString()}</td>
                          <td className="px-3 py-2.5 text-slate-500 dark:text-slate-400">{Number(row.po_qty).toLocaleString()}</td>
                          <td className="px-3 py-2.5 text-emerald-400 font-semibold">{Number(row.recommended_qty).toLocaleString()}</td>
                          <td className="px-3 py-2.5 text-slate-500 dark:text-slate-400">{Number(row.moq).toLocaleString()}</td>
                          <td className="px-3 py-2.5 text-slate-500 dark:text-slate-400">{row.unit}</td>
                          <td className="px-3 py-2.5 text-slate-500 dark:text-slate-400">₹{Number(row.price).toFixed(2)}</td>
                          <td className="px-3 py-2.5 text-slate-900 dark:text-white font-medium">₹{Number(row.estimated_cost).toLocaleString('en-IN')}</td>
                          <td className="px-3 py-2.5 text-slate-500 dark:text-slate-400 whitespace-nowrap">{row.expected_delivery}</td>
                          <td className="px-3 py-2.5">
                            {row.urgency === 'URGENT' ? (
                              <span className="flex items-center gap-1 text-rose-400 text-xs font-bold"><Zap size={11} />URGENT</span>
                            ) : (
                              <span className="text-slate-500 text-xs">NORMAL</span>
                            )}
                          </td>
                          <td className="px-3 py-2.5">
                            <button onClick={() => markOrdered(row.ingredient)}
                              className="px-2.5 py-1 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20
                                         text-emerald-400 text-xs font-medium border border-emerald-500/20 transition-colors whitespace-nowrap">
                              Mark Ordered
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )
          })}
          {Object.keys(grouped).length === 0 && (
            <div className="card p-16 rounded-2xl text-center text-slate-500">
              No procurement recommendations — warehouse is well stocked!
            </div>
          )}
        </div>
      )}
    </Layout>
  )
}

'use client'
import { useState, useEffect } from 'react'
import Layout from '@/components/Layout'
import DatePicker from '@/components/DatePicker'
import ExportButton from '@/components/ExportButton'
import LoadingSpinner from '@/components/LoadingSpinner'
import { useCachedApi } from '@/hooks/useCachedApi'
import { AlertTriangle, Info } from 'lucide-react'

export default function VariancePage() {
  const [startDate, setStartDate] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() - 7); return d.toISOString().slice(0, 10)
  })
  const [endDate, setEndDate] = useState(new Date().toISOString().slice(0, 10))
  const [outlet, setOutlet] = useState('')
  const [ingredient, setIngredient] = useState('')

  const params = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
    ...(outlet && { outlet }),
    ...(ingredient && { ingredient }),
  }).toString()

  const { data: cachedRows, loading, error, mutate } = useCachedApi<Record<string, unknown>[]>(`/api/variance?${params}`)
  const rows = cachedRows || []

  const fetchData = () => {
    mutate(true)
  }



  return (
    <Layout title="Variance Analysis (Wastage)">
      <div className="mb-6 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-4 rounded-xl flex gap-3 items-start">
        <Info className="text-sky-500 shrink-0 mt-0.5" size={18} />
        <div className="text-sm text-slate-700 dark:text-slate-300">
          <p className="font-semibold mb-1">How Variance works</p>
          <p>
            <strong>Expected Qty</strong> is calculated by exploding UrbanPiper POS dish sales through the Recipe Master. 
            <strong>Actual Qty</strong> is what the kitchen logged as consumed in SupplyNote.
            A positive variance means the kitchen used more ingredients than the sales justify (indicating wastage or over-portioning).
          </p>
        </div>
      </div>

      {/* Filters & View Toggle */}
      <div className="flex flex-col gap-4 mb-6 card p-4 rounded-xl relative z-40">
        <div className="flex flex-wrap items-center gap-3">
          <DatePicker label="From" value={startDate} onChange={setStartDate} />
          <DatePicker label="To" value={endDate} onChange={setEndDate} />
          <div className="flex flex-col gap-1.5">
             <label className="text-xs font-medium text-slate-500">Outlet</label>
             <input placeholder="Search..." value={outlet} onChange={e => setOutlet(e.target.value)}
               className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-200 placeholder-slate-600 focus:outline-none focus:border-emerald-500 w-40" />
          </div>
          <div className="flex flex-col gap-1.5">
             <label className="text-xs font-medium text-slate-500">Ingredient</label>
             <input placeholder="Search..." value={ingredient} onChange={e => setIngredient(e.target.value)}
               className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-200 placeholder-slate-600 focus:outline-none focus:border-emerald-500 w-40" />
          </div>
           <div className="flex flex-col gap-1.5 self-end">
             <button onClick={() => mutate(true)}
               className="px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-white text-sm font-medium transition-colors h-9">
               Apply
             </button>
          </div>
          <div className="ml-auto self-end h-9 flex items-center">
            <ExportButton data={filteredRows} filename="variance_report" sheetName="Variance" />
          </div>
        </div>
      </div>

      {loading ? <LoadingSpinner /> : (
        <div className="card rounded-2xl overflow-hidden border border-slate-200 dark:border-slate-800">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600 dark:text-slate-300">
              <thead className="bg-slate-50 dark:bg-slate-900/50 text-slate-500 dark:text-slate-400 text-xs uppercase font-semibold border-b border-slate-200 dark:border-slate-800">
                <tr>
                  <th className="px-6 py-4">Date</th>
                  <th className="px-6 py-4">Outlet</th>
                  <th className="px-6 py-4">Ingredient</th>
                  <th className="px-6 py-4 text-right">Expected (POS)</th>
                  <th className="px-6 py-4 text-right">Actual (SupplyNote)</th>
                  <th className="px-6 py-4 text-right">Variance Qty</th>
                  <th className="px-6 py-4 text-right">Variance %</th>
                  <th className="px-6 py-4 text-center">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800 bg-white dark:bg-slate-950">
                {rows.length === 0 ? (
                  <tr><td colSpan={8} className="px-6 py-8 text-center text-slate-500">No records found for this view.</td></tr>
                ) : (
                  rows.map((row: any, i: number) => {
                    const isRed = row.flag === 'red'
                    const isYellow = row.flag === 'yellow'
                    const isGreen = row.flag === 'green'
                    const isUnmapped = row.flag === 'unmapped'
                    
                    return (
                      <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-900/50 transition-colors">
                        <td className="px-6 py-4 whitespace-nowrap">{row.date}</td>
                        <td className="px-6 py-4 whitespace-nowrap font-medium text-slate-900 dark:text-white">{row.outlet}</td>
                        <td className="px-6 py-4 font-medium text-slate-900 dark:text-white">{row.ingredient}</td>
                        <td className="px-6 py-4 whitespace-nowrap text-right">{row.expected_qty} <span className="text-xs text-slate-400">{row.unit}</span></td>
                        <td className="px-6 py-4 whitespace-nowrap text-right font-medium">{row.actual_qty} <span className="text-xs text-slate-400">{row.unit}</span></td>
                        
                        <td className={`px-6 py-4 whitespace-nowrap text-right font-semibold ${isRed ? 'text-red-600 dark:text-red-400' : isYellow ? 'text-amber-600 dark:text-amber-400' : isUnmapped ? 'text-slate-600 dark:text-slate-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                          {row.variance_qty > 0 ? '+' : ''}{row.variance_qty} <span className="text-xs opacity-75">{row.unit}</span>
                        </td>
                        
                        <td className={`px-6 py-4 whitespace-nowrap text-right font-bold ${isRed ? 'text-red-600 dark:text-red-400' : isYellow ? 'text-amber-600 dark:text-amber-400' : isUnmapped ? 'text-slate-500 dark:text-slate-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                          {row.variance_pct !== null ? `${row.variance_pct}%` : '—'}
                        </td>
                        
                        <td className="px-6 py-4 whitespace-nowrap text-center">
                          {isRed && <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-700 dark:bg-red-500/10 dark:text-red-400"><AlertTriangle size={12}/> Critical</span>}
                          {isYellow && <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400">Warning</span>}
                          {isGreen && <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400">Normal</span>}
                          {isUnmapped && <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 dark:bg-slate-500/10 dark:text-slate-400">Needs Mapping</span>}
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Layout>
  )
}

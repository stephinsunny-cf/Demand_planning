'use client'
import { useState, useEffect } from 'react'
import Layout from '@/components/Layout'
import DataTable from '@/components/DataTable'
import LoadingSpinner from '@/components/LoadingSpinner'
import api from '@/lib/api'
import { Plus } from 'lucide-react'

export default function TrackerPage() {
  const [data, setData] = useState<Record<string, unknown>[]>([])
  const [loading, setLoading] = useState(true)
  const [showAddModal, setShowAddModal] = useState(false)
  const [newItem, setNewItem] = useState({ code: '', ingredient: '', supply_mode: 'Inhouse', drr: 0, wh_sih: 0, open_po: 0, neworder: 0, lead_time_days: 7.0 })

  const fetchData = async () => {
    setLoading(true)
    api.get('/api/tracker').then(r => {
      setData(r.data)
      setLoading(false)
    }).catch(e => {
      console.error(e)
      setLoading(false)
    })
  }

  useEffect(() => { fetchData() }, [])

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newItem.ingredient) return alert('Ingredient name is required')
    
    try {
      await api.post('/api/tracker', newItem)
      setShowAddModal(false)
      setNewItem({ code: '', ingredient: '', supply_mode: 'Inhouse', drr: 0, wh_sih: 0, open_po: 0, neworder: 0, lead_time_days: 7.0 })
      fetchData()
    } catch (e) {
      alert('Error adding item')
      console.error(e)
    }
  }

  const handleUpdateLeadTime = async (ingredient: string, newLeadTime: number) => {
    try {
      await api.put(`/api/tracker/${encodeURIComponent(ingredient)}/lead_time`, { lead_time_days: newLeadTime })
      fetchData() // Refresh
    } catch (e) {
      alert('Failed to update lead time')
    }
  }

  const EditableLeadTimeCell = ({ val, row }: { val: unknown, row: any }) => {
    const [editing, setEditing] = useState(false)
    const [value, setValue] = useState(Number(val ?? 7))

    const handleSave = () => {
      setEditing(false)
      if (value !== Number(val)) {
        handleUpdateLeadTime(row.ingredient, value)
      }
    }

    if (editing) {
      return (
        <input 
          autoFocus
          type="number" 
          value={value} 
          onChange={e => setValue(Number(e.target.value))}
          onBlur={handleSave}
          onKeyDown={e => e.key === 'Enter' && handleSave()}
          className="w-20 px-2 py-1 text-xs border border-emerald-500 rounded bg-white dark:bg-slate-800 text-slate-900 dark:text-white"
        />
      )
    }

    return (
      <div 
        onClick={() => setEditing(true)} 
        className="cursor-pointer hover:text-emerald-500 underline decoration-dashed decoration-slate-300 underline-offset-4"
        title="Click to edit"
      >
        {Number(val ?? 7).toFixed(1)}
      </div>
    )
  }

  const columns = [
    { key: 'code', label: 'Item Code', sortable: true },
    { key: 'ingredient', label: 'Ingredient / SKU', sortable: true },
    { key: 'supply_mode', label: 'Supply Mode', sortable: true },
    { key: 'lead_time_days', label: 'Safety Stock (Days)', sortable: true, render: (v: unknown, r: any) => <EditableLeadTimeCell val={v} row={r} /> },
    { key: 'drr', label: 'DRR', sortable: true, render: (v: unknown) => Number(v).toFixed(2) },
    { key: 'wh_sih', label: 'WH SIH', sortable: true, render: (v: unknown) => Number(v).toFixed(2) },
    { key: 'open_po', label: 'Open PO', sortable: true, render: (v: unknown) => Number(v).toFixed(2) },
    { key: 'neworder', label: 'New Order', sortable: true, render: (v: unknown) => Number(v).toFixed(2) },
  ]

  return (
    <Layout title="Procurement Tracker">
      <div className="space-y-6">
        <div className="card p-6 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900">
          <div className="flex justify-between items-center mb-6">
            <div>
              <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Active SKU List</h3>
              <p className="text-xs text-slate-500">Only items in this list are tracked by the forecasting engine.</p>
            </div>
            <button 
              onClick={() => setShowAddModal(true)}
              className="flex items-center gap-2 px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-white text-sm font-medium rounded-lg transition-colors">
              <Plus size={16} /> Add SKU
            </button>
          </div>
          
          {loading ? <LoadingSpinner message="Loading active SKUs..." /> : (
            <DataTable columns={columns} data={data} searchKeys={['code', 'ingredient']} />
          )}
        </div>
      </div>

      {/* Add Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-white dark:bg-slate-900 w-full max-w-md p-6 rounded-2xl shadow-xl">
            <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-4">Track New SKU</h3>
            <form onSubmit={handleAdd} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Ingredient / SKU Name *</label>
                <input required type="text" value={newItem.ingredient} onChange={e => setNewItem({...newItem, ingredient: e.target.value})} className="w-full px-3 py-2 bg-slate-100 dark:bg-slate-800 border-none rounded-lg text-sm focus:ring-2 focus:ring-emerald-500" placeholder="e.g. Tomoto Puree" />
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div className="col-span-1">
                  <label className="block text-xs font-semibold text-slate-500 mb-1">Item Code</label>
                  <input type="text" value={newItem.code} onChange={e => setNewItem({...newItem, code: e.target.value})} className="w-full px-3 py-2 bg-slate-100 dark:bg-slate-800 border-none rounded-lg text-sm focus:ring-2 focus:ring-emerald-500" placeholder="e.g. CFVEG024" />
                </div>
                <div className="col-span-1">
                  <label className="block text-xs font-semibold text-slate-500 mb-1">Supply Mode</label>
                  <select 
                    value={newItem.supply_mode} 
                    onChange={e => setNewItem({...newItem, supply_mode: e.target.value})}
                    className="w-full px-3 py-2 bg-slate-100 dark:bg-slate-800 border-none rounded-lg text-sm focus:ring-2 focus:ring-emerald-500"
                  >
                    <option value="Dry">Dry</option>
                    <option value="Frozen">Frozen</option>
                    <option value="FnV">FnV</option>
                  </select>
                </div>
                <div className="col-span-1">
                  <label className="block text-xs font-semibold text-slate-500 mb-1">Safety Stock (Days)</label>
                  <input type="number" step="0.1" value={newItem.lead_time_days} onChange={e => setNewItem({...newItem, lead_time_days: Number(e.target.value)})} className="w-full px-3 py-2 bg-slate-100 dark:bg-slate-800 border-none rounded-lg text-sm focus:ring-2 focus:ring-emerald-500" />
                </div>
              </div>
              <div className="flex justify-end gap-3 mt-6">
                <button type="button" onClick={() => setShowAddModal(false)} className="px-4 py-2 text-sm font-medium text-slate-500 hover:text-slate-700">Cancel</button>
                <button type="submit" className="px-4 py-2 bg-emerald-500 hover:bg-emerald-400 text-white text-sm font-medium rounded-lg">Save & Track</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </Layout>
  )
}

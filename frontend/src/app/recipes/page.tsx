// src/app/recipes/page.tsx
'use client'
import { useState, useEffect } from 'react'
import Layout from '@/components/Layout'
import DataTable from '@/components/DataTable'
import LoadingSpinner from '@/components/LoadingSpinner'
import api from '@/lib/api'
import { useRole } from '@/hooks/useRole'
import { ChefHat, AlertTriangle, Edit2, X, Save } from 'lucide-react'

interface Recipe {
  dish_name:       string
  ingredient:      string
  qty_per_portion: number
  unit:            string
  yield_factor:    number
  updated_at:      string
  brand:           string
}

export default function RecipesPage() {
  const [rows,      setRows]     = useState<Recipe[]>([])
  const [loading,   setLoading]  = useState(true)
  const [search,    setSearch]   = useState('')
  const [brand,     setBrand]    = useState('')
  const [editDish,  setEditDish] = useState<string | null>(null)
  const [editRows,  setEditRows] = useState<Recipe[]>([])
  const [brands,    setBrands]   = useState<string[]>([])
  const { canEdit } = useRole()

  const fetchData = async () => {
    setLoading(true)
    const params = new URLSearchParams({ ...(brand && { brand }), ...(search && { dish_name: search }) })
    const r = await api.get(`/api/recipes?${params}`).catch(() => ({ data: [] }))
    setRows(r.data)
    setBrands([...new Set((r.data as Recipe[]).map(d => d.brand).filter(Boolean))].sort())
    setLoading(false)
  }

  useEffect(() => { fetchData() }, [])

  const openEdit = (dishName: string) => {
    setEditDish(dishName)
    setEditRows(rows.filter(r => r.dish_name === dishName))
  }

  const saveEdit = async () => {
    if (!editDish) return
    await api.put(`/api/recipes/${encodeURIComponent(editDish)}`, editRows.map(r => ({
      ingredient:      r.ingredient,
      qty_per_portion: r.qty_per_portion,
      unit:            r.unit,
      yield_factor:    r.yield_factor,
    })))
    setEditDish(null)
    fetchData()
  }

  const noRecipeDishes = [...new Set(rows.filter(r => !r.ingredient).map(r => r.dish_name))]

  const columns = [
    { key: 'dish_name',       label: 'Dish',         sortable: true },
    { key: 'brand',           label: 'Brand',        sortable: true },
    { key: 'ingredient',      label: 'Ingredient',   sortable: true },
    { key: 'qty_per_portion', label: 'Qty/Portion',  sortable: true, render: (v: unknown) => Number(v).toFixed(2) },
    { key: 'unit',            label: 'Unit',         sortable: false },
    { key: 'yield_factor',    label: 'Yield Factor', sortable: true, render: (v: unknown) => {
      const n = Number(v)
      return <span className={n < 0.9 ? 'text-amber-400' : 'text-slate-600 dark:text-slate-300'}>{n.toFixed(2)}</span>
    }},
    { key: 'updated_at', label: 'Updated', sortable: true, render: (v: unknown) => v ? String(v).slice(0, 10) : '—' },
    ...(canEdit ? [{
      key: 'dish_name',
      label: '',
      sortable: false,
      render: (v: unknown) => (
        <button onClick={() => openEdit(String(v))}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-700
                     text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:text-white text-xs border border-slate-300 dark:border-slate-700 transition-all">
          <Edit2 size={11} /> Edit
        </button>
      )
    }] : [])
  ]

  return (
    <Layout title="Recipe Manager">
      {/* Warning banner */}
      {noRecipeDishes.length > 0 && (
        <div className="flex items-center gap-3 p-4 mb-6 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400">
          <AlertTriangle size={16} />
          <span className="text-sm">
            <strong>{noRecipeDishes.length} dishes</strong> have no recipe mapped — ingredient planning will be inaccurate.
          </span>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-4 card p-4 rounded-xl">
        <input placeholder="Search dish or ingredient..." value={search}
          onChange={e => { setSearch(e.target.value); fetchData() }}
          className="bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-900 dark:text-white
                     placeholder-slate-600 focus:outline-none focus:border-emerald-500 w-56" />
        <select value={brand} onChange={e => { setBrand(e.target.value); fetchData() }}
          className="bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-900 dark:text-white focus:outline-none focus:border-emerald-500">
          <option value="">All Brands</option>
          {brands.map(b => <option key={b} value={b}>{b}</option>)}
        </select>
      </div>

      <div className="card p-6 rounded-2xl">
        <div className="flex items-center gap-3 mb-4">
          <ChefHat size={18} className="text-emerald-400" />
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Recipe Master ({rows.length} rows)</h3>
        </div>
        {loading ? <LoadingSpinner /> : (
          <DataTable columns={columns} data={rows as unknown as Record<string, unknown>[]} searchKeys={['dish_name', 'ingredient', 'brand']} />
        )}
      </div>

      {/* Edit Modal */}
      {editDish && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-2xl w-full max-w-2xl p-6 shadow-2xl">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white">Edit Recipe: <span className="text-emerald-400">{editDish}</span></h3>
              <button onClick={() => setEditDish(null)} className="p-2 rounded-lg hover:bg-slate-100 dark:bg-slate-800 text-slate-500 hover:text-slate-900 dark:text-white">
                <X size={16} />
              </button>
            </div>
            <div className="space-y-3 max-h-96 overflow-y-auto">
              {editRows.map((row, i) => (
                <div key={i} className="grid grid-cols-4 gap-3 p-3 bg-slate-100 dark:bg-slate-800/50 rounded-xl border border-slate-300 dark:border-slate-700">
                  <div>
                    <label className="text-xs text-slate-500 mb-1 block">Ingredient</label>
                    <p className="text-sm text-slate-900 dark:text-white">{row.ingredient}</p>
                  </div>
                  <div>
                    <label className="text-xs text-slate-500 mb-1 block">Qty/Portion</label>
                    <input type="number" value={row.qty_per_portion}
                      onChange={e => setEditRows(prev => prev.map((r, j) => j === i ? { ...r, qty_per_portion: parseFloat(e.target.value) } : r))}
                      className="w-full bg-slate-700 border border-slate-600 rounded-lg px-2 py-1 text-sm text-slate-900 dark:text-white focus:outline-none focus:border-emerald-500" />
                  </div>
                  <div>
                    <label className="text-xs text-slate-500 mb-1 block">Unit</label>
                    <input value={row.unit}
                      onChange={e => setEditRows(prev => prev.map((r, j) => j === i ? { ...r, unit: e.target.value } : r))}
                      className="w-full bg-slate-700 border border-slate-600 rounded-lg px-2 py-1 text-sm text-slate-900 dark:text-white focus:outline-none focus:border-emerald-500" />
                  </div>
                  <div>
                    <label className="text-xs text-slate-500 mb-1 block">Yield Factor</label>
                    <input type="number" step="0.01" min="0.01" max="1" value={row.yield_factor}
                      onChange={e => setEditRows(prev => prev.map((r, j) => j === i ? { ...r, yield_factor: parseFloat(e.target.value) } : r))}
                      className="w-full bg-slate-700 border border-slate-600 rounded-lg px-2 py-1 text-sm text-slate-900 dark:text-white focus:outline-none focus:border-emerald-500" />
                  </div>
                </div>
              ))}
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setEditDish(null)} className="px-4 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-700 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:text-white text-sm border border-slate-300 dark:border-slate-700 transition-all">
                Cancel
              </button>
              <button onClick={saveEdit} className="flex items-center gap-2 px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-white text-sm font-medium transition-all">
                <Save size={14} /> Save Changes
              </button>
            </div>
          </div>
        </div>
      )}
    </Layout>
  )
}

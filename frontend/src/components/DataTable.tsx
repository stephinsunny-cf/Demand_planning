// src/components/DataTable.tsx
'use client'
import { useState, useMemo } from 'react'
import { ChevronUp, ChevronDown, ChevronsUpDown, Search } from 'lucide-react'
import { clsx } from 'clsx'

interface Column {
  key:      string
  label:    string
  render?:  (val: unknown, row: Record<string, unknown>) => React.ReactNode
  sortable?: boolean
  className?: string
}

interface Props {
  columns:   Column[]
  data:      Record<string, unknown>[]
  searchable?: boolean
  searchKeys?: string[]
  maxRows?:  number
}

export default function DataTable({ columns, data, searchable = true, searchKeys, maxRows = 200 }: Props) {
  const [sortKey,   setSortKey]   = useState<string | null>(null)
  const [sortDir,   setSortDir]   = useState<'asc' | 'desc'>('asc')
  const [search,    setSearch]    = useState('')
  const [page,      setPage]      = useState(0)
  const PAGE_SIZE = 50

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
    setPage(0)
  }

  const filtered = useMemo(() => {
    let d = data.slice(0, maxRows)
    if (search && searchKeys) {
      const q = search.toLowerCase()
      d = d.filter(row => searchKeys.some(k => String(row[k] ?? '').toLowerCase().includes(q)))
    }
    if (sortKey) {
      d = [...d].sort((a, b) => {
        const va = a[sortKey]; const vb = b[sortKey]
        if (va == null) return 1
        if (vb == null) return -1
        const cmp = String(va).localeCompare(String(vb), undefined, { numeric: true })
        return sortDir === 'asc' ? cmp : -cmp
      })
    }
    return d
  }, [data, search, searchKeys, sortKey, sortDir, maxRows])

  const pages = Math.ceil(filtered.length / PAGE_SIZE)
  const displayed = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  return (
    <div className="space-y-3">
      {searchable && searchKeys && (
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(0) }}
            placeholder="Search..."
            className="w-full pl-8 pr-4 py-2 bg-slate-100 dark:bg-slate-800/50 border border-slate-300 dark:border-slate-700 rounded-lg
                       text-sm text-slate-700 dark:text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500/50"
          />
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60">
              {columns.map(col => (
                <th
                  key={col.key}
                  className={clsx(
                    'px-4 py-3 text-left text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider',
                    col.sortable !== false && 'cursor-pointer hover:text-slate-900 dark:text-white select-none',
                    col.className,
                  )}
                  onClick={() => col.sortable !== false && handleSort(col.key)}
                >
                  <div className="flex items-center gap-1">
                    {col.label}
                    {col.sortable !== false && (
                      <span className="text-slate-600">
                        {sortKey === col.key
                          ? sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />
                          : <ChevronsUpDown size={12} />
                        }
                      </span>
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayed.map((row, i) => (
              <tr
                key={i}
                className="border-b border-slate-200 dark:border-slate-800/50 hover:bg-slate-100 dark:bg-slate-800/30 transition-colors"
              >
                {columns.map(col => (
                  <td key={col.key} className={clsx('px-4 py-3 text-slate-600 dark:text-slate-300', col.className)}>
                    {col.render ? col.render(row[col.key], row) : String(row[col.key] ?? '—')}
                  </td>
                ))}
              </tr>
            ))}
            {displayed.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-4 py-12 text-center text-slate-500">
                  No data found
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>{filtered.length} rows</span>
          <div className="flex gap-2">
            <button
              disabled={page === 0}
              onClick={() => setPage(p => p - 1)}
              className="px-2 py-1 rounded bg-slate-100 dark:bg-slate-800 hover:bg-slate-700 disabled:opacity-40"
            >←</button>
            <span className="px-2 py-1">Page {page + 1} / {pages}</span>
            <button
              disabled={page >= pages - 1}
              onClick={() => setPage(p => p + 1)}
              className="px-2 py-1 rounded bg-slate-100 dark:bg-slate-800 hover:bg-slate-700 disabled:opacity-40"
            >→</button>
          </div>
        </div>
      )}
    </div>
  )
}

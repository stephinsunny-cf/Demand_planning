// src/components/ExportButton.tsx
'use client'
import { Download } from 'lucide-react'
import * as XLSX from 'xlsx'

interface Props {
  data:      Record<string, unknown>[]
  filename?: string
  sheetName?: string
}

export default function ExportButton({ data, filename = 'export', sheetName = 'Data' }: Props) {
  const handleExport = () => {
    if (!data.length) return
    const ws  = XLSX.utils.json_to_sheet(data)
    const wb  = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, sheetName)
    XLSX.writeFile(wb, `${filename}_${new Date().toISOString().slice(0,10)}.xlsx`)
  }
  return (
    <button
      onClick={handleExport}
      className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium
                 bg-slate-100 dark:bg-slate-800 hover:bg-slate-700 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:text-white
                 border border-slate-300 dark:border-slate-700 hover:border-slate-600 transition-all"
    >
      <Download size={14} />
      Export Excel
    </button>
  )
}

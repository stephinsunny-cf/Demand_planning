// src/components/KPICard.tsx
'use client'
import { ReactNode } from 'react'
import { clsx } from 'clsx'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

interface Props {
  title:    string
  value:    string | number
  subtitle?: string
  icon:     ReactNode
  trend?:   number
  color?:   string // kept for prop compatibility, ignored in new design
  onClick?: () => void
}

export default function KPICard({ title, value, subtitle, icon, trend, onClick }: Props) {
  return (
    <div
      onClick={onClick}
      className={clsx(
        'relative overflow-hidden rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-5',
        'transition-all duration-200',
        onClick && 'cursor-pointer hover:bg-slate-100 dark:bg-slate-800/80 hover:border-slate-300 dark:border-slate-700',
      )}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800/50 text-slate-500 dark:text-slate-400 border border-slate-300 dark:border-slate-700/50">
          {icon}
        </div>
        {trend !== undefined && (
          <div className={clsx('flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded-md bg-slate-100 dark:bg-slate-800/50',
            trend > 0 ? 'text-emerald-400' : trend < 0 ? 'text-rose-400' : 'text-slate-500 dark:text-slate-400'
          )}>
            {trend > 0 ? <TrendingUp size={12} /> : trend < 0 ? <TrendingDown size={12} /> : <Minus size={12} />}
            {trend !== 0 && `${Math.abs(trend)}%`}
          </div>
        )}
      </div>

      <p className="text-2xl font-bold text-slate-900 dark:text-slate-100 mb-0.5 tracking-tight">{value}</p>
      <p className="text-sm font-medium text-slate-500 dark:text-slate-400">{title}</p>
      {subtitle && <p className="text-xs text-slate-500 mt-1">{subtitle}</p>}
    </div>
  )
}

// src/components/AlertBadge.tsx
import { clsx } from 'clsx'

interface Props {
  severity: 'CRITICAL' | 'WARNING' | 'INFO' | string
}

const cfg = {
  CRITICAL: { bg: 'bg-rose-600',   text: 'text-slate-900 dark:text-white' },
  WARNING:  { bg: 'bg-amber-500',  text: 'text-slate-900 dark:text-white' },
  INFO:     { bg: 'bg-sky-500',    text: 'text-slate-900 dark:text-white' },
}

export default function AlertBadge({ severity }: Props) {
  const c = cfg[severity as keyof typeof cfg] || cfg.INFO
  return (
    <span className={clsx('px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-widest', c.bg, c.text)}>
      {severity}
    </span>
  )
}

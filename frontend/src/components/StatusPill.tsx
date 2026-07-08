// src/components/StatusPill.tsx
import { clsx } from 'clsx'

interface Props {
  status: 'RED' | 'YELLOW' | 'GREEN' | string
  className?: string
}

const config = {
  RED:    { bg: 'bg-rose-500/20',   text: 'text-rose-400',   border: 'border-rose-500/40',   dot: 'bg-rose-400'   },
  YELLOW: { bg: 'bg-amber-500/20',  text: 'text-amber-400',  border: 'border-amber-500/40',  dot: 'bg-amber-400'  },
  GREEN:  { bg: 'bg-emerald-500/20',text: 'text-emerald-400',border: 'border-emerald-500/40',dot: 'bg-emerald-400' },
}

export default function StatusPill({ status, className }: Props) {
  const c = config[status as keyof typeof config] || config.GREEN
  return (
    <span className={clsx(
      'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold border',
      c.bg, c.text, c.border, className,
    )}>
      <span className={clsx('w-1.5 h-1.5 rounded-full', c.dot)} />
      {status}
    </span>
  )
}

// src/components/Sidebar.tsx
'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { clsx } from 'clsx'
import { useRole } from '@/hooks/useRole'
import {
  LayoutDashboard, TrendingUp, BarChart2, Truck, BookOpen,
  Warehouse, ShoppingCart, Bell, FileText, Settings, ChefHat,
} from 'lucide-react'

const NAV = [
  { href: '/dashboard',   label: 'Dashboard',   icon: LayoutDashboard, page: 'dashboard'   },
  { href: '/sales',       label: 'Sales',        icon: TrendingUp,      page: 'sales'       },
  { href: '/forecast',    label: 'Forecast',     icon: BarChart2,       page: 'forecast'    },
  { href: '/supply',      label: 'Supply Plan',  icon: Truck,           page: 'supply'      },
  { href: '/recipes',     label: 'Recipes',      icon: ChefHat,         page: 'recipes'     },
  { href: '/warehouse',   label: 'Warehouse',    icon: Warehouse,       page: 'warehouse'   },
  { href: '/procurement', label: 'Procurement',  icon: ShoppingCart,    page: 'procurement' },
  { href: '/tracker',     label: 'Tracker',      icon: FileText,        page: 'tracker'     },
  { href: '/alerts',      label: 'Alerts',       icon: Bell,            page: 'alerts'      },
  { href: '/reports',     label: 'Reports',      icon: FileText,        page: 'reports'     },
  { href: '/admin',       label: 'Admin',        icon: Settings,        page: 'admin'       },
]

export default function Sidebar() {
  const pathname  = usePathname()
  const { canAccess } = useRole()

  const visible = NAV.filter(n => canAccess(n.page))

  return (
    <aside className="w-64 flex-shrink-0 flex flex-col bg-slate-50 dark:bg-slate-900/50 pt-6 border-r border-slate-100 dark:border-slate-800/60">
      {/* Logo */}
      <div className="h-12 flex items-center px-8 mb-6">
        <div className="flex flex-col">
          <div className="px-3 py-1.5 rounded bg-[#011B4D] inline-flex items-center justify-center mb-0.5">
            <span className="text-white font-extrabold text-[15px] tracking-wider leading-none font-sans">CUREFOODS</span>
          </div>
          <p className="text-slate-500 dark:text-slate-400 text-[10px] tracking-wide uppercase font-semibold pl-0.5">Demand Planning</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-3 space-y-0.5 overflow-y-auto">
        {visible.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(href + '/')
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                'flex items-center gap-3 px-4 py-2.5 mx-3 rounded-lg text-sm font-medium transition-colors',
                active
                  ? 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800/40',
              )}
            >
              <Icon size={16} className={active ? 'text-emerald-400' : ''} />
              {label}
            </Link>
          )
        })}
      </nav>

      <div className="px-6 pb-6 mt-auto">
        <div className="rounded-2xl bg-white/50 dark:bg-slate-900 p-4 text-xs text-slate-500 border border-white/60 dark:border-slate-800/50">
          <p className="text-slate-500 dark:text-slate-400 font-medium mb-0.5">Demand Planning Engine</p>
          <p>v1.0 · Beta</p>
        </div>
      </div>
    </aside>
  )
}

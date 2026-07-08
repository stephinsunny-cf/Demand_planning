// src/app/login/page.tsx
'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Globe, Zap, BarChart2, Shield } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'

export default function LoginPage() {
  const { user, loading, signInWithGoogle } = useAuth()
  const router = useRouter()
  const DEMO   = process.env.NEXT_PUBLIC_DEMO_MODE === 'true'

  useEffect(() => {
    if (DEMO || (!loading && user)) {
      router.push('/dashboard')
    }
  }, [user, loading, router, DEMO])

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center p-4 relative overflow-hidden">
      {/* Animated background */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute -top-40 -right-40 w-96 h-96 rounded-full bg-blue-500/10 blur-3xl animate-pulse" />
        <div className="absolute -bottom-40 -left-40 w-96 h-96 rounded-full bg-cyan-500/10 blur-3xl animate-pulse delay-1000" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 rounded-full bg-slate-500/5 blur-3xl" />
      </div>

      {/* Grid pattern */}
      <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.015)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.015)_1px,transparent_1px)] bg-[size:64px_64px]" />

      <div className="relative z-10 w-full max-w-md">
        {/* Card */}
        <div className="rounded-3xl bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-slate-800 backdrop-blur-xl p-8 shadow-2xl">

          {/* Logo + Brand */}
          <div className="text-center mb-8">
            <div className="px-5 py-3 rounded-lg bg-[#011B4D] inline-flex items-center justify-center mb-4 shadow-lg shadow-blue-500/10">
              <span className="text-white font-extrabold text-2xl tracking-wider leading-none font-sans">CUREFOODS</span>
            </div>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-white mb-1">Demand Planning Engine</h1>
            <p className="text-slate-500 dark:text-slate-400 text-sm">Curefoods Internal Platform</p>
          </div>

          {/* Feature pills */}
          <div className="flex flex-wrap gap-2 justify-center mb-8">
            {[
              { icon: BarChart2, label: 'AI Forecasting' },
              { icon: Zap,       label: 'Live Alerts' },
              { icon: Shield,    label: 'Role-based Access' },
            ].map(({ icon: Icon, label }) => (
              <div key={label} className="flex items-center gap-1.5 px-3 py-1.5 rounded-full
                                         bg-slate-100 dark:bg-slate-800/60 border border-slate-300 dark:border-slate-700 text-slate-500 dark:text-slate-400 text-xs">
                <Icon size={11} />
                {label}
              </div>
            ))}
          </div>

          {/* Sign in button */}
          <button
            onClick={signInWithGoogle}
            className="w-full flex items-center justify-center gap-3 py-3.5 px-6 rounded-xl
                       bg-white hover:bg-slate-100 text-slate-900 font-semibold text-sm
                       transition-all duration-200 hover:shadow-lg hover:shadow-white/10
                       active:scale-[0.98]"
          >
            <Globe size={18} />
            Continue with Google
          </button>

          <p className="text-center text-xs text-slate-600 mt-6">
            Access restricted to Curefoods team only.<br />
            Contact your admin if you can&apos;t log in.
          </p>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-3 mt-6">
          {[
            { label: 'Outlets',   value: '50+' },
            { label: 'Brands',    value: '8'   },
            { label: 'SKUs',      value: '500+' },
          ].map(({ label, value }) => (
            <div key={label} className="text-center rounded-xl bg-white dark:bg-slate-900/40 border border-slate-200 dark:border-slate-800 py-3">
              <p className="text-xl font-bold text-slate-900 dark:text-white">{value}</p>
              <p className="text-xs text-slate-500">{label}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

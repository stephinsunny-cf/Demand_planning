// src/app/login/page.tsx
'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Globe, Eye, EyeOff } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'

export default function LoginPage() {
  const { user, loading, signInWithGoogle, signInWithEmail } = useAuth()
  const router = useRouter()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    if (!loading && user) {
      router.push('/dashboard')
    }
  }, [user, loading, router])

  const handleEmailLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setErrorMsg('')
    setIsSubmitting(true)
    try {
      await signInWithEmail(email, password)
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to sign in')
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 p-4">
      <div className="w-full max-w-md bg-white dark:bg-slate-900 rounded-2xl shadow-xl border border-slate-100 dark:border-slate-800 p-8 sm:p-10">
        
        {/* Top Logo & Title */}
        <div className="text-center mb-10">
          <div className="px-5 py-3 rounded-lg bg-[#011B4D] inline-flex items-center justify-center shadow-lg shadow-blue-500/10 mb-4">
            <span className="text-white font-extrabold text-2xl tracking-wider leading-none font-sans">CUREFOODS</span>
          </div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-white">
            Demand Planning Engine
          </h1>
        </div>

        {errorMsg && (
          <div className="mb-6 p-4 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border border-red-200 dark:border-red-800/30 font-medium text-center">
            {errorMsg}
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleEmailLogin} className="space-y-5 mb-8">
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Email address</label>
            <input
              type="email"
              required
              placeholder="name@curefoods.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              className="w-full px-4 py-3 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-all text-slate-900 dark:text-white"
            />
          </div>
          
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">Password</label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                required
                placeholder="Enter your password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full pl-4 pr-12 py-3 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-all text-slate-900 dark:text-white"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                tabIndex={-1}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          <div className="pt-2">
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full flex items-center justify-center py-3.5 px-6 rounded-xl bg-[#6366f1] hover:bg-[#4f46e5] disabled:opacity-70 text-white font-semibold text-sm transition-all duration-200 shadow-lg shadow-indigo-500/25 active:scale-[0.98]"
            >
              {isSubmitting ? 'Signing in...' : 'Sign In'}
            </button>
          </div>
        </form>

        <div className="flex items-center gap-4 mb-8">
          <div className="flex-1 h-px bg-slate-200 dark:bg-slate-800" />
          <span className="text-xs text-slate-400 uppercase tracking-widest font-semibold">Or register with</span>
          <div className="flex-1 h-px bg-slate-200 dark:bg-slate-800" />
        </div>

        <button
          type="button"
          onClick={signInWithGoogle}
          className="w-full flex items-center justify-center gap-3 py-3.5 px-6 rounded-xl
                     bg-slate-50 dark:bg-slate-950 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 font-semibold text-sm
                     transition-all duration-200 border border-slate-200 dark:border-slate-700 shadow-sm
                     active:scale-[0.98]"
        >
          <Globe size={18} className="text-blue-500" />
          Google
        </button>

      </div>
      
      {/* Footer Text */}
      <div className="absolute bottom-6 left-0 right-0 text-center">
        <p className="text-xs text-slate-400">
          Access restricted to Curefoods internal team.
        </p>
      </div>
    </div>
  )
}

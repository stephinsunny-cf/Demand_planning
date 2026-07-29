// src/app/login/page.tsx
'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Eye, EyeOff, ArrowRight } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'
import api from '@/lib/api'

export default function LoginPage() {
  const { user, loading, signInWithEmail } = useAuth()
  const router = useRouter()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Auto-redirect if already logged in (when loading the page initially)
  useEffect(() => {
    if (!loading && user) {
      // Don't auto-redirect here to avoid race conditions with the login handler
      // We assume if they land on /login and have a session, we shouldn't force them anywhere unless they click
    }
  }, [user, loading])

  const handleEmailLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setErrorMsg('')
    setIsSubmitting(true)
    try {
      await signInWithEmail(email, password)
      
      // Delay slightly to ensure cookie is propagated
      await new Promise(r => setTimeout(r, 500))
      
      // Check if user must reset password on first login
      try {
        const res = await api.get('/api/auth/profile')
        if (res.data?.must_reset_password) {
          router.push('/reset-password')
          return
        }
      } catch (profileErr) {
        console.warn('Could not fetch profile for reset check', profileErr)
      }
      
      router.push('/dashboard')
    } catch (err: any) {
      let msg = err.message || 'Failed to sign in'
      if (msg === 'Failed to fetch' || msg.toLowerCase().includes('invalid login credentials')) {
        msg = 'Incorrect email or password.'
      }
      setErrorMsg(msg)
      setIsSubmitting(false)
    }
  }


  return (
    <div className="min-h-screen flex flex-col md:flex-row bg-slate-900 overflow-hidden font-sans">
      
      {/* Left side - Dynamic Brand Area */}
      <div className="hidden md:flex md:w-1/2 relative bg-[#011B4D] items-center justify-center p-12 overflow-hidden">
        {/* Subtle animated background gradients */}
        <div className="absolute inset-0 bg-gradient-to-br from-blue-600/20 to-purple-600/20 mix-blend-overlay"></div>
        <div className="absolute top-0 left-0 w-full h-full bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-indigo-500/30 via-transparent to-transparent"></div>
        <div className="absolute bottom-0 right-0 w-full h-full bg-[radial-gradient(ellipse_at_bottom_left,_var(--tw-gradient-stops))] from-blue-500/20 via-transparent to-transparent"></div>
        
        <div className="relative z-10 text-white max-w-lg">
          <div className="px-6 py-2 rounded-xl bg-white/10 backdrop-blur-md border border-white/10 inline-flex items-center justify-center mb-8 shadow-2xl">
            <span className="text-white font-extrabold text-3xl tracking-widest leading-none">CUREFOODS</span>
          </div>
          <h1 className="text-5xl font-bold mb-6 leading-tight tracking-tight">
            Demand Planning <br />
            <span className="text-blue-400">Engine v2</span>
          </h1>
          <p className="text-lg text-slate-300 leading-relaxed font-light max-w-md">
            Advanced supply chain forecasting, intelligent variance analysis, and predictive procurement operations.
          </p>
        </div>
      </div>

      {/* Right side - Login Form */}
      <div className="flex-1 flex items-center justify-center p-6 sm:p-12 bg-white dark:bg-[#0a0f1c] relative">
        <div className="w-full max-w-md space-y-8 relative z-10">
          
          <div className="md:hidden text-center mb-10">
            <div className="px-5 py-2 rounded-lg bg-[#011B4D] inline-flex items-center justify-center shadow-lg mb-4">
              <span className="text-white font-extrabold text-2xl tracking-wider leading-none">CUREFOODS</span>
            </div>
            <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Demand Planning</h2>
          </div>

          <div className="text-left mb-8 hidden md:block">
            <h2 className="text-3xl font-bold text-slate-900 dark:text-white tracking-tight mb-2">Welcome back</h2>
            <p className="text-slate-500 dark:text-slate-400">Sign in to your internal account to continue.</p>
          </div>

          {errorMsg && (
            <div className="p-4 rounded-xl bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 text-sm border border-red-200 dark:border-red-500/20 flex items-center animate-in fade-in slide-in-from-top-2">
              <div className="w-1.5 h-1.5 rounded-full bg-red-500 mr-3"></div>
              {errorMsg}
            </div>
          )}

          <form onSubmit={handleEmailLogin} className="space-y-6" action="#" method="POST">
            <div className="space-y-2 group">
              <label htmlFor="email" className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 group-focus-within:text-blue-600 dark:group-focus-within:text-blue-400 transition-colors">
                Email Address
              </label>
              <input
                id="email"
                name="email"
                type="email"
                required
                autoComplete="username"
                placeholder="name@curefoods.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="w-full px-4 py-3.5 bg-slate-50 dark:bg-[#111827] border border-slate-200 dark:border-slate-800 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all text-slate-900 dark:text-white shadow-sm placeholder:text-slate-400"
              />
            </div>
            
            <div className="space-y-2 group">
              <div className="flex justify-between items-center">
                <label htmlFor="password" className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 group-focus-within:text-blue-600 dark:group-focus-within:text-blue-400 transition-colors">
                  Password
                </label>
                <a href="/forgot-password" className="text-xs font-medium text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300">
                  Forgot password?
                </a>
              </div>
              <div className="relative">
                <input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  required
                  autoComplete="current-password"
                  placeholder="Enter your password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="w-full pl-4 pr-12 py-3.5 bg-slate-50 dark:bg-[#111827] border border-slate-200 dark:border-slate-800 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all text-slate-900 dark:text-white shadow-sm placeholder:text-slate-400"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors focus:outline-none"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <div className="pt-4">
              <button
                type="submit"
                disabled={isSubmitting}
                className="group w-full flex items-center justify-center gap-2 py-4 px-6 rounded-xl bg-[#011B4D] hover:bg-[#02266b] disabled:opacity-70 text-white font-semibold text-sm transition-all duration-300 shadow-[0_4_20px_rgba(1,27,77,0.15)] hover:shadow-[0_6_25px_rgba(1,27,77,0.3)] active:scale-[0.98]"
              >
                {isSubmitting ? 'Authenticating...' : 'Sign in to Dashboard'}
                {!isSubmitting && <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />}
              </button>
            </div>
          </form>

        </div>
        
        <div className="absolute bottom-8 left-0 right-0 text-center">
          <p className="text-xs text-slate-400 font-medium">
            Access restricted to Curefoods internal team.
          </p>
        </div>
      </div>
    </div>
  )
}

// src/app/login/page.tsx
'use client'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Globe } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'

export default function LoginPage() {
  const { user, loading, signInWithGoogle, signInWithEmail } = useAuth()
  const router = useRouter()
  const DEMO   = process.env.NEXT_PUBLIC_DEMO_MODE === 'true'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errorMsg, setErrorMsg] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    if (DEMO || (!loading && user)) {
      router.push('/dashboard')
    }
  }, [user, loading, router, DEMO])

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
    <div className="min-h-screen flex bg-white dark:bg-slate-950">
      {/* Left Panel - Image Background */}
      <div className="hidden lg:flex lg:w-1/2 relative bg-slate-900 flex-col justify-between p-12 overflow-hidden">
        {/* Background Image */}
        <div 
          className="absolute inset-0 bg-cover bg-center opacity-40 mix-blend-overlay"
          style={{ backgroundImage: "url('/login-bg.png')" }}
        />
        {/* Gradient Overlay */}
        <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-900/50 to-transparent" />
        
        {/* Top Logo Area */}
        <div className="relative z-10 flex items-center gap-3">
          <div className="px-4 py-2 rounded-lg bg-[#011B4D] inline-flex items-center justify-center shadow-lg shadow-blue-500/20">
            <span className="text-white font-extrabold text-xl tracking-wider leading-none font-sans">CUREFOODS</span>
          </div>
          <span className="text-slate-200 font-semibold text-lg tracking-wide">Demand Planning Engine</span>
        </div>

        {/* Bottom Text Area */}
        <div className="relative z-10 max-w-lg mb-8">
          <h1 className="text-4xl font-bold text-white mb-4 leading-tight">
            Forecasting the future of food supply.
          </h1>
          <p className="text-slate-300 text-lg leading-relaxed">
            AI-powered demand predictions, real-time warehouse alerts, and intelligent procurement—all in one premium platform.
          </p>
        </div>
      </div>

      {/* Right Panel - Login Form */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-8 sm:p-12 lg:p-24 relative">
        {/* Subtle decorative glow */}
        <div className="absolute top-0 right-0 w-96 h-96 bg-blue-500/5 rounded-full blur-3xl pointer-events-none" />
        
        <div className="w-full max-w-md relative z-10">
          
          {/* Mobile Logo (hidden on desktop) */}
          <div className="lg:hidden mb-10 text-center">
             <div className="px-5 py-3 rounded-lg bg-[#011B4D] inline-flex items-center justify-center shadow-lg mb-4">
              <span className="text-white font-extrabold text-2xl tracking-wider leading-none font-sans">CUREFOODS</span>
            </div>
            <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Welcome Back</h2>
            <p className="text-slate-500 dark:text-slate-400 mt-2">Sign in to your account</p>
          </div>

          <div className="hidden lg:block mb-10">
            <h2 className="text-3xl font-bold text-slate-900 dark:text-white mb-2">Create an account</h2>
            <p className="text-slate-500 dark:text-slate-400">Already have an account? <span className="text-blue-600 dark:text-blue-400 cursor-pointer font-medium hover:underline">Log in</span></p>
          </div>

          {errorMsg && (
            <div className="mb-6 p-4 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border border-red-200 dark:border-red-800/30 font-medium">
              {errorMsg}
            </div>
          )}

          <form onSubmit={handleEmailLogin} className="space-y-5 mb-8">
            <div className="space-y-1">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 px-1">Email address</label>
              <input
                type="email"
                required
                placeholder="name@curefoods.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="w-full px-4 py-3.5 bg-white dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-all text-slate-900 dark:text-white"
              />
            </div>
            
            <div className="space-y-1">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300 px-1">Password</label>
              <input
                type="password"
                required
                placeholder="Enter your password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full px-4 py-3.5 bg-white dark:bg-slate-900/50 border border-slate-200 dark:border-slate-800 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40 focus:border-blue-500 transition-all text-slate-900 dark:text-white"
              />
            </div>

            <div className="pt-2">
              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full flex items-center justify-center py-4 px-6 rounded-xl bg-[#6366f1] hover:bg-[#4f46e5] disabled:opacity-70 text-white font-semibold text-sm transition-all duration-200 shadow-lg shadow-indigo-500/25 active:scale-[0.98]"
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
                       bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 font-semibold text-sm
                       transition-all duration-200 border border-slate-200 dark:border-slate-700 shadow-sm
                       active:scale-[0.98]"
          >
            <Globe size={18} className="text-blue-500" />
            Google
          </button>

          <p className="text-center text-xs text-slate-400 mt-12">
            By signing in, you agree to our Terms of Service and Privacy Policy.<br/>
            Access restricted to Curefoods internal team.
          </p>
        </div>
      </div>
    </div>
  )
}

// src/app/forgot-password/page.tsx
'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, CheckCircle, ShieldAlert } from 'lucide-react'
import { supabase } from '@/lib/supabase'

export default function ForgotPasswordPage() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [errorMsg, setErrorMsg] = useState('')
  const [successMsg, setSuccessMsg] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setErrorMsg('')
    setSuccessMsg('')
    setIsSubmitting(true)

    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/reset-password`,
      })

      if (error) throw error

      setSuccessMsg('Password reset link sent! Check your email.')
      setEmail('')
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to send reset link.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-slate-50 dark:bg-[#0a0f1c]">
      <div className="w-full max-w-md space-y-8 bg-white dark:bg-slate-900 p-8 rounded-2xl shadow-xl border border-slate-200 dark:border-slate-800">
        
        <div className="text-center mb-8">
          <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Reset Password</h2>
          <p className="text-slate-500 dark:text-slate-400 mt-2 text-sm">Enter your email and we will send you a link to reset your password.</p>
        </div>

        {errorMsg && (
          <div className="p-4 rounded-xl bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 text-sm border border-red-200 dark:border-red-500/20 flex items-start gap-3">
            <ShieldAlert className="w-5 h-5 shrink-0" />
            <p className="mt-0.5">{errorMsg}</p>
          </div>
        )}

        {successMsg && (
          <div className="p-4 rounded-xl bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-sm border border-emerald-200 dark:border-emerald-500/20 flex items-start gap-3">
            <CheckCircle className="w-5 h-5 shrink-0" />
            <p className="mt-0.5">{successMsg}</p>
          </div>
        )}

        <form onSubmit={handleResetPassword} className="space-y-6">
          <div className="space-y-2 group">
            <label htmlFor="email" className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Email Address
            </label>
            <input
              id="email"
              type="email"
              required
              placeholder="name@curefoods.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              className="w-full px-4 py-3 bg-slate-50 dark:bg-[#111827] border border-slate-200 dark:border-slate-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all text-slate-900 dark:text-white"
            />
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full bg-[#011B4D] hover:bg-[#02266b] disabled:bg-slate-400 dark:disabled:bg-slate-700 text-white font-medium py-3 rounded-lg transition-colors flex justify-center items-center gap-2"
          >
            {isSubmitting ? 'Sending...' : 'Send Reset Link'}
          </button>
        </form>

        <div className="pt-4 text-center">
          <button
            onClick={() => router.push('/login')}
            className="inline-flex items-center gap-2 text-sm font-medium text-slate-500 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" /> Back to Login
          </button>
        </div>
      </div>
    </div>
  )
}

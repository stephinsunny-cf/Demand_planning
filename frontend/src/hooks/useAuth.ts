// src/hooks/useAuth.ts
'use client'
import { useState, useEffect, useCallback } from 'react'
import { supabase } from '@/lib/supabase'

export interface AuthUser {
  id: string
  email: string
  role: string
}

export function useAuth() {
  const [user, setUser]       = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (process.env.NEXT_PUBLIC_DEMO_MODE === 'true') {
      const demoToken = localStorage.getItem('sb-token')
      if (demoToken) {
        setUser({ id: 'mock_user', email: 'admin@curefoods.in', role: 'super_admin' })
      }
      setLoading(false)
      return
    }

    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) {
        let role = session.user.user_metadata?.role || 'viewer'
        if (process.env.NEXT_PUBLIC_ADMIN_EMAIL && session.user.email?.toLowerCase() === process.env.NEXT_PUBLIC_ADMIN_EMAIL.toLowerCase()) {
          role = 'super_admin'
        }
        const token = session.access_token
        localStorage.setItem('sb-token', token)
        document.cookie = `sb-token=${token}; path=/; max-age=86400; SameSite=Lax`
        setUser({ id: session.user.id, email: session.user.email!, role })
      }
      setLoading(false)
    })

    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.user) {
        let role = session.user.user_metadata?.role || 'viewer'
        if (process.env.NEXT_PUBLIC_ADMIN_EMAIL && session.user.email?.toLowerCase() === process.env.NEXT_PUBLIC_ADMIN_EMAIL.toLowerCase()) {
          role = 'super_admin'
        }
        localStorage.setItem('sb-token', session.access_token)
        document.cookie = `sb-token=${session.access_token}; path=/; max-age=86400; SameSite=Lax`
        setUser({ id: session.user.id, email: session.user.email!, role })
      }
    })

    return () => listener.subscription.unsubscribe()
  }, [])

  const signInWithGoogle = useCallback(async () => {
    if (process.env.NEXT_PUBLIC_DEMO_MODE === 'true') return
    await supabase.auth.signInWithOAuth({ provider: 'google' })
  }, [])

  const signInWithEmail = useCallback(async (email: string, password: string) => {
    if (process.env.NEXT_PUBLIC_DEMO_MODE === 'true') {
      const demoToken = 'mock-token'
      localStorage.setItem('sb-token', demoToken)
      document.cookie = `sb-token=${demoToken}; path=/; max-age=86400; SameSite=Lax`
      setUser({ id: 'mock_user', email, role: 'super_admin' })
      return
    }
    const { data, error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) throw error
    
    // Explicitly set the token here to avoid a race condition with onAuthStateChange
    // which can cause the profile fetch to trigger a 401 and redirect back to login.
    if (data?.session) {
      localStorage.setItem('sb-token', data.session.access_token)
      document.cookie = `sb-token=${data.session.access_token}; path=/; max-age=86400; SameSite=Lax`
    }
  }, [])

  const signOut = useCallback(async () => {
    if (process.env.NEXT_PUBLIC_DEMO_MODE === 'true') {
      setUser(null)
      localStorage.removeItem('sb-token')
      document.cookie = 'sb-token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT'
      return
    }
    await supabase.auth.signOut()
    setUser(null)
    localStorage.removeItem('sb-token')
    document.cookie = 'sb-token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT'
  }, [])

  return { user, loading, signInWithGoogle, signInWithEmail, signOut }
}

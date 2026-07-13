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
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) {
        const role = session.user.user_metadata?.role || 'demand_planner'
        const token = session.access_token
        localStorage.setItem('sb-token', token)
        setUser({ id: session.user.id, email: session.user.email!, role })
      }
      setLoading(false)
    })

    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.user) {
        const role = session.user.user_metadata?.role || 'demand_planner'
        localStorage.setItem('sb-token', session.access_token)
        setUser({ id: session.user.id, email: session.user.email!, role })
      } else {
        setUser(null)
        localStorage.removeItem('sb-token')
      }
    })

    return () => listener.subscription.unsubscribe()
  }, [])

  const signInWithGoogle = useCallback(async () => {
    await supabase.auth.signInWithOAuth({ provider: 'google' })
  }, [])

  const signInWithEmail = useCallback(async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) throw error
  }, [])

  const signOut = useCallback(async () => {
    await supabase.auth.signOut()
    setUser(null)
    localStorage.removeItem('sb-token')
  }, [])

  return { user, loading, signInWithGoogle, signInWithEmail, signOut }
}

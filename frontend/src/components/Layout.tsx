// src/components/Layout.tsx
'use client'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Sidebar from './Sidebar'
import Header  from './Header'
import { useAuth } from '@/hooks/useAuth'
import LoadingSpinner from './LoadingSpinner'

interface Props {
  title:    string
  children: React.ReactNode
}

export default function Layout({ title, children }: Props) {
  const { user, loading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!loading) {
      if (!user) {
        router.push('/login')
      } else {
        // Enforce must_reset_password safety net across the entire app
        import('@/lib/api').then(({ default: api }) => {
          api.get('/api/auth/profile').then(res => {
            if (res.data?.must_reset_password) {
              router.push('/reset-password')
            }
          }).catch(err => {
            console.warn('Could not fetch profile in Layout', err)
          })
        })
      }
    }
  }, [user, loading, router])

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center">
        <LoadingSpinner />
      </div>
    )
  }

  if (!user) return null

  return (
    <div className="h-screen overflow-hidden flex bg-white dark:bg-slate-950 text-slate-900 dark:text-white transition-colors">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 bg-white dark:bg-slate-950 overflow-hidden">
        <Header title={title} />
        <main className="flex-1 p-6 sm:px-10 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  )
}

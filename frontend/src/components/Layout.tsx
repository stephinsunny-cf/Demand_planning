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

  const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === 'true'

  useEffect(() => {
    if (!DEMO_MODE && !loading && !user) {
      router.push('/login')
    }
  }, [user, loading, router, DEMO_MODE])

  if (!DEMO_MODE && loading) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center">
        <LoadingSpinner />
      </div>
    )
  }

  if (!DEMO_MODE && !user) return null

  return (
    <div className="min-h-screen flex bg-white dark:bg-slate-950 text-slate-900 dark:text-white transition-colors">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 bg-white dark:bg-slate-950">
        <Header title={title} />
        <main className="flex-1 p-6 sm:px-10 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  )
}

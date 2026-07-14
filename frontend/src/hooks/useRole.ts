// src/hooks/useRole.ts
'use client'
import { useAuth } from './useAuth'

const ROLE_ACCESS: Record<string, string[]> = {
  super_admin: ['*'],
  editor:      ['dashboard', 'sales', 'forecast', 'supply', 'warehouse', 'procurement', 'alerts', 'reports', 'recipes'],
  viewer:      ['dashboard', 'reports', 'alerts'],
}

export function useRole() {
  const { user, loading } = useAuth()
  const role = user?.role || ''

  const canAccess = (page: string): boolean => {
    if (!role) return false
    const pages = ROLE_ACCESS[role] || []
    return pages.includes('*') || pages.includes(page)
  }

  const isAdmin      = role === 'super_admin'
  const canEdit      = ['super_admin', 'editor'].includes(role)
  const canProcure   = ['super_admin', 'editor'].includes(role)

  return { role, canAccess, isAdmin, canEdit, canProcure, loading }
}

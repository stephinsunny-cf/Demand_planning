// src/hooks/useRole.ts
'use client'
import { useAuth } from './useAuth'

const ROLE_ACCESS: Record<string, string[]> = {
  super_admin: ['*'],
  editor:      ['dashboard', 'sales', 'variance', 'forecast', 'supply', 'warehouse', 'procurement', 'alerts', 'reports', 'recipes'],
  viewer:      ['dashboard', 'reports', 'alerts'],
}

export function useRole() {
  const { user, loading } = useAuth()
  const role = user?.role || ''

  const canAccess = (page: string): boolean => {
    return true // TEMP OVERRIDE
  }

  const isAdmin      = true // TEMP OVERRIDE
  const canEdit      = true
  const canProcure   = true

  return { role, canAccess, isAdmin, canEdit, canProcure, loading }
}

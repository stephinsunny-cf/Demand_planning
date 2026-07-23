import { useAuth } from './useAuth';

export type UserRole = 'reader' | 'editor' | 'admin' | 'super_admin';

export function usePermission() {
  const { user } = useAuth();
  const role = (user?.role || 'reader').toLowerCase() as UserRole;

  const isSuperAdmin = role === 'super_admin';
  const isAdmin = role === 'admin' || isSuperAdmin;
  const isEditor = role === 'editor' || isAdmin;
  const isReader = role === 'reader';

  return {
    role,
    isReader,
    canEdit: isEditor,
    canAdmin: isAdmin,
    isSuperAdmin,
    canTriggerPipeline: isAdmin,
    canManageUsers: isAdmin,
    canEscalateAdmin: isSuperAdmin,
  };
}

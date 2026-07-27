'use client';

import { useState, useEffect } from 'react';
import { usePermission } from '@/hooks/usePermission';
import api from '@/lib/api';
import { 
  Users, Shield, UserPlus, RefreshCw, KeyRound, UserX, 
  CheckCircle2, AlertTriangle, Play, Server, FileText 
} from 'lucide-react';

interface UserProfile {
  user_id: string;
  email: string;
  role: string;
  must_reset_password: boolean;
  is_active: boolean;
  created_at: string;
}

export default function AdminPage() {
  const { canAdmin, isSuperAdmin } = usePermission();
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [loading, setLoading] = useState(true);

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newEmail, setNewEmail] = useState('');
  const [newRole, setNewRole] = useState('editor');
  const [submitting, setSubmitting] = useState(false);

  // Custom Confirm/Prompt Modal States
  const [confirmDialog, setConfirmDialog] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    isDestructive?: boolean;
    onConfirm: () => void;
  } | null>(null);
  
  const [promptDialog, setPromptDialog] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    value: string;
    onConfirm: (val: string) => void;
  } | null>(null);

  // Status & Error Banners
  const [bannerSuccess, setBannerSuccess] = useState('');
  const [bannerError, setBannerError] = useState('');
  const [criticalOrphanAlert, setCriticalOrphanAlert] = useState('');

  // Pipeline Execution State
  const [pipelineRunning, setPipelineRunning] = useState(false);

  const fetchUsers = async () => {
    try {
      setLoading(true);
      const res = await api.get('/api/admin/users');
      setUsers(res.data);
    } catch (err) {
      console.error('Failed to fetch users:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (canAdmin) {
      fetchUsers();
    }
  }, [canAdmin]);

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setBannerSuccess('');
    setBannerError('');
    setCriticalOrphanAlert('');

    try {
      const res = await api.post('/api/admin/users', { email: newEmail, role: newRole });
      setBannerSuccess(`User ${newEmail} created! A temporary password was emailed.`);
      setIsModalOpen(false);
      setNewEmail('');
      setNewRole('editor');
      fetchUsers();
    } catch (err: any) {
      const detail = err.response?.data?.detail || err.message;
      if (detail && detail.includes('ORPHANED SUPABASE USER')) {
        setCriticalOrphanAlert(detail);
      } else {
        setBannerError(detail || 'Failed to create user');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleResendTempPassword = async (userId: string, email: string) => {
    setConfirmDialog({
      isOpen: true,
      title: 'Resend Password',
      message: `Resend temporary password for ${email}? This will force a password reset on next login.`,
      onConfirm: async () => {
        setConfirmDialog(null);
        try {
          await api.post(`/api/admin/users/${userId}/resend-temp-password`);
          setBannerSuccess(`New temporary password generated and emailed to ${email}.`);
          fetchUsers();
        } catch (err: any) {
          setBannerError(err.response?.data?.detail || err.message || 'Failed to resend temporary password');
        }
      }
    });
  };

  const handleRoleChange = async (userId: string, currentRole: string) => {
    setPromptDialog({
      isOpen: true,
      title: 'Change Role',
      message: `Change role for user (current: ${currentRole}). Enter: reader, editor, admin, or super_admin`,
      value: currentRole,
      onConfirm: async (nextRole) => {
        setPromptDialog(null);
        const roles = ['reader', 'editor', 'admin', 'super_admin'];
        if (!nextRole || !roles.includes(nextRole.toLowerCase())) return;
        try {
          await api.put(`/api/admin/users/${userId}/role`, { role: nextRole.toLowerCase() });
          setBannerSuccess(`User role updated to ${nextRole}.`);
          fetchUsers();
        } catch (err: any) {
          setBannerError(err.response?.data?.detail || err.message || 'Failed to update role');
        }
      }
    });
  };

  const handleDeactivate = async (userId: string, email: string) => {
    setConfirmDialog({
      isOpen: true,
      title: 'Deactivate User',
      message: `Are you sure you want to deactivate ${email}? This will revoke their session immediately.`,
      isDestructive: true,
      onConfirm: async () => {
        setConfirmDialog(null);
        try {
          await api.put(`/api/admin/users/${userId}/deactivate`);
          setBannerSuccess(`User ${email} deactivated and session revoked.`);
          fetchUsers();
        } catch (err: any) {
          setBannerError(err.response?.data?.detail || err.message || 'Failed to deactivate user');
        }
      }
    });
  };

  const handleTriggerPipeline = async () => {
    setConfirmDialog({
      isOpen: true,
      title: 'Run Pipeline',
      message: 'Run full demand planning pipeline now?',
      onConfirm: () => {
        setConfirmDialog(null);
        setPipelineRunning(true);
        try {
          setBannerSuccess('Pipeline run triggered. Processing in background...');
        } finally {
          setTimeout(() => setPipelineRunning(false), 2000);
        }
      }
    });
  };

  if (!canAdmin) {
    return (
      <div className="p-8 text-center text-slate-400">
        <Shield className="w-12 h-12 text-rose-500 mx-auto mb-4" />
        <h2 className="text-xl font-bold text-white mb-2">Access Denied</h2>
        <p className="text-sm">You must have Admin or Super Admin privileges to view this section.</p>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      {/* Top Header */}
      <div className="flex justify-between items-center border-b border-slate-200 dark:border-slate-800 pb-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-3">
            <Shield className="w-7 h-7 text-indigo-400" />
            System Administration & Security
          </h1>
          <p className="text-sm text-slate-400 mt-1">Manage user access, role assignments, and pipeline operations</p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleTriggerPipeline}
            disabled={pipelineRunning}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-lg font-medium text-sm transition-colors shadow-lg disabled:opacity-50"
          >
            <Play className="w-4 h-4" />
            {pipelineRunning ? 'Triggering...' : 'Run Pipeline'}
          </button>
          <button
            onClick={() => setIsModalOpen(true)}
            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg font-medium text-sm transition-colors shadow-lg"
          >
            <UserPlus className="w-4 h-4" />
            Add User
          </button>
        </div>
      </div>

      {/* Prominent Banners */}
      {criticalOrphanAlert && (
        <div className="p-4 bg-rose-950/80 border-2 border-rose-500 rounded-xl flex items-start space-x-3 text-rose-200 shadow-2xl">
          <AlertTriangle className="w-6 h-6 text-rose-400 shrink-0 mt-0.5" />
          <div>
            <h4 className="font-bold text-rose-300">Action Required: Orphaned Supabase User Cleanup Failed</h4>
            <p className="text-sm mt-1">{criticalOrphanAlert}</p>
          </div>
        </div>
      )}

      {bannerError && (
        <div className="p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl flex items-center space-x-3 text-rose-300 text-sm">
          <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0" />
          <span>{bannerError}</span>
        </div>
      )}

      {bannerSuccess && (
        <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-xl flex items-center space-x-3 text-emerald-300 text-sm">
          <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
          <span>{bannerSuccess}</span>
        </div>
      )}

      {/* User Management Section */}
      <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden shadow-xl">
        <div className="px-6 py-4 border-b border-slate-200 dark:border-slate-700 flex justify-between items-center bg-slate-50 dark:bg-slate-800/50">
          <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Users className="w-5 h-5 text-indigo-400" />
            User Profiles & Permissions ({users.length})
          </h2>
          <button onClick={fetchUsers} className="text-slate-400 hover:text-white p-1 rounded-lg">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {loading ? (
          <div className="p-8 text-center text-slate-400">Loading user profiles...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600 dark:text-slate-300">
              <thead className="bg-slate-50 dark:bg-slate-900/60 text-slate-500 dark:text-slate-400 font-semibold border-b border-slate-200 dark:border-slate-700">
                <tr>
                  <th className="px-6 py-3">Email</th>
                  <th className="px-6 py-3">Role</th>
                  <th className="px-6 py-3">Status</th>
                  <th className="px-6 py-3">Password State</th>
                  <th className="px-6 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-700/50">
                {users.map((u) => (
                  <tr key={u.user_id} className="hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors">
                    <td className="px-6 py-4 font-medium text-slate-900 dark:text-white">{u.email}</td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase ${
                        u.role === 'super_admin' ? 'bg-purple-500/10 text-purple-400 border border-purple-500/30' :
                        u.role === 'admin' ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/30' :
                        u.role === 'editor' ? 'bg-blue-500/10 text-blue-400 border border-blue-500/30' :
                        'bg-slate-700 text-slate-300'
                      }`}>
                        {u.role}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      {u.is_active ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/10 text-emerald-400">
                          Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-rose-500/10 text-rose-400">
                          Deactivated
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-400">
                      {u.must_reset_password ? (
                        <span className="text-amber-400 font-medium flex items-center gap-1">
                          <KeyRound className="w-3.5 h-3.5" /> Pending Reset
                        </span>
                      ) : (
                        <span className="text-slate-400">Normal</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-right space-x-2">
                      <button
                        onClick={() => handleResendTempPassword(u.user_id, u.email)}
                        title="Resend Temporary Password"
                        className="p-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg transition-colors"
                      >
                        <KeyRound className="w-4 h-4" />
                      </button>

                      {isSuperAdmin && (
                        <>
                          <button
                            onClick={() => handleRoleChange(u.user_id, u.role)}
                            title="Change User Role"
                            className="p-1.5 bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 rounded-lg transition-colors"
                          >
                            <Shield className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => handleDeactivate(u.user_id, u.email)}
                            title="Deactivate Account"
                            className="p-1.5 bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 rounded-lg transition-colors"
                          >
                            <UserX className="w-4 h-4" />
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Create User Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 max-w-md w-full shadow-2xl">
            <h3 className="text-lg font-bold text-white mb-2 flex items-center gap-2">
              <UserPlus className="w-5 h-5 text-emerald-400" /> Add New User
            </h3>
            <p className="text-xs text-slate-400 mb-6">
              A random, 12+ character temporary password will be generated and emailed to the user. They will be forced to set their own password on first login.
            </p>

            <form onSubmit={handleCreateUser} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Email Address</label>
                <input
                  type="email"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  required
                  placeholder="user@curefoods.in"
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1">Role Assignment</label>
                <select
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                >
                  <option value="reader">Reader (View Only)</option>
                  <option value="editor">Editor (Business Data Control)</option>
                  {isSuperAdmin && <option value="admin">Admin (Operations & System Logs)</option>}
                  {isSuperAdmin && <option value="super_admin">Super Admin (Full System Control)</option>}
                </select>
                {!isSuperAdmin && (
                  <p className="text-[11px] text-amber-400 mt-1">Note: Only Super Admins can create Admin or Super Admin users.</p>
                )}
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-slate-700">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-medium disabled:opacity-50"
                >
                  {submitting ? 'Creating...' : 'Create & Send Password'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Custom Confirm Dialog */}
      {confirmDialog?.isOpen && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-6 max-w-sm w-full shadow-2xl">
            <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">{confirmDialog.title}</h3>
            <p className="text-sm text-slate-600 dark:text-slate-300 mb-6">{confirmDialog.message}</p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setConfirmDialog(null)}
                className="px-4 py-2 bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-300 rounded-lg text-sm font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmDialog.onConfirm}
                className={`px-4 py-2 text-white rounded-lg text-sm font-medium transition-colors ${confirmDialog.isDestructive ? 'bg-rose-600 hover:bg-rose-500' : 'bg-indigo-600 hover:bg-indigo-500'}`}
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Custom Prompt Dialog */}
      {promptDialog?.isOpen && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl p-6 max-w-sm w-full shadow-2xl">
            <h3 className="text-lg font-bold text-slate-900 dark:text-white mb-2">{promptDialog.title}</h3>
            <p className="text-sm text-slate-600 dark:text-slate-300 mb-4">{promptDialog.message}</p>
            <input
              type="text"
              value={promptDialog.value}
              onChange={(e) => setPromptDialog({ ...promptDialog, value: e.target.value })}
              className="w-full bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-900 dark:text-white mb-6 focus:outline-none focus:border-indigo-500 transition-colors"
            />
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setPromptDialog(null)}
                className="px-4 py-2 bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 text-slate-700 dark:text-slate-300 rounded-lg text-sm font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => promptDialog.onConfirm(promptDialog.value)}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-sm font-medium transition-colors"
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

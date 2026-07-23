'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Lock, CheckCircle, AlertCircle, KeyRound, ShieldAlert } from 'lucide-react';

export default function ResetPasswordPage() {
  const router = useRouter();
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  // Password complexity rules
  const hasMinLength = newPassword.length >= 12;
  const hasUpper = /[A-Z]/.test(newPassword);
  const hasLower = /[a-z]/.test(newPassword);
  const hasDigit = /[0-9]/.test(newPassword);
  const hasSymbol = /[!@#$%^&*]/.test(newPassword);
  const passwordsMatch = newPassword.length > 0 && newPassword === confirmPassword;

  const isFormValid = hasMinLength && hasUpper && hasLower && hasDigit && hasSymbol && passwordsMatch;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isFormValid) return;

    setLoading(true);
    setError('');

    try {
      const res = await fetch('http://localhost:8000/api/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_password: newPassword }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Password reset failed.');
      }

      setSuccess(true);
      setTimeout(() => {
        router.push('/dashboard');
      }, 1500);
    } catch (err: any) {
      setError(err.message || 'Failed to update password.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-slate-800 rounded-xl border border-slate-700 p-8 shadow-2xl">
        <div className="flex items-center space-x-3 mb-6">
          <div className="p-3 bg-amber-500/10 rounded-lg border border-amber-500/20">
            <KeyRound className="w-6 h-6 text-amber-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">Password Reset Required</h1>
            <p className="text-sm text-slate-400">Set your permanent password to continue</p>
          </div>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-rose-500/10 border border-rose-500/30 rounded-lg flex items-start space-x-3">
            <ShieldAlert className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
            <p className="text-sm text-rose-300">{error}</p>
          </div>
        )}

        {success && (
          <div className="mb-6 p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-lg flex items-start space-x-3">
            <CheckCircle className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
            <p className="text-sm text-emerald-300">Password updated successfully! Redirecting...</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">New Password</label>
            <div className="relative">
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                placeholder="••••••••••••"
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-2.5 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 text-sm"
              />
              <Lock className="w-4 h-4 text-slate-500 absolute right-3 top-3" />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-300 mb-1.5">Confirm New Password</label>
            <div className="relative">
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                placeholder="••••••••••••"
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-2.5 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 text-sm"
              />
              <Lock className="w-4 h-4 text-slate-500 absolute right-3 top-3" />
            </div>
          </div>

          {/* Password Complexity Checklist */}
          <div className="bg-slate-900/50 p-4 rounded-lg border border-slate-700/50 space-y-2 text-xs">
            <p className="font-semibold text-slate-400 mb-2">Password Requirements:</p>
            <div className="grid grid-cols-2 gap-2">
              <div className={`flex items-center space-x-1.5 ${hasMinLength ? 'text-emerald-400' : 'text-slate-500'}`}>
                <CheckCircle className="w-3.5 h-3.5" />
                <span>At least 12 characters</span>
              </div>
              <div className={`flex items-center space-x-1.5 ${hasUpper ? 'text-emerald-400' : 'text-slate-500'}`}>
                <CheckCircle className="w-3.5 h-3.5" />
                <span>Uppercase letter</span>
              </div>
              <div className={`flex items-center space-x-1.5 ${hasLower ? 'text-emerald-400' : 'text-slate-500'}`}>
                <CheckCircle className="w-3.5 h-3.5" />
                <span>Lowercase letter</span>
              </div>
              <div className={`flex items-center space-x-1.5 ${hasDigit ? 'text-emerald-400' : 'text-slate-500'}`}>
                <CheckCircle className="w-3.5 h-3.5" />
                <span>Numeric digit</span>
              </div>
              <div className={`flex items-center space-x-1.5 ${hasSymbol ? 'text-emerald-400' : 'text-slate-500'}`}>
                <CheckCircle className="w-3.5 h-3.5" />
                <span>Symbol (!@#$%^&*)</span>
              </div>
              <div className={`flex items-center space-x-1.5 ${passwordsMatch ? 'text-emerald-400' : 'text-slate-500'}`}>
                <CheckCircle className="w-3.5 h-3.5" />
                <span>Passwords match</span>
              </div>
            </div>
          </div>

          <button
            type="submit"
            disabled={!isFormValid || loading}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-700 disabled:text-slate-500 text-white font-medium py-2.5 rounded-lg transition-colors duration-150 text-sm shadow-lg"
          >
            {loading ? 'Updating Password...' : 'Save New Password & Continue'}
          </button>
        </form>
      </div>
    </div>
  );
}

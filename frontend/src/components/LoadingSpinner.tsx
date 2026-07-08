// src/components/LoadingSpinner.tsx
import React from 'react'

export default function LoadingSpinner({ message = "Loading data..." }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] w-full gap-4 animate-fade-in">
      <div className="relative flex items-center justify-center">
        {/* Outer ringing pulse */}
        <div className="absolute w-16 h-16 rounded-full border-4 border-emerald-500/20 animate-ping"></div>
        {/* Inner spinning ring */}
        <div className="w-12 h-12 rounded-full border-4 border-slate-200 dark:border-slate-800 border-t-emerald-500 animate-spin"></div>
      </div>
      <p className="text-sm font-medium text-slate-500 dark:text-slate-400 animate-pulse">{message}</p>
    </div>
  )
}

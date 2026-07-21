// src/app/reports/page.tsx
'use client'
import { useState, useEffect } from 'react'
import Layout from '@/components/Layout'
import LoadingSpinner from '@/components/LoadingSpinner'
import api from '@/lib/api'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Cell,
} from 'recharts'
import { FileText } from 'lucide-react'

import useSWR from 'swr'

const fetcher = (url: string) => api.get(url).then(res => res.data)

export default function ReportsPage() {
  const [days, setDays] = useState(90)

  const swrOptions = { revalidateOnFocus: false, revalidateOnReconnect: false }
  const { data: accuracy } = useSWR<any[]>(`/api/reports/accuracy?days=${days}`, fetcher, swrOptions)
  const { data: stockouts } = useSWR<any[]>(`/api/reports/stockouts?days=${days}`, fetcher, swrOptions)
  const { data: wastage } = useSWR<any[]>(`/api/reports/wastage?days=${days}`, fetcher, swrOptions)
  const { data: vendor } = useSWR<any[]>('/api/reports/vendor', fetcher, swrOptions)

  const loading = !accuracy || !stockouts || !wastage || !vendor

  const COLORS = ['#34d399', '#60a5fa', '#a78bfa', '#f59e0b', '#f87171']

  return (
    <Layout title="Reports">
      {/* Controls */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex rounded-lg overflow-hidden border border-slate-300 dark:border-slate-700">
          {[30, 60, 90].map(d => (
            <button key={d} onClick={() => setDays(d)}
              className={`px-4 py-1.5 text-sm font-medium transition-colors
                ${days === d ? 'bg-emerald-500 text-slate-900 dark:text-white' : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:bg-slate-700'}`}>
              {d} days
            </button>
          ))}
        </div>
        <button
          onClick={() => window.print()}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 hover:bg-slate-700
                     text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:text-white border border-slate-300 dark:border-slate-700 text-sm font-medium transition-all"
        >
          <FileText size={14} />
          Download PDF
        </button>
      </div>

      {loading ? <LoadingSpinner /> : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          {/* Chart 1: Forecast Accuracy */}
          <div className="card p-6 rounded-2xl">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-1">Forecast Accuracy</h3>
            <p className="text-xs text-slate-500 mb-4">Target: 80% · Dashed line = target</p>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={accuracy}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="week" tick={{ fill: '#64748b', fontSize: 10 }} tickFormatter={v => String(v).slice(5)} />
                <YAxis domain={[50, 100]} tick={{ fill: '#64748b', fontSize: 11 }} unit="%" />
                <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }} />
                <ReferenceLine y={80} stroke="#34d399" strokeDasharray="4 4" label={{ value: '80% target', fill: '#34d399', fontSize: 10 }} />
                <Line type="monotone" dataKey="accuracy" stroke="#818cf8" strokeWidth={2} dot={{ r: 3, fill: '#818cf8' }} name="Accuracy %" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Chart 2: Stockout Incidents */}
          <div className="card p-6 rounded-2xl">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-1">Stock-out Incidents per Week</h3>
            <p className="text-xs text-slate-500 mb-4">Lower is better</p>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={stockouts}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="week" tick={{ fill: '#64748b', fontSize: 10 }} tickFormatter={v => String(v).slice(5)} />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }} />
                <Bar dataKey="incidents" fill="#f87171" radius={[4, 4, 0, 0]} name="Incidents" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Chart 3: Top Ingredients Causing Shortages */}
          <div className="card p-6 rounded-2xl">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-1">Top Ingredients Causing Shortages</h3>
            <p className="text-xs text-slate-500 mb-4">Potential wastage = received − ordered</p>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={wastage.slice(0, 10)} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} />
                <YAxis dataKey="ingredient" type="category" tick={{ fill: '#94a3b8', fontSize: 10 }} width={100} />
                <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }} />
                <Bar dataKey="potential_wastage" name="Wastage" radius={[0, 4, 4, 0]}>
                  {wastage.slice(0, 10).map((_, index) => (
                    <Cell key={index} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Chart 4: Vendor On-Time Delivery */}
          <div className="card p-6 rounded-2xl">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-1">Vendor On-Time Delivery</h3>
            <p className="text-xs text-slate-500 mb-4">% of deliveries on or before expected date</p>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={vendor}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="vendor" tick={{ fill: '#64748b', fontSize: 10 }} />
                <YAxis domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 11 }} unit="%" />
                <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }} />
                <ReferenceLine y={90} stroke="#34d399" strokeDasharray="4 4" />
                <Bar dataKey="on_time_pct" name="On-time %" radius={[4, 4, 0, 0]}>
                  {vendor.map((r, index) => (
                    <Cell key={index} fill={Number(r.on_time_pct) >= 90 ? '#34d399' : Number(r.on_time_pct) >= 75 ? '#f59e0b' : '#f87171'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </Layout>
  )
}

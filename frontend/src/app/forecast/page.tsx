// src/app/forecast/page.tsx
'use client'
import { useState, useEffect } from 'react'
import Layout from '@/components/Layout'
import DataTable from '@/components/DataTable'
import ExportButton from '@/components/ExportButton'
import MultiSelect from '@/components/MultiSelect'
import SingleSelect from '@/components/SingleSelect'
import LoadingSpinner from '@/components/LoadingSpinner'
import api from '@/lib/api'

export default function ForecastPage() {
  const [allForecasts,      setAllForecasts]    = useState<Record<string, unknown>[]>([])
  
  // Filter lists from API
  const [allLocations,      setAllLocations]      = useState<string[]>([])
  const [locationOutlets,   setLocationOutlets]   = useState<Record<string, string[]>>({})
  
  // Selected state
  const [selectedLocations, setSelectedLocations] = useState<string[]>([])
  const [selectedOutlets,   setSelectedOutlets]   = useState<string[]>([])
  const [skuSearch,         setSkuSearch]         = useState('')
  const [forecastDays,      setForecastDays]      = useState(7)
  const [isLoading,         setIsLoading]         = useState(true)

  // Load filter metadata
  useEffect(() => {
    api.get('/api/forecast/filters').then(r => {
      const data = r.data as { city: string, outlets: string[] }[]
      const locs = data.map(d => d.city).filter(Boolean).sort()
      const outMap: Record<string, string[]> = {}
      data.forEach(d => {
        if (d.city) outMap[d.city] = d.outlets.sort()
      })
      setAllLocations(locs)
      setLocationOutlets(outMap)
    }).catch(console.error)
  }, [])

  const fetchData = () => {
    setIsLoading(true)
    const params = new URLSearchParams()
    if (selectedLocations.length > 0) params.set('locations', selectedLocations.join(','))
    if (selectedOutlets.length > 0) params.set('outlets', selectedOutlets.join(','))
    params.set('days', forecastDays.toString())
    
    api.get(`/api/forecast/all?${params}`).then(r => {
      const rows = r.data as Record<string, unknown>[]
      const totalVolume = rows.reduce((sum, row) => sum + Number(row.total_predicted || 0), 0)
      const enrichedRows = rows.map(row => ({
        ...row,
        display_sku: row.sku_code ? `${row.sku} (${row.sku_code})` : row.sku,
        location: row.mapped_city ? String(row.mapped_city) : String(row.outlet).split(' - ')[0].trim(),
        percentage: totalVolume > 0
          ? ((Number(row.total_predicted) / totalVolume) * 100).toFixed(2)
          : '0.00',
      }))
      setAllForecasts(enrichedRows)
      setIsLoading(false)
    }).catch(e => {
      console.error(e)
      setIsLoading(false)
    })
  }

  // Load initial data and auto-reload on forecastDays change
  useEffect(() => { fetchData() }, [forecastDays])

  // Derived outlets for cascaded filter
  const outletsForLocation = selectedLocations.length === 0
    ? Object.values(locationOutlets).flat().sort()
    : selectedLocations.flatMap(loc => locationOutlets[loc] || []).sort()

  const handleLocationChange = (locs: string[]) => {
    setSelectedLocations(locs)
    setSelectedOutlets([])
  }

  // Final client-side filter for SKU search (to avoid refetching on every keystroke)
  const filteredForecasts = allForecasts
    .filter(r => skuSearch === '' || String(r.sku).toLowerCase().includes(skuSearch.toLowerCase()))
    .sort((a, b) => Number(b.total_predicted) - Number(a.total_predicted))

  return (
    <Layout title="Forecast Explorer">
      <div className="space-y-4 animate-fade-in">
        {/* Filter Bar */}
        <div className="relative z-20 card p-4 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900">
          <div className="flex flex-wrap items-end gap-4">

            {/* Location */}
            <div className="flex flex-col gap-1 min-w-[220px] max-w-[260px]">
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Location</label>
              <MultiSelect 
                options={allLocations} 
                selected={selectedLocations} 
                onChange={handleLocationChange} 
                placeholder="All Locations" 
              />
            </div>

            {/* Outlet (cascaded) */}
            <div className="flex flex-col gap-1 min-w-[280px] max-w-[320px]">
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Outlet</label>
              <MultiSelect 
                options={outletsForLocation} 
                selected={selectedOutlets} 
                onChange={setSelectedOutlets} 
                placeholder="All Outlets" 
              />
            </div>
            
            {/* Horizon Selector */}
            <div className="flex flex-col gap-1 min-w-[120px]">
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Horizon</label>
              <SingleSelect
                value={forecastDays}
                onChange={setForecastDays}
                options={[
                  { label: '7 Days', value: 7 },
                  { label: '14 Days', value: 14 },
                  { label: '30 Days', value: 30 },
                ]}
              />
            </div>
            
            {/* Apply Button */}
            <div className="flex flex-col gap-1.5 self-end">
               <button onClick={fetchData}
                 className="px-4 py-2 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-white text-sm font-medium transition-colors h-[42px] min-w-[100px] shadow-sm">
                 Apply Filters
               </button>
            </div>

            {/* Product Search */}
            <div className="flex flex-col gap-1 flex-1 min-w-[200px]">
              <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Search Product</label>
              <div className="relative">
                <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                <input
                  type="text"
                  value={skuSearch}
                  onChange={e => setSkuSearch(e.target.value)}
                  placeholder="e.g. Biryani, Idli, Meals..."
                  className="w-full pl-9 pr-4 py-2 bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg text-sm text-slate-900 dark:text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
                  style={{ height: '42px' }}
                />
              </div>
            </div>

            {/* Result count + Export */}
            <div className="flex items-center gap-3 ml-auto h-[42px]">
              <span className="text-sm text-slate-500">
                <span className="font-bold text-slate-900 dark:text-white">{filteredForecasts.length}</span> products
              </span>
              <ExportButton data={filteredForecasts} filename="forecast_filtered" sheetName="Forecast" />
            </div>
          </div>
        </div>

        {/* Data Table */}
        <div className="card p-6 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white mb-1">
            {selectedLocations.length === 0 ? 'Network-Wide' : selectedLocations.length === 1 ? selectedLocations[0] : `${selectedLocations.length} Locations`}
            {selectedOutlets.length > 0 && <span className="text-slate-500"> · {selectedOutlets.length === 1 ? selectedOutlets[0] : `${selectedOutlets.length} Outlets`}</span>}
            <span className="text-slate-500 font-normal"> — {forecastDays}-Day Forecast</span>
          </h3>
          <p className="text-xs text-slate-400 mb-4">Sorted by highest forecasted demand first</p>
          {isLoading ? (
            <LoadingSpinner message="Crunching Network Forecast..." />
          ) : (
            <DataTable
              columns={[
                { key: 'display_sku', label: 'Product SKU', sortable: true },
                { key: 'outlet', label: 'Outlet', sortable: true },
                { key: 'total_predicted', label: `${forecastDays}-Day Forecast Qty`, sortable: true, render: v => Number(v).toFixed(1) },
                { key: 'percentage', label: '% of Total Demand', sortable: true, render: v => <span className="text-emerald-500 font-medium">{v}%</span> },
              ]}
              data={filteredForecasts}
              searchable={false}
            />
          )}
        </div>
      </div>
    </Layout>
  )
}

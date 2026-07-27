// src/components/PageInfo.tsx
'use client'
import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { Info, X } from 'lucide-react'
import { usePathname } from 'next/navigation'

const PAGE_INFO: Record<string, { title: string, content: React.ReactNode }> = {
  '/': {
    title: 'Dashboard Overview',
    content: (
      <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
        <p><strong>What is this page?</strong> A high-level executive summary of demand planning health across all operations.</p>
        <p><strong>How is it calculated?</strong> Aggregates the total 3-day forecast volume, estimates current inventory value from kitchen stock, and sums active alerts.</p>
        <p><strong>Data Source:</strong> Sales data comes from UrbanPiper POS. Stock data is synchronized nightly from the ERP database.</p>
      </div>
    )
  },
  '/sales': {
    title: 'Sales Trends',
    content: (
      <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
        <p><strong>What is this page?</strong> Displays historical daily sales volume across kitchens.</p>
        <p><strong>How is it calculated?</strong> Aggregates item-level sales from POS systems by date, kitchen, and SKU.</p>
        <p><strong>Data Source:</strong> Pulled daily from UrbanPiper via background sync scripts into the PostgreSQL <code>fact_daily_sales</code> table.</p>
      </div>
    )
  },
  '/variance': {
    title: 'Forecast Variance',
    content: (
      <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
        <p><strong>What is this page?</strong> Measures how accurate our past forecasts were compared to actual sales.</p>
        <p><strong>How is it calculated?</strong> <code>Variance % = abs(Actual Sales - Forecasted Sales) / Actual Sales</code></p>
        <p><strong>Data Source:</strong> Compares the historical snapshots in <code>fact_ingredient_demand</code> with the realized sales in <code>fact_daily_sales</code>.</p>
      </div>
    )
  },
  '/forecast': {
    title: 'Demand Forecasting',
    content: (
      <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
        <p><strong>What is this page?</strong> Shows the predicted future sales for finished goods.</p>
        <p><strong>How is it calculated?</strong> Uses an Exponential Smoothing (Holt-Winters) statistical model on the last 30 days of sales history to predict the next 7 days.</p>
        <p><strong>Data Source:</strong> Calculated on the fly by the FastAPI Python backend using Pandas and stored in PostgreSQL.</p>
      </div>
    )
  },
  '/supply': {
    title: 'Supply Planning',
    content: (
      <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
        <p><strong>What is this page?</strong> Determines how much stock (ingredients) must be dispatched to each kitchen today.</p>
        <p><strong>How is it calculated?</strong> <code>Replenishment = (3-Day Forecast + Safety Stock) - Current Stock</code>.</p>
        <p><strong>Data Source:</strong> Forecasts are from the ML engine. Current stock is from the Kitchen ERP snapshot. Safety stock limits are statically defined.</p>
      </div>
    )
  },
  '/recipes': {
    title: 'Recipe & BOM Master',
    content: (
      <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
        <p><strong>What is this page?</strong> The Bill of Materials mapping finished goods to raw ingredients.</p>
        <p><strong>How is it calculated?</strong> Explodes finished product SKUs into fractional raw material quantities.</p>
        <p><strong>Data Source:</strong> Extracted and parsed automatically from the Supply Chain PPTX/Excel files uploaded by admins.</p>
      </div>
    )
  },
  '/warehouse': {
    title: 'Warehouse Stock',
    content: (
      <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
        <p><strong>What is this page?</strong> Shows the central warehouse inventory levels.</p>
        <p><strong>How is it calculated?</strong> Sums up the latest physical inventory counts for raw materials.</p>
        <p><strong>Data Source:</strong> Synchronized from the central warehouse ERP system.</p>
      </div>
    )
  },
  '/procurement': {
    title: 'Procurement Engine',
    content: (
      <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
        <p><strong>What is this page?</strong> Recommends Purchase Orders (POs) for raw materials to vendors.</p>
        <p><strong>How is it calculated?</strong> Explodes all kitchen forecasts into raw material demand using recipes, then subtracts current central warehouse stock to find the net procurement gap.</p>
        <p><strong>Data Source:</strong> Combines Forecasts, Recipes, and Warehouse Stock databases into a unified calculation.</p>
      </div>
    )
  },
  '/tracker': {
    title: 'Delivery Tracker',
    content: (
      <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
        <p><strong>What is this page?</strong> Tracks the status of inbound POs and outbound kitchen dispatches.</p>
        <p><strong>How is it calculated?</strong> Logs state transitions (e.g. Ordered, In Transit, Delivered).</p>
        <p><strong>Data Source:</strong> Updated manually by ops staff or via external logistics webhooks.</p>
      </div>
    )
  },
  '/alerts': {
    title: 'Alerts & Anomalies',
    content: (
      <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
        <p><strong>What is this page?</strong> Central inbox for automated system warnings (e.g., stockouts, missing data).</p>
        <p><strong>How is it calculated?</strong> Background cron jobs scan for edge cases (stock &lt; 0, data sync failed) and generate tickets.</p>
        <p><strong>Data Source:</strong> Generated internally by the <code>alerts_engine.py</code> background tasks.</p>
      </div>
    )
  },
  '/reports': {
    title: 'Reports & Exports',
    content: (
      <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
        <p><strong>What is this page?</strong> Downloadable Excel and CSV reports for offline analysis.</p>
        <p><strong>How is it calculated?</strong> Formats PostgreSQL views into spreadsheet-friendly formats.</p>
        <p><strong>Data Source:</strong> Direct dumps from the core data warehouse.</p>
      </div>
    )
  },
  '/admin': {
    title: 'Admin Panel',
    content: (
      <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
        <p><strong>What is this page?</strong> Configuration and manual trigger controls for the platform.</p>
        <p><strong>How is it calculated?</strong> Provides UI wrappers for internal Python scripts and file uploaders.</p>
        <p><strong>Data Source:</strong> Direct connection to system services, cron scheduler, and database triggers.</p>
      </div>
    )
  },
}

export default function PageInfo() {
  const [isOpen, setIsOpen] = useState(false)
  const pathname = usePathname()
  
  // Default fallback if route not found
  const info = PAGE_INFO[pathname] || {
    title: 'Page Information',
    content: (
      <p className="text-sm text-slate-600 dark:text-slate-300">
        This page displays data from the demand planning database.
      </p>
    )
  }

  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    setMounted(true)
  }, [])

  return (
    <>
      <button 
        onClick={() => setIsOpen(true)}
        title="Page Information"
        className="p-2 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors text-slate-500 dark:text-slate-400 focus:outline-none"
      >
        <Info size={18} />
      </button>

      {isOpen && mounted && createPortal(
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm transition-opacity">
          <div 
            className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-xl w-full max-w-md overflow-hidden transform transition-all scale-100 opacity-100"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-4 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50">
              <h3 className="font-semibold flex items-center gap-2 text-slate-900 dark:text-white">
                <Info size={18} className="text-emerald-500" />
                {info.title}
              </h3>
              <button 
                onClick={() => setIsOpen(false)}
                className="p-1.5 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-800 text-slate-400 transition-colors focus:outline-none"
              >
                <X size={18} />
              </button>
            </div>
            
            <div className="p-5">
              {info.content}
            </div>
            
            <div className="p-4 bg-slate-50 dark:bg-slate-950/50 border-t border-slate-100 dark:border-slate-800 flex justify-end">
              <button 
                onClick={() => setIsOpen(false)}
                className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium rounded-lg transition-colors focus:outline-none"
              >
                Got it
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  )
}

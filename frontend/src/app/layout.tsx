// src/app/layout.tsx
import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Demand Planning Engine — Curefoods',
  description: 'Internal demand forecasting and supply planning platform for Curefoods cloud kitchens across India.',
  keywords: 'demand planning, supply chain, forecasting, Curefoods, cloud kitchen',
}

import { ThemeProvider } from '@/components/ThemeProvider'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-white transition-colors duration-200">
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  )
}

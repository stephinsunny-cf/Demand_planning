// src/components/DatePicker.tsx
'use client'
import { useState, useRef, useEffect } from 'react'
import { Calendar as CalendarIcon, ChevronLeft, ChevronRight } from 'lucide-react'
import { 
  format, parseISO, isValid, 
  startOfMonth, endOfMonth, startOfWeek, endOfWeek, 
  eachDayOfInterval, isSameMonth, isSameDay, 
  addMonths, subMonths 
} from 'date-fns'

interface Props {
  value: string
  onChange: (val: string) => void
  label?: string
}

export default function DatePicker({ value, onChange, label }: Props) {
  const [open, setOpen] = useState(false)
  const parsed = parseISO(value)
  const displayDate = isValid(parsed) ? parsed : new Date()
  const display = isValid(parsed) ? format(parsed, 'MMM d, yyyy') : 'Select date'
  
  const [currentMonth, setCurrentMonth] = useState(displayDate)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const monthStart = startOfMonth(currentMonth)
  const monthEnd = endOfMonth(monthStart)
  const startDate = startOfWeek(monthStart)
  const endDate = endOfWeek(monthEnd)
  
  const dateFormat = "d"
  const days = eachDayOfInterval({ start: startDate, end: endDate })

  const weekDays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

  return (
    <div className="flex flex-col gap-1.5 relative" ref={ref}>
      {label && <label className="text-xs font-medium text-slate-500">{label}</label>}
      
      {/* Trigger Button */}
      <button 
        type="button"
        onClick={() => setOpen(!open)}
        className="relative flex items-center bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-lg transition-colors hover:border-slate-300 dark:hover:border-slate-700 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
      >
        <div className="pl-3 pr-2 py-2 text-slate-500 dark:text-slate-400">
          <CalendarIcon size={14} />
        </div>
        <span className="pr-3 py-2 text-sm text-slate-700 dark:text-slate-200 min-w-[110px] text-left">
          {display}
        </span>
      </button>

      {/* Popover */}
      {open && (
        <div className="absolute top-[calc(100%+0.5rem)] left-0 z-50 p-5 bg-white dark:bg-slate-900 rounded-3xl shadow-[0_12px_40px_-10px_rgba(0,0,0,0.15)] dark:shadow-[0_12px_40px_-10px_rgba(0,0,0,0.5)] border border-slate-100 dark:border-slate-800 w-[280px]">
          {/* Header */}
          <div className="flex justify-between items-center mb-6">
            <button 
              type="button"
              onClick={() => setCurrentMonth(subMonths(currentMonth, 1))}
              className="p-1.5 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 transition-colors"
            >
              <ChevronLeft size={18} />
            </button>
            <h2 className="text-sm font-bold text-slate-900 dark:text-white">
              {format(currentMonth, 'MMMM yyyy')}
            </h2>
            <button 
              type="button"
              onClick={() => setCurrentMonth(addMonths(currentMonth, 1))}
              className="p-1.5 rounded-xl border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 transition-colors"
            >
              <ChevronRight size={18} />
            </button>
          </div>

          {/* Days Header */}
          <div className="grid grid-cols-7 mb-4 gap-1">
            {weekDays.map(day => (
              <div key={day} className="text-center text-[10px] font-medium text-slate-400 dark:text-slate-500">
                {day}
              </div>
            ))}
          </div>

          {/* Calendar Grid */}
          <div className="grid grid-cols-7 gap-y-2 gap-x-1">
            {days.map((day, i) => {
              const isSelected = isValid(parsed) && isSameDay(day, parsed)
              const isCurrentMonth = isSameMonth(day, monthStart)
              
              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => {
                    onChange(format(day, 'yyyy-MM-dd'))
                    setOpen(false)
                  }}
                  className={`
                    w-8 h-8 mx-auto rounded-full flex items-center justify-center text-[13px] font-medium transition-all
                    ${!isCurrentMonth ? 'text-slate-300 dark:text-slate-600' : 'text-slate-700 dark:text-slate-200'}
                    ${isSelected 
                      ? 'bg-blue-500 text-white shadow-md shadow-blue-500/20 font-bold' 
                      : 'hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-white'}
                  `}
                >
                  {format(day, dateFormat)}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

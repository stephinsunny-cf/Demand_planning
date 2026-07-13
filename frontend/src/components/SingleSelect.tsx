import { useState, useRef, useEffect } from 'react'
import { ChevronDown, Check } from 'lucide-react'

interface SingleSelectProps {
  options: { label: string, value: number }[]
  value: number
  onChange: (value: number) => void
}

export default function SingleSelect({ options, value, onChange }: SingleSelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  const selectedOption = options.find(o => o.value === value)

  return (
    <div className="relative" ref={ref}>
      {/* Trigger Button */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between bg-white dark:bg-slate-800 border-2 border-cyan-500 rounded-xl px-4 py-2 text-sm font-medium text-slate-700 dark:text-white focus:outline-none focus:ring-4 focus:ring-cyan-500/20 transition-all shadow-sm hover:border-cyan-400"
        style={{ height: '42px' }}
      >
        <span className="truncate pr-2">{selectedOption?.label || 'Select'}</span>
        <ChevronDown size={16} className={`text-slate-500 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute z-50 mt-2 w-full min-w-[120px] bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-xl overflow-hidden animate-fade-in-up origin-top">
          <div className="max-h-60 overflow-y-auto p-1">
            {options.map(option => {
              const isSelected = option.value === value
              return (
                <label 
                  key={option.value} 
                  onClick={(e) => { 
                    e.preventDefault(); 
                    onChange(option.value); 
                    setIsOpen(false);
                  }}
                  className={`flex items-center gap-3 px-3 py-2 cursor-pointer rounded-lg transition-colors group
                  ${isSelected ? 'bg-emerald-500/10' : 'hover:bg-slate-50 dark:hover:bg-slate-700/50'}`}>
                  <div className={`flex items-center justify-center w-4 h-4 rounded-full border transition-colors
                    ${isSelected 
                      ? 'bg-emerald-500 border-emerald-500' 
                      : 'border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 group-hover:border-emerald-400'}`}>
                    {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
                  </div>
                  <span className={`text-sm ${isSelected ? 'font-medium text-emerald-700 dark:text-emerald-400' : 'text-slate-700 dark:text-slate-300'}`}>
                    {option.label}
                  </span>
                </label>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

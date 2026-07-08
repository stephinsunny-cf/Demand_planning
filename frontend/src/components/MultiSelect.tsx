import { useState, useRef, useEffect } from 'react'
import { ChevronDown, Search, Check } from 'lucide-react'

interface MultiSelectProps {
  options: string[]
  selected: string[]
  onChange: (selected: string[]) => void
  placeholder?: string
}

export default function MultiSelect({ options, selected, onChange, placeholder = "Select options" }: MultiSelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState('')
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

  const filteredOptions = options.filter(o => o.toLowerCase().includes(search.toLowerCase()))
  
  const allSelected = filteredOptions.length > 0 && filteredOptions.every(o => selected.includes(o))
  const someSelected = filteredOptions.some(o => selected.includes(o))

  const handleSelectAll = () => {
    if (allSelected) {
      // Deselect all currently filtered
      onChange(selected.filter(s => !filteredOptions.includes(s)))
    } else {
      // Select all currently filtered
      const newSelected = [...selected]
      filteredOptions.forEach(o => {
        if (!newSelected.includes(o)) newSelected.push(o)
      })
      onChange(newSelected)
    }
  }

  const toggleOption = (option: string) => {
    if (selected.includes(option)) {
      onChange(selected.filter(s => s !== option))
    } else {
      onChange([...selected, option])
    }
  }

  // Display logic
  let displayText = placeholder
  if (selected.length === 1) {
    displayText = selected[0]
  } else if (selected.length > 1) {
    displayText = `${selected.length} selected`
  }

  return (
    <div className="relative" ref={ref}>
      {/* Trigger Button */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between bg-white dark:bg-slate-800 border-2 border-cyan-500 rounded-xl px-4 py-2.5 text-sm font-medium text-slate-700 dark:text-white focus:outline-none focus:ring-4 focus:ring-cyan-500/20 transition-all shadow-sm hover:border-cyan-400"
      >
        <span className="truncate pr-2">{displayText}</span>
        <ChevronDown size={16} className={`text-slate-500 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute z-50 mt-2 w-full min-w-[240px] bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-xl overflow-hidden animate-fade-in-up origin-top">
          
          {/* Search Bar */}
          <div className="p-2 border-b border-slate-100 dark:border-slate-700">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                autoFocus
                placeholder="Search..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 text-sm bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500/30 text-slate-900 dark:text-white placeholder-slate-400"
              />
            </div>
          </div>

          <div className="max-h-60 overflow-y-auto p-1">
            {/* Select All Option */}
            {filteredOptions.length > 0 && (
              <label 
                onClick={(e) => { e.preventDefault(); handleSelectAll(); }}
                className="flex items-center gap-3 px-3 py-2 cursor-pointer rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors group">
                <div className={`flex items-center justify-center w-4 h-4 rounded border transition-colors
                  ${allSelected 
                    ? 'bg-emerald-500 border-emerald-500' 
                    : someSelected 
                      ? 'bg-emerald-500 border-emerald-500'
                      : 'border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 group-hover:border-emerald-400'}`}>
                  {(allSelected || someSelected) && <Check size={12} strokeWidth={3} className="text-white" />}
                </div>
                <span className="text-sm font-medium text-slate-900 dark:text-white">
                  {allSelected ? 'Deselect All' : 'Select All'}
                </span>
              </label>
            )}

            {/* Divider */}
            {filteredOptions.length > 0 && <div className="h-px bg-slate-100 dark:bg-slate-700 my-1 mx-2" />}

            {/* Options List */}
            {filteredOptions.length === 0 ? (
              <div className="px-3 py-4 text-center text-sm text-slate-500">No results found.</div>
            ) : (
              filteredOptions.map(option => {
                const isSelected = selected.includes(option)
                return (
                  <label 
                    key={option} 
                    onClick={(e) => { e.preventDefault(); toggleOption(option); }}
                    className={`flex items-center gap-3 px-3 py-2 cursor-pointer rounded-lg transition-colors group
                    ${isSelected ? 'bg-emerald-500/10' : 'hover:bg-slate-50 dark:hover:bg-slate-700/50'}`}>
                    <div className={`flex items-center justify-center w-4 h-4 rounded border transition-colors
                      ${isSelected 
                        ? 'bg-emerald-500 border-emerald-500' 
                        : 'border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-900 group-hover:border-emerald-400'}`}>
                      {isSelected && <Check size={12} strokeWidth={3} className="text-white" />}
                    </div>
                    <span className={`text-sm ${isSelected ? 'font-medium text-emerald-700 dark:text-emerald-400' : 'text-slate-700 dark:text-slate-300'}`}>
                      {option}
                    </span>
                  </label>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}

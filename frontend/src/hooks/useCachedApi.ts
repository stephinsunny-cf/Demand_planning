import { useState, useEffect, useCallback, useRef } from 'react'
import api from '@/lib/api'
import axios from 'axios'
import { getCached, setCached } from '@/lib/pageCache'

interface CachedApiState<T> {
  data: T | null
  loading: boolean
  isRefreshing: boolean
  error: Error | null
}

export function useCachedApi<T>(url: string | null, enabled: boolean = true) {
  const [state, setState] = useState<CachedApiState<T>>(() => {
    const cached = (url && enabled) ? getCached<T>(url) : null
    return {
      data: cached,
      loading: !cached,
      isRefreshing: false,
      error: null,
    }
  })

  // Prevent multiple inflight requests for the same URL
  const abortControllerRef = useRef<AbortController | null>(null)

  const fetchData = useCallback(async (forceRefresh = false) => {
    if (!url || !enabled) return

    // Cancel any ongoing request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    const controller = new AbortController()
    abortControllerRef.current = controller

    const cached = getCached<T>(url)
    
    setState(prev => ({
      ...prev,
      data: (cached && !forceRefresh) ? cached : prev.data,
      loading: (!cached || forceRefresh) ? true : false,
      isRefreshing: (!!cached && !forceRefresh),
      error: null
    }))

    try {
      const res = await api.get(url, { signal: controller.signal })
      setCached(url, res.data)
      
      if (!controller.signal.aborted) {
        setState({
          data: res.data,
          loading: false,
          isRefreshing: false,
          error: null
        })
      }
    } catch (err: any) {
      if (axios.isCancel(err) || err.name === 'CanceledError') {
        // Ignored
      } else if (!controller.signal.aborted) {
        setState(prev => ({ ...prev, loading: false, isRefreshing: false, error: err }))
      }
    }
  }, [url, enabled])

  useEffect(() => {
    fetchData()
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [fetchData])

  return { ...state, mutate: fetchData }
}

import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
} from 'react'
import type { ReactNode } from 'react'
import * as outbox from './outbox'
import type { OutboxEntry, SyncReport } from './outbox'

interface OfflineValue {
  online: boolean
  queue: OutboxEntry[]
  pending: number
  failed: number
  syncing: boolean
  lastReport: SyncReport | null
  syncNow: () => Promise<void>
  refresh: () => Promise<void>
  discardAll: () => Promise<void>
}

const OfflineContext = createContext<OfflineValue | null>(null)

export function OfflineProvider({ children }: { children: ReactNode }) {
  const [online, setOnline] = useState(navigator.onLine)
  const [queue, setQueue] = useState<OutboxEntry[]>([])
  const [syncing, setSyncing] = useState(false)
  const [lastReport, setLastReport] = useState<SyncReport | null>(null)

  const refresh = useCallback(async () => {
    setQueue(await outbox.list())
  }, [])

  useEffect(() => {
    const up = () => setOnline(true)
    const down = () => setOnline(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    const unsubscribe = outbox.subscribe(() => { void refresh() })
    const stopAuto = outbox.startAutoSync()
    void refresh()
    return () => {
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
      unsubscribe()
      stopAuto()
    }
  }, [refresh])

  const syncNow = useCallback(async () => {
    setSyncing(true)
    try {
      setLastReport(await outbox.sync())
    } finally {
      setSyncing(false)
      await refresh()
    }
  }, [refresh])

  const discardAll = useCallback(async () => {
    await outbox.discardAll()
    await refresh()
  }, [refresh])

  const value = useMemo<OfflineValue>(() => ({
    online,
    queue,
    pending: queue.filter((e) => e.status === 'pending').length,
    failed: queue.filter((e) => e.status === 'failed').length,
    syncing,
    lastReport,
    syncNow,
    refresh,
    discardAll,
  }), [online, queue, syncing, lastReport, syncNow, refresh, discardAll])

  return (
    <OfflineContext.Provider value={value}>{children}</OfflineContext.Provider>
  )
}

export function useOffline(): OfflineValue {
  const ctx = useContext(OfflineContext)
  if (!ctx) throw new Error('useOffline must be used inside OfflineProvider')
  return ctx
}

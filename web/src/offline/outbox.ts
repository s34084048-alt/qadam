import { ApiError, session } from '../api'
import * as db from './db'
import type { OutboxEntry } from './db'

export type { OutboxEntry } from './db'

const BASE = '/api/v1'

/**
 * Offline outbox.
 *
 * Entries are drained STRICTLY IN ORDER, because they depend on each other: a
 * case needs its patient to exist, an analysis needs its case. A dependency is
 * written as a `{$ref:localId}` placeholder; when the entry that owns that
 * localId syncs, the placeholder is rewritten IN THE DATABASE with the real
 * server id. Resolving in memory instead would break the moment the app is
 * closed halfway through a sync — which on a clinic device is normal.
 *
 * On the first failure the drain STOPS rather than skipping ahead. Skipping
 * would send a foot assessment for a case that does not exist yet.
 */

const REF = /\{\$ref:([^}]+)\}/g

function resolveString(text: string, localId: string, serverId: string): string {
  return text.replace(REF, (match, ref) => (ref === localId ? serverId : match))
}

function resolveDeep<T>(value: T, localId: string, serverId: string): T {
  if (typeof value === 'string') {
    return resolveString(value, localId, serverId) as unknown as T
  }
  if (Array.isArray(value)) {
    return value.map((v) => resolveDeep(v, localId, serverId)) as unknown as T
  }
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {}
    for (const [key, item] of Object.entries(value)) {
      out[key] = resolveDeep(item, localId, serverId)
    }
    return out as unknown as T
  }
  return value
}

function unresolved(entry: OutboxEntry): boolean {
  REF.lastIndex = 0
  const haystack = entry.path + JSON.stringify(entry.body ?? '')
    + JSON.stringify(entry.formFields ?? '')
  return REF.test(haystack)
}

export function newLocalId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export async function enqueue(
  entry: Omit<OutboxEntry, 'createdAt' | 'status' | 'attempts'>,
): Promise<number> {
  const id = await db.put({
    ...entry, createdAt: Date.now(), status: 'pending', attempts: 0,
  })
  notify()
  return id
}

export async function list(): Promise<OutboxEntry[]> {
  return db.supported() ? db.all() : []
}

export async function discardAll(): Promise<void> {
  await db.clear()
  notify()
}

export async function discard(id: number): Promise<void> {
  await db.remove(id)
  notify()
}

// --- listeners ---------------------------------------------------------------

type Listener = () => void
const listeners = new Set<Listener>()

export function subscribe(fn: Listener): () => void {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

function notify(): void {
  listeners.forEach((fn) => fn())
}

// --- sync --------------------------------------------------------------------

export interface SyncReport {
  sent: number
  remaining: number
  stopped: boolean
  reason?: string
}

let syncing = false

async function send(entry: OutboxEntry): Promise<Record<string, unknown>> {
  const headers: HeadersInit = {}
  const token = session.token
  if (token) headers.Authorization = `Bearer ${token}`

  let body: BodyInit
  if (entry.blob) {
    const form = new FormData()
    for (const [key, value] of Object.entries(entry.formFields ?? {})) {
      form.append(key, value)
    }
    form.append(entry.blobFieldName ?? 'file', entry.blob,
                entry.blobFileName ?? 'capture.png')
    body = form
  } else {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(entry.body ?? {})
  }

  const resp = await fetch(`${BASE}${entry.path}`, {
    method: entry.method, headers, body,
  })
  if (!resp.ok) {
    let message = resp.statusText
    let code = `http_${resp.status}`
    try {
      const payload = await resp.json()
      code = payload?.error?.code ?? code
      message = payload?.error?.message ?? message
    } catch { /* non-JSON */ }
    throw new ApiError(resp.status, code, message, null, {})
  }
  return resp.json().catch(() => ({}))
}

export async function sync(): Promise<SyncReport> {
  if (syncing || !db.supported()) {
    return { sent: 0, remaining: 0, stopped: true, reason: 'already running' }
  }
  if (!navigator.onLine) {
    const pending = await db.all()
    return { sent: 0, remaining: pending.length, stopped: true, reason: 'offline' }
  }
  if (!session.token) {
    const pending = await db.all()
    return {
      sent: 0, remaining: pending.length, stopped: true,
      reason: 'not signed in',
    }
  }

  syncing = true
  let sent = 0
  try {
    for (;;) {
      const queue = await db.all()
      const entry = queue[0]
      if (!entry) return { sent, remaining: 0, stopped: false }

      if (unresolved(entry)) {
        return {
          sent, remaining: queue.length, stopped: true,
          reason: 'an item depends on something that has not been sent yet',
        }
      }

      try {
        const result = await send(entry)
        const serverId = typeof result?.id === 'string' ? result.id : null

        // Rewrite dependants in the DATABASE, not in memory, so an interrupted
        // sync resumes correctly.
        if (serverId) {
          for (const other of queue.slice(1)) {
            const patched: OutboxEntry = {
              ...other,
              path: resolveString(other.path, entry.localId, serverId),
              body: resolveDeep(other.body, entry.localId, serverId),
              formFields: resolveDeep(other.formFields, entry.localId, serverId),
            }
            if (JSON.stringify(patched) !== JSON.stringify(other)) {
              await db.put(patched)
            }
          }
        }
        await db.remove(entry.id!)
        sent += 1
        notify()
      } catch (err) {
        const status = err instanceof ApiError ? err.status : 0
        const message = err instanceof Error ? err.message : String(err)
        await db.put({
          ...entry,
          status: status >= 400 && status < 500 && status !== 408 && status !== 429
            ? 'failed' : 'pending',
          attempts: entry.attempts + 1,
          lastError: message,
        })
        notify()
        const remaining = (await db.all()).length
        return {
          sent, remaining, stopped: true,
          reason: status === 401
            ? 'session expired — sign in again to finish sending'
            : message,
        }
      }
    }
  } finally {
    syncing = false
    notify()
  }
}

/** Sync when connectivity returns and when the app is brought back into view. */
export function startAutoSync(): () => void {
  const attempt = () => { void sync() }
  window.addEventListener('online', attempt)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') attempt()
  })
  const timer = window.setInterval(attempt, 60_000)
  attempt()
  return () => {
    window.removeEventListener('online', attempt)
    window.clearInterval(timer)
  }
}

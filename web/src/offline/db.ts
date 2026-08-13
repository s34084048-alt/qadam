/**
 * Minimal IndexedDB wrapper for the offline outbox.
 *
 * No dependency: the queue is small and the API surface needed is tiny, and a
 * clinic device should not be downloading a library to hold six records.
 *
 * PRIVACY: entries here hold patient images and clinical findings on the
 * device until they sync. They are never cleared automatically — silently
 * discarding a capture a health worker believes they took is worse than
 * leaving it queued — but the UI states the count plainly and offers an
 * explicit discard.
 */

const DB_NAME = 'qadam-offline'
const DB_VERSION = 1
const STORE = 'outbox'

export type OutboxStatus = 'pending' | 'failed'

export interface OutboxEntry {
  /** Monotonic; the queue is drained in this order to preserve dependencies. */
  id?: number
  localId: string
  kind: 'patient' | 'case' | 'analyze' | 'foot-risk' | 'labs' | 'investigation'
    | 'follow-up'
  /** May contain `{$ref: localId}` placeholders resolved at sync time. */
  path: string
  method: 'POST' | 'PATCH'
  body?: unknown
  /** Multipart payloads: the captured image itself. */
  blob?: Blob
  blobFieldName?: string
  blobFileName?: string
  formFields?: Record<string, string>
  label: string
  patientRef: string | null
  createdAt: number
  status: OutboxStatus
  attempts: number
  lastError?: string
}

let dbPromise: Promise<IDBDatabase> | null = null

function open(): Promise<IDBDatabase> {
  if (dbPromise) return dbPromise
  dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true })
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
  return dbPromise
}

function tx<T>(mode: IDBTransactionMode,
               run: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return open().then((db) => new Promise<T>((resolve, reject) => {
    const transaction = db.transaction(STORE, mode)
    const request = run(transaction.objectStore(STORE))
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  }))
}

export async function put(entry: OutboxEntry): Promise<number> {
  return tx('readwrite', (store) => store.put(entry) as IDBRequest<number>)
}

export async function all(): Promise<OutboxEntry[]> {
  const rows = await tx<OutboxEntry[]>('readonly',
    (store) => store.getAll() as IDBRequest<OutboxEntry[]>)
  return rows.sort((a, b) => (a.id ?? 0) - (b.id ?? 0))
}

export async function remove(id: number): Promise<void> {
  await tx('readwrite', (store) => store.delete(id) as unknown as IDBRequest<undefined>)
}

export async function clear(): Promise<void> {
  await tx('readwrite', (store) => store.clear() as unknown as IDBRequest<undefined>)
}

export function supported(): boolean {
  return typeof indexedDB !== 'undefined'
}

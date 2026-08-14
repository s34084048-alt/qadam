import type {
  Analysis, CaseDeleteResult, CaseDetail, CaseList, EmergencyReference,
  Fairness, LabCatalogue, Finding, FollowUp, FollowUpList, FollowUpQuestion,
  FeedbackEntry, FeedbackList, FootRiskAssessment, InvestigationResult,
  LabPanel, ModuleInfo, Progress,
  Patient, SafetyBlock,
} from './types'

const BASE = '/api/v1'
const TOKEN_KEY = 'qadam.token'
const ROLE_KEY = 'qadam.role'
const EMAIL_KEY = 'qadam.email'

export class ApiError extends Error {
  code: string
  hint: string | null
  details: Record<string, unknown>
  status: number

  constructor(status: number, code: string, message: string,
              hint: string | null, details: Record<string, unknown>) {
    super(message)
    this.status = status
    this.code = code
    this.hint = hint
    this.details = details
  }
}

export const session = {
  get token() { return localStorage.getItem(TOKEN_KEY) },
  get role() { return localStorage.getItem(ROLE_KEY) },
  get email() { return localStorage.getItem(EMAIL_KEY) },
  set(token: string, role: string, email: string) {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(ROLE_KEY, role)
    localStorage.setItem(EMAIL_KEY, email)
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(ROLE_KEY)
    localStorage.removeItem(EMAIL_KEY)
  },
}

function authHeaders(): HeadersInit {
  const token = session.token
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function toError(resp: Response): Promise<ApiError> {
  let code = `http_${resp.status}`
  let message = resp.statusText || 'Request failed'
  let hint: string | null = null
  let details: Record<string, unknown> = {}
  try {
    const body = await resp.json()
    if (body?.error) {
      code = body.error.code ?? code
      message = body.error.message ?? message
      hint = body.error.hint ?? null
      details = body.error.details ?? {}
    } else if (Array.isArray(body?.detail)) {
      // FastAPI validation errors.
      code = 'validation_error'
      message = body.detail.map((d: { msg: string }) => d.msg).join('; ')
    }
  } catch { /* non-JSON error body */ }
  return new ApiError(resp.status, code, message, hint, details)
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...authHeaders(), ...(init.headers ?? {}) },
  })
  if (resp.status === 401) {
    session.clear()
    throw await toError(resp)
  }
  if (!resp.ok) throw await toError(resp)
  if (resp.status === 204) return undefined as T
  return (await resp.json()) as T
}

async function requestBlob(path: string): Promise<Blob> {
  const resp = await fetch(`${BASE}${path}`, { headers: authHeaders() })
  if (!resp.ok) throw await toError(resp)
  return resp.blob()
}

export const api = {
  async login(email: string, password: string) {
    const body = new URLSearchParams({ username: email, password })
    const resp = await fetch(`${BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    })
    if (!resp.ok) throw await toError(resp)
    const data = await resp.json()
    session.set(data.access_token, data.role, data.email)
    return data
  },

  // One-click access with no password. Available only when the API reports
  // demo_mode; each call creates a session isolated in its own organisation.
  async startDemo() {
    const resp = await fetch(`${BASE}/auth/demo`, { method: 'POST' })
    if (!resp.ok) throw await toError(resp)
    const data = await resp.json()
    session.set(data.access_token, data.role, data.email)
    return data
  },

  modules: () =>
    request<{ modules: ModuleInfo[]; grades: Record<string, { color: string; label_en: string; label_ar: string }>; safety: SafetyBlock }>('/modules'),

  safety: () => request<SafetyBlock>('/safety'),

  emergency: () => request<EmergencyReference>('/reference/emergency'),

  health: () =>
    request<{
      status: string
      clinical_use: boolean
      version: string
      environment: string
      demo_mode: boolean
    }>('/health'),

  createPatient: (payload: {
    external_ref: string
    dob_year?: number | null
    sex?: string | null
    skin_tone_monk?: number | null
    consent_flag: boolean
  }) =>
    request<Patient>('/patients', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  getPatient: (ref: string) => request<Patient>(`/patients/${encodeURIComponent(ref)}`),

  updatePatient: (ref: string, payload: Record<string, unknown>) =>
    request<Patient>(`/patients/${encodeURIComponent(ref)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  createCase: (payload: {
    module: string
    patient_ref: string
    body_site?: string | null
    note?: string | null
  }) =>
    request<CaseDetail>('/cases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  analyze: (caseId: string, file: Blob, filename = 'capture.png') => {
    const form = new FormData()
    form.append('file', file, filename)
    return request<Analysis>(`/cases/${caseId}/analyze`, { method: 'POST', body: form })
  },

  getCase: (caseId: string) => request<CaseDetail>(`/cases/${caseId}`),

  listCases: (params: Record<string, string | number | undefined>) => {
    const query = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== '') query.set(key, String(value))
    })
    return request<CaseList>(`/cases?${query.toString()}`)
  },

  // Overlays are fetched with the bearer token and turned into object URLs, so
  // no credential is ever placed in an <img src> query string.
  overlayUrl: async (caseId: string, analysisId: string) => {
    const blob = await requestBlob(`/cases/${caseId}/analyses/${analysisId}/overlay.png`)
    return URL.createObjectURL(blob)
  },

  summaryPdf: (caseId: string) => requestBlob(`/cases/${caseId}/summary.pdf`),

  labCatalogue: () => request<LabCatalogue>('/labs/catalogue'),

  addLabPanel: (caseId: string, payload: {
    results: { code: string; value: number; unit: string }[]
    panel_name?: string | null
    age?: number | null
    sex?: string | null
    collected_at?: string | null
  }) =>
    request<LabPanel>(`/cases/${caseId}/labs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  listLabPanels: (caseId: string) =>
    request<{ case_id: string; panels: LabPanel[]; total: number }>(
      `/cases/${caseId}/labs`),

  listInvestigations: (caseId: string) =>
    request<{
      case_id: string
      results: InvestigationResult[]
      total: number
      interpretation_note: string
    }>(`/cases/${caseId}/investigations`),

  addInvestigation: (caseId: string, form: FormData) =>
    request<InvestigationResult>(`/cases/${caseId}/investigations`, {
      method: 'POST', body: form,
    }),

  // Fetched with the bearer token and turned into an object URL, so no
  // credential ever travels in a src attribute.
  investigationFileUrl: async (caseId: string, resultId: string) => {
    const blob = await requestBlob(
      `/cases/${caseId}/investigations/${resultId}/file`)
    return URL.createObjectURL(blob)
  },

  footRiskModel: () => request<Record<string, unknown>>('/foot/risk-model'),

  addFootRisk: (caseId: string, payload: {
    foot: string
  } & Record<string, Finding | string>) =>
    request<FootRiskAssessment>(`/cases/${caseId}/foot-risk`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  listFootRisk: (caseId: string) =>
    request<{ case_id: string; assessments: FootRiskAssessment[]; total: number }>(
      `/cases/${caseId}/foot-risk`),

  followUpQuestions: (module: string) =>
    request<{
      module: string
      questions: FollowUpQuestion[]
      combination_rule: string
      answers_are_not_measurements: string
      safety: SafetyBlock
    }>(`/follow-up/questions/${encodeURIComponent(module)}`),

  addFollowUp: (caseId: string, payload: {
    answers: Record<string, string | number>
    note?: string | null
    analysis_id?: string | null
  }) =>
    request<FollowUp>(`/cases/${caseId}/follow-up`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  listFollowUp: (caseId: string) =>
    request<FollowUpList>(`/cases/${caseId}/follow-up`),

  // `confirm` is required by the API, not defaulted there: a DELETE that fires
  // on a mistyped URL and destroys a case is not a recoverable mistake.
  deleteCase: (caseId: string) =>
    request<CaseDeleteResult>(`/cases/${caseId}?confirm=true`, {
      method: 'DELETE',
    }),

  caseProgress: (caseId: string, measure?: string) =>
    request<Progress>(
      `/cases/${caseId}/progress${measure ? `?measure=${measure}` : ''}`),

  listFeedback: (caseId: string) =>
    request<FeedbackList>(`/cases/${caseId}/feedback`),

  addFeedback: (caseId: string, payload: {
    analysis_id: string
    verdict: string
    ground_truth?: string | null
    note?: string | null
  }) =>
    request<FeedbackEntry>(`/cases/${caseId}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  fairness: () => request<Fairness>('/admin/fairness'),
}

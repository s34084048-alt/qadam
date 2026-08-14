export type Grade = 'no_flag' | 'monitor' | 'review' | 'urgent'
export type ModuleId = 'foot' | 'lab'

export interface SafetyBlock {
  disclaimer: string
  device_notice: string
  human_in_the_loop: string
  scope: string
  no_treatment: string
  intended_use: string
  clinical_use: boolean
  never_claims: string[]
  module_limitations?: string[]
  no_flag_caveat?: string
  data_residency?: string
  consent_required?: boolean
}

export interface RoutingSpec {
  label: string
  routing_target: string
  next_investigation: string
  urgency: string
  color: string
}

export interface ModuleInfo {
  id: ModuleId
  label: { en: string; ar: string }
  description: { en: string; ar: string }
  screens: string[]
  body_sites: string[]
  routing_only: boolean
  input_kind: 'image' | 'numeric'
  limitations: string[]
  no_flag_caveat: string | null
  routing: Record<Grade, RoutingSpec>
}

export interface QualityCheck {
  name: string
  passed: boolean
  value: number
  threshold: number
  hint: string
}

export interface Quality {
  passed: boolean
  width: number
  height: number
  subject_fraction: number
  focus_var: number
  exposure_mean: number
  confidence_factor: number
  checks: QualityCheck[]
  hints: string[]
}

export interface LesionOut {
  id: string
  kind: string
  area_pct: number
  severity: number
  bbox: { x: number; y: number; w: number; h: number }
  centroid: { x: number; y: number }
  description: string
}

export interface Triage {
  grade: Grade
  label: string
  confidence: number
  rationale: string[]
  next_investigation: string
  urgency: string
  routing_target: string
  color: string
}

export interface AnalyteRange { low: number | null; high: number | null }

export interface Analyte {
  code: string
  name: string
  unit: string
  accepted_units: string[]
  group: string
  group_label: string
  reference: AnalyteRange
  reference_female: AnalyteRange | null
  critical_low: number | null
  critical_high: number | null
  note: string
}

export interface LabCatalogue {
  analytes: Analyte[]
  groups: Record<string, string>
  reference_range_caveat: string
}

export interface LabResultOut {
  code: string
  name: string
  value: number
  unit: string
  flag: 'normal' | 'low' | 'high'
  critical: boolean
  submitted: { value: number; unit: string }
  converted: boolean
  reference: AnalyteRange
  note?: string
}

export interface DerivedIndex {
  code: string
  name: string
  value: number
  unit: string
  interpretation: string
  caveat: string
}

export interface LabPanel {
  id?: string
  case_id?: string
  panel_name?: string | null
  collected_at?: string | null
  created_at?: string
  triage: Triage
  results: LabResultOut[]
  derived: DerivedIndex[]
  clinical: Clinical | null
  unrecognised: { code: string; reason: string }[]
  safety: SafetyBlock
  reference_range_caveat?: string
}

export type Finding = 'present' | 'absent' | 'not_tested'

export interface FootRiskAssessment {
  id?: string
  case_id?: string
  foot?: string
  created_at?: string
  category: number | null
  label: string
  complete: boolean
  missing_tests: string[]
  criteria: string | null
  screening_interval: string
  routing_target: string
  grade: Grade
  rationale: string[]
  clinical: Clinical | null
  source: string
  derived_from_image: false
  findings?: Record<string, Finding>
}

export interface InvestigationResult {
  id: string
  case_id: string
  category: string
  modality: string | null
  body_site: string | null
  performed_at: string | null
  reporting_service: string | null
  report_text: string | null
  has_file: boolean
  content_type: string | null
  size_bytes: number | null
  created_at: string
  automated_interpretation: false
  interpretation_note: string
}

export interface EmergencyTopic {
  id: string
  title: string
  steps: string[]
  warnings?: string[]
  move_only_if?: string[]
  diagram?: string
}

export interface EmergencyReference {
  kind: string
  image_independent: boolean
  generated_from_image: boolean
  title: string
  disclaimer: string
  why_static: string
  topics: EmergencyTopic[]
  diagrams: Record<string, string>
}

export interface Consideration {
  pattern: string
  overlaps_with: string[]
  distinguished_by: string
}

export interface SeverityIndex {
  name: string
  value: number
  unit: string
  band: string
  components: unknown
  caveat: string
}

export interface Clinical {
  severity_index: SeverityIndex | null
  considerations: Consideration[]
  immediate_actions: string[]
  ask_and_check: string[]
  not_assessable: string[]
  scales: Record<string, Record<string, unknown>>
  status: string
}

export interface Analysis {
  id: string
  case_id: string
  image_id: string
  module: ModuleId
  model_version: string
  backend: string
  created_at: string
  triage: Triage
  lesions: LesionOut[]
  quality: Quality
  features: Record<string, unknown>
  clinical: Clinical | null
  overlay_png_base64: string | null
  summary: string
  safety: SafetyBlock
}

export interface ColourCalibration {
  detected: boolean
  applied: boolean
  how_to: string
  note: string
  reason?: string
  gains_bgr?: number[]
  illuminant_shift_pct?: number
  card?: {
    bbox: { x: number; y: number; w: number; h: number }
    area_frac: number
    L_mean: number
    L_std: number
    chroma_mean: number
    bgr_mean: number[]
    clipped_frac: number
  }
}

export interface FollowUpQuestion {
  id: string
  text: string
  kind: 'choice' | 'yesno' | 'number'
  options: string[]
  unit: string | null
  why: string
}

export interface FollowUpTrigger {
  grade: Grade
  finding: string
  because: string
  consider: string[]
  distinguished_by: string
}

export interface FollowUpOutcome {
  module: string
  answer_grade: Grade
  triggers: FollowUpTrigger[]
  answers: Record<string, string | number>
  unanswered: string[]
  not_tested: string[]
  rule: string
  status: string
}

export interface FollowUp {
  id: string
  case_id: string
  analysis_id: string | null
  module: ModuleId
  /** What the photograph observed. RECORDED ONLY — it routes nothing. */
  image_grade: Grade
  answer_grade: Grade
  answer_label: string
  answer_color: string
  triggered: boolean
  answers: Record<string, string | number>
  outcome: FollowUpOutcome
  note: string | null
  created_at: string
  created_by: string
  safety: SafetyBlock
}

export interface FollowUpList {
  case_id: string
  module: ModuleId
  questions: FollowUpQuestion[]
  entries: FollowUp[]
  total: number
}

export interface ProgressPoint {
  at: string
  area_cm2: number
  analysis_id: string
}

/**
 * Wound area across visits. The one image-derived number that corresponds to
 * an established clinical indicator — and it still routes nothing.
 */
export interface Progress {
  case_id: string
  measure: string
  comparable: boolean
  points: ProgressPoint[]
  excluded: { analysis_id: string; at: string; reason: string }[]
  reason?: string
  change?: {
    baseline: ProgressPoint
    latest: ProgressPoint
    days_between: number
    absolute_cm2: number
    percent_area_reduction: number | null
    direction: 'smaller' | 'larger' | 'unchanged'
  }
  prompt?: {
    action: 'reassess' | 'on_track' | 'too_early' | 'none'
    basis: string
    detail: string
  }
  not_a_diagnosis: string
  derived_from_image: true
  routes_nothing: true
  safety: SafetyBlock
}

export interface CaseDeleteResult {
  case_id: string
  deleted: Record<string, number>
  images_removed: number
  audit_retained: boolean
  note: string
}

export interface RoutingBasis {
  source: 'iwgdf_risk_category' | 'follow_up_answers'
  grade: Grade
  detail: string
  screening_interval?: string
  triggers?: string[]
}

/**
 * THE decision for a case. Comes from the examination and the answers; the
 * photograph is not an input. `grade` is 'not_assessed' when nothing has been
 * assessed yet — which is NOT the same as no_flag and must never be shown as
 * a reassuring result.
 */
export interface Routing {
  assessed: boolean
  grade: Grade | 'not_assessed'
  label: string
  urgency: string
  routing_target: string
  next_investigation: string
  basis: RoutingBasis[]
  missing: string[]
  derived_from_image: false
  image_note: string
  color?: string
  note?: string
}

export interface CaseDetail {
  id: string
  module: ModuleId
  patient_ref: string
  status: string
  body_site: string | null
  note: string | null
  created_at: string
  created_by: string
  latest_analysis: Analysis | null
  history: Analysis[]
  routing: Routing
}

export interface CaseListItem {
  id: string
  module: ModuleId
  patient_ref: string
  status: string
  created_at: string
  triage_grade: Grade | null
  triage_label: string | null
  confidence: number | null
  analysis_count: number
}

export interface CaseList {
  items: CaseListItem[]
  total: number
  limit: number
  offset: number
}

export interface Patient {
  id: string
  external_ref: string
  dob_year: number | null
  sex: string | null
  skin_tone_monk: number | null
  consent_flag: boolean
  created_at: string
}

export interface FairnessStratum {
  group: string
  analyses: number
  by_module: Record<string, number>
  by_grade: Record<string, number>
  mean_confidence: number | null
  quality_pass_rate: number | null
}

export interface Fairness {
  status: string
  strata: FairnessStratum[]
  coverage: {
    analyses_total: number
    skin_tone_recorded: number
    recorded_fraction: number | null
  }
  notes: string[]
}

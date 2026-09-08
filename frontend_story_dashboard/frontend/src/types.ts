export type AnalysisStatus = 'pending' | 'processing' | 'ready' | 'failed'
export type FacetName = 'positive_evaluation' | 'negative_evaluation' | 'improvement'

export interface Product {
  parent_asin: string
  title: string
  category: string
  review_count: number
  analysis_status?: AnalysisStatus
  active_month_count?: number
  last_review_month?: string
}

export interface Facet {
  facet: FacetName
  status: AnalysisStatus
  theme_count: number | null
  empty_reason: 'no_qualified_theme' | null
  error_summary: string | null
}

export interface Ratio {
  value: number | null
  status: 'ready' | 'definition_pending' | string
  definition_id?: string | null
}

export interface Theme {
  theme_id: string
  name: string
  sentiment: 'positive' | 'negative' | null
  review_count: number
  ratio: Ratio
  trend?: TrendPoint[]
}

export interface TrendPoint {
  month: string
  review_count: number
  ratio?: Ratio
}

export interface ReviewEvidence {
  review_id: string
  text: string
  evidence_text: string | null
  rating: number
  review_date: string | null
  review_month?: string | null
}

export interface ApiMeta {
  data_source: 'mock' | 'mongodb_gold' | string
  is_gold: boolean
  batch_id: string
  generated_at?: string
  gold_status?: string
}

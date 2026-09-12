export interface ApiResponse<T = unknown> {
  success: boolean
  data: T
  message?: string
  error?: { code: string; message: string }
}

export interface Principal {
  id: string
  email: string
  first_name: string
  last_name: string
  company?: string
  avatar_url?: string
  principal_type: 'user' | 'admin'
  roles: string[]
  preferences?: Record<string, unknown>
}

export interface Dataset {
  id: string
  name: string
  description?: string
  file_name: string
  file_format: string
  file_size_bytes: number
  status: 'uploading' | 'processing' | 'ready' | 'error'
  row_count?: number
  column_count?: number
  duckdb_table?: string
  created_at: string
}

export interface DatasetColumn {
  id?: string
  name: string
  display_name: string
  semantic_name?: string
  col_type: 'text' | 'integer' | 'float' | 'boolean' | 'date' | 'datetime'
  is_metric: boolean
  is_dimension: boolean
  sample_values: string[]
  null_count: number
  unique_count: number
}

// ─── Semantic layer ─────────────────────────────────────────────────────────
export interface SemanticMember {
  name: string
  kind: 'dimension' | 'measure' | 'computed'
  title: string
  type: string
  column?: string | null
  format?: string | null
  description?: string | null
  agg?: string | null // SUM/AVG/… for aggregated column measures; null = raw row values
  row_level?: boolean // raw column measure or row-level formula metric (row-level values)
}

export interface ComputedMetric {
  id: string
  name: string
  display_name: string
  description?: string
  expression: Record<string, unknown>
  format?: string
  is_auto: boolean
  is_row_level?: boolean // formula uses raw column values → row-level metric
}

export interface MemberCatalog {
  cube: string
  dimensions: SemanticMember[]
  measures: SemanticMember[]
  computed_metrics: ComputedMetric[]
}

export type FilterOperator =
  | 'equals' | 'notEquals' | 'gt' | 'gte' | 'lt' | 'lte'
  | 'contains' | 'set' | 'notSet'

export interface SemanticFilter {
  member: string
  operator: FilterOperator
  values: Array<string | number | boolean>
}

export interface SemanticQuery {
  measures: string[]
  dimensions: string[]
  time_dimension?: string | null
  granularity?: 'day' | 'week' | 'month' | null
  date_range?: string | string[] | null
  filters: SemanticFilter[]
  order: Record<string, 'asc' | 'desc'>
  limit: number
  visualization?: ChartType
  mode?: 'auto' | 'ohlc' // ohlc = candlestick open/high/low/close aggregation
  kpi?: { expression: Record<string, unknown>; label?: string } // KPI custom calculation
}

export interface SemanticResult {
  rows: Array<Record<string, unknown>>
  meta: { engine: string; took_ms: number }
}

export interface Dashboard {
  id: string
  name: string
  description?: string
  is_default: boolean
  layout?: Record<string, unknown>
  created_at: string
}

export interface Widget {
  id: string
  title: string
  viz_type: string
  echart_config?: Record<string, unknown>
  semantic_query?: Record<string, unknown>
  position: { x: number; y: number; w: number; h: number }
  refresh_interval?: number
  dataset_id?: string
  insight_id?: string
}

export interface Insight {
  id: string
  name: string
  description?: string
  dataset_id?: string
  insight_type: string
  insight_definition: Record<string, unknown>
  echart_config?: Record<string, unknown>
  ai_explanation?: string
  ai_recommendation?: string
  is_pinned: boolean
  is_template?: boolean
  tags: string[]
  created_at: string
}

export interface InsightExecution {
  rows: Array<Record<string, unknown>>
  echart_config: Record<string, unknown>
  definition: Record<string, unknown>
  ai_explanation?: string
  ai_recommendation?: string
  meta: { engine: string; took_ms: number }
}

export interface CopilotConversation {
  id: string
  title: string
  dataset_id?: string
  created_at: string
}

export interface CopilotMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  echart_config?: Record<string, unknown>
  semantic_query?: Record<string, unknown>
  tool_calls?: Array<{ tool: string; args: Record<string, unknown> }>
  created_at: string
}

export interface Report {
  id: string
  name: string
  status: 'generating' | 'ready' | 'error'
  has_download?: boolean
  generated_at?: string
  created_at: string
}

export interface ReportSchedule {
  id: string
  name: string
  dataset_id: string
  cadence: 'daily' | 'weekly'
  hour_utc: number
  is_active: boolean
  last_run_at?: string
  next_run_at?: string
}

export interface KPIData {
  [key: string]: number
}

// 'table' is legacy: still rendered for old saved insights/widgets, but no
// longer offered by the builder picker (replaced by 'candlestick').
export type ChartType = 'bar' | 'line' | 'area' | 'pie' | 'scatter' | 'table' | 'kpi' | 'candlestick'

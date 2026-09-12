import { apiClient, del, get, patch, post, put, upload } from './client'
import type {
  ComputedMetric, CopilotConversation, CopilotMessage, Dashboard, Dataset,
  DatasetColumn, Insight, InsightExecution, KPIData, MemberCatalog, Principal,
  Report, ReportSchedule, SemanticQuery, SemanticResult, Widget,
} from '@/types'

// ─── Auth ──────────────────────────────────────────────────────────────────────
export const authService = {
  // Login/register/logout are Server Actions (auth.actions.ts) — no Axios variants here.
  me: () => get<Principal>('/me/'),
  meAdmin: () => get<Principal>('/me/admin'),
  changePassword: (current_password: string, new_password: string) =>
    post('/users/change-password', { current_password, new_password }),
}

// ─── Datasets ─────────────────────────────────────────────────────────────────
export const datasetService = {
  list: () => get<{ datasets: Dataset[] }>('/datasets/'),
  get: (id: string) => get<{ dataset: Dataset; columns: DatasetColumn[]; schema_summary: unknown }>('/datasets/' + id),
  upload: (file: File) => upload<{ dataset: Dataset }>('/datasets/upload', file),
  delete: (id: string) => del('/datasets/' + id),
  query: (id: string, sql: string) => post<{ rows: Record<string, unknown>[]; row_count: number }>('/datasets/' + id + '/query', { sql }),
  preview: (
    id: string, limit = 50, offset = 0,
    opts?: { filters?: Array<{ field: string; operator: string; value: string | number }>; search?: string },
  ) =>
    get<{ rows: Record<string, unknown>[]; columns: string[]; total_rows: number; unfiltered_rows?: number; offset: number; limit: number }>(
      '/datasets/' + id + '/preview', {
        limit, offset,
        ...(opts?.filters?.length ? { filters: JSON.stringify(opts.filters) } : {}),
        ...(opts?.search ? { search: opts.search } : {}),
      }),
}

// ─── Analytics ────────────────────────────────────────────────────────────────
export const analyticsService = {
  kpis: (datasetId: string) => get<{ kpis: KPIData }>('/analytics/' + datasetId + '/kpis'),
  groupBy: (datasetId: string, payload: unknown) => post<{ rows: unknown[] }>('/analytics/' + datasetId + '/group-by', payload),
  timeSeries: (datasetId: string, payload: unknown) => post<{ rows: Array<Record<string, unknown>> }>('/analytics/' + datasetId + '/time-series', payload),
  anomalies: (datasetId: string, metric: string, threshold = 2.0) =>
    get<{ anomalies: Array<Record<string, unknown>> }>('/analytics/' + datasetId + '/anomalies', { metric, threshold }),
  compare: (datasetId: string, payload: unknown) =>
    post<{ period_a: { value: number }; period_b: { value: number }; delta: number; pct_change: number | null; direction: string }>(
      '/analytics/' + datasetId + '/compare', payload),
}

// ─── Semantic layer ─────────────────────────────────────────────────────────
export const semanticService = {
  members: (datasetId: string) => get<MemberCatalog>('/datasets/' + datasetId + '/semantic'),
  query: (payload: Partial<SemanticQuery> & { dataset_id: string }) =>
    post<SemanticResult>('/semantic/query', payload),
  createMetric: (datasetId: string, data: unknown) =>
    post<{ id: string; name: string }>('/datasets/' + datasetId + '/metrics', data),
  previewMetric: (datasetId: string, expression: unknown) =>
    post<{ value: number | null }>('/datasets/' + datasetId + '/metrics/preview', { expression }),
  updateMetric: (datasetId: string, metricId: string, data: unknown) =>
    patch('/datasets/' + datasetId + '/metrics/' + metricId, data),
  deleteMetric: (datasetId: string, metricId: string) =>
    del('/datasets/' + datasetId + '/metrics/' + metricId),
  updateColumn: (datasetId: string, columnId: string, data: unknown) =>
    patch('/datasets/' + datasetId + '/columns/' + columnId, data),
}

// ─── Insights ─────────────────────────────────────────────────────────────────
export const insightService = {
  list: () => get<{ insights: Insight[] }>('/insights/'),
  templates: () => get<{ templates: Insight[] }>('/insights/templates'),
  create: (data: unknown) => post<{ id: string }>('/insights/', data),
  execute: (id: string, explain = false) =>
    post<InsightExecution>('/insights/' + id + '/execute?explain=' + explain, {}),
  update: (id: string, data: unknown) => patch<Insight>('/insights/' + id, data),
  nlCreate: (dataset_id: string, prompt: string) =>
    post<{ definition: Record<string, unknown>; rows: Array<Record<string, unknown>>; echart_config: Record<string, unknown> }>(
      '/insights/nl-create', { dataset_id, prompt }),
  discover: (datasetId: string) => post<{ findings: unknown }>('/insights/' + datasetId + '/discover', {}),
  delete: (id: string) => del('/insights/' + id),
}

// ─── Copilot ──────────────────────────────────────────────────────────────────
export const copilotService = {
  start: (dataset_id: string, title?: string) =>
    post<{ conversation_id: string; title: string }>('/copilot/conversations', { dataset_id, title }),
  send: (convId: string, message: string) =>
    post<{ message_id: string; text: string; echart_config?: Record<string, unknown>; semantic_query?: Record<string, unknown>; tool_calls?: unknown[]; latency_ms: number }>(
      '/copilot/conversations/' + convId + '/messages', { message }),
  list: () => get<{ conversations: CopilotConversation[] }>('/copilot/conversations'),
  messages: (convId: string) => get<{ messages: CopilotMessage[] }>('/copilot/conversations/' + convId + '/messages'),
  saveInsight: (messageId: string, name: string, description?: string) =>
    post<{ id: string }>('/copilot/messages/' + messageId + '/save-insight', { name, description }),
  addToDashboard: (messageId: string, dashboard_id: string, title: string) =>
    post<{ widget_id: string }>('/copilot/messages/' + messageId + '/add-to-dashboard', { dashboard_id, title }),
}

// ─── Dashboards ───────────────────────────────────────────────────────────────
export const dashboardService = {
  list: () => get<{ dashboards: Dashboard[] }>('/dashboards/'),
  get: (id: string) => get<{ dashboard: Dashboard; widgets: Widget[] }>('/dashboards/' + id),
  create: (data: { name: string; description?: string }) => post<{ dashboard: Dashboard }>('/dashboards/', data),
  update: (id: string, data: unknown) => patch<Dashboard>('/dashboards/' + id, data),
  delete: (id: string) => del('/dashboards/' + id),
  saveLayout: (id: string, items: Array<{ widget_id: string; x: number; y: number; w: number; h: number }>) =>
    put('/dashboards/' + id + '/layout', { items }),
  addWidget: (dashboardId: string, data: unknown) => post<{ widget_id: string }>('/dashboards/' + dashboardId + '/widgets', data),
  updateWidget: (dashboardId: string, widgetId: string, data: unknown) =>
    patch('/dashboards/' + dashboardId + '/widgets/' + widgetId, data),
  deleteWidget: (dashboardId: string, widgetId: string) =>
    del('/dashboards/' + dashboardId + '/widgets/' + widgetId),
  widgetData: (dashboardId: string, widgetId: string) =>
    post<{ rows: Array<Record<string, unknown>>; echart_config: Record<string, unknown>; meta: unknown }>(
      '/dashboards/' + dashboardId + '/widgets/' + widgetId + '/data', {}),
}

// ─── Reports ──────────────────────────────────────────────────────────────────
export const reportService = {
  list: () => get<{ reports: Report[] }>('/reports/'),
  create: (data: { dataset_id: string; name: string }) => post<{ report_id: string }>('/reports/', data),
  download: (id: string) => get<{ download_url: string }>('/reports/' + id + '/download'),
  /** Fetch the PDF through the API (cookies included) and trigger a browser download. */
  downloadFile: async (id: string, name = 'report') => {
    const r = await apiClient.get('/reports/' + id + '/file', { responseType: 'blob' })
    const url = URL.createObjectURL(r.data as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = name.toLowerCase().endsWith('.pdf') ? name : `${name}.pdf`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },
  delete: (id: string) => del('/reports/' + id),
  schedules: () => get<{ schedules: ReportSchedule[] }>('/reports/schedules'),
  createSchedule: (data: { dataset_id: string; name: string; cadence: string; hour_utc: number }) =>
    post<ReportSchedule>('/reports/schedules', data),
  updateSchedule: (id: string, data: unknown) => patch('/reports/schedules/' + id, data),
  deleteSchedule: (id: string) => del('/reports/schedules/' + id),
}

// ─── Admin ────────────────────────────────────────────────────────────────────
export const adminService = {
  users: (page = 1) => get<{ users: unknown[]; total: number }>('/admin/users/', { page }),
  userStats: () => get('/admin/users/stats'),
  userDetail: (id: string) => get<AdminUserDetail>('/admin/users/' + id),
  suspendUser: (id: string) => patch('/admin/users/' + id + '/suspend', {}),
  deleteUser: (id: string) => del('/admin/users/' + id),
  health: () => get('/admin/monitoring/health'),
  stats: () => get('/admin/monitoring/stats'),
  settings: () => get('/admin/settings/'),
  analytics: (days = 14) => get<AdminAnalytics>('/admin/analytics/overview', { days }),
}

export interface AdminUserDetail {
  user: {
    id: string; email: string; first_name: string; last_name: string
    company?: string | null; avatar_url?: string | null; is_active: boolean
    preferences?: Record<string, unknown> | null
    last_login_at?: string | null; created_at: string; updated_at: string
  }
  resources: {
    datasets: number; storage_bytes: number; dataset_rows: number
    dashboards: number; insights: number; reports: number
    conversations: number; messages: number
  }
  ai_usage: {
    calls: number; input_tokens: number; output_tokens: number
    total_tokens: number; last_call_at?: string | null
  }
  recent_datasets: Array<{
    id: string; name: string; status: string
    row_count?: number | null; file_size_bytes?: number | null; created_at: string
  }>
}

export interface AdminAnalytics {
  users: { total: number; active: number; new_7d: number }
  content: {
    datasets: number; insights: number; dashboards: number
    reports: number; conversations: number; messages: number
  }
  ai: {
    total_calls: number; input_tokens: number; output_tokens: number; total_tokens: number
    avg_latency_ms?: number | null; success_rate?: number | null; calls_24h: number
    tokens_by_day: Array<{ date: string; calls: number; input_tokens: number; output_tokens: number }>
    by_model: Array<{ model: string; calls: number; tokens: number }>
    by_feature: Array<{ feature: string; calls: number; tokens: number; avg_latency_ms?: number | null }>
    top_users: Array<{ email: string; calls: number; tokens: number }>
  }
  window_days: number
}

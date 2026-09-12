'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { analyticsService } from '@/lib/api/services'
import { EChartWrapper } from '@/components/features/charts/echart-wrapper'
import { buildOption } from '@/lib/charts/build-option'
import { formatNumber, formatPercent, cn } from '@/lib/utils'
import type { DatasetColumn } from '@/types'

// ─── Time series ──────────────────────────────────────────────────────────────
export function TimeSeriesTab({ datasetId, cols }: { datasetId: string; cols: DatasetColumn[] }) {
  const dateCols = cols.filter((c) => c.col_type === 'date' || c.col_type === 'datetime')
  const metrics = cols.filter((c) => c.is_metric)
  const [dateCol, setDateCol] = useState(dateCols[0]?.name ?? '')
  const [metric, setMetric] = useState(metrics[0]?.name ?? '')
  const [truncate, setTruncate] = useState('day')

  const q = useQuery({
    queryKey: ['ts', datasetId, dateCol, metric, truncate],
    queryFn: () => analyticsService.timeSeries(datasetId, { date_col: dateCol, metric, agg: 'SUM', truncate }),
    enabled: !!dateCol && !!metric,
  })

  const rows = q.data?.rows ?? []
  const option = rows.length ? buildOption({ rows, chartType: 'line', xField: 'period', yFields: ['value'], title: `${metric} over time` }) : null

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <select value={dateCol} onChange={(e) => setDateCol(e.target.value)} className="input-cyber">
          {dateCols.map((c) => <option key={c.name} value={c.name}>{c.display_name}</option>)}
        </select>
        <select value={metric} onChange={(e) => setMetric(e.target.value)} className="input-cyber">
          {metrics.map((c) => <option key={c.name} value={c.name}>{c.display_name}</option>)}
        </select>
        <select value={truncate} onChange={(e) => setTruncate(e.target.value)} className="input-cyber">
          <option value="day">Daily</option><option value="week">Weekly</option><option value="month">Monthly</option>
        </select>
      </div>
      <div className="card min-h-[320px] flex items-center justify-center">
        {q.isFetching ? <Loader2 className="w-5 h-5 animate-spin text-neon-blue" /> : option ? <EChartWrapper option={option} height={300} /> : <p className="text-text-muted text-sm">No date columns to plot.</p>}
      </div>
    </div>
  )
}

// ─── Anomalies ────────────────────────────────────────────────────────────────
export function AnomaliesTab({ datasetId, cols }: { datasetId: string; cols: DatasetColumn[] }) {
  const metrics = cols.filter((c) => c.is_metric)
  const [metric, setMetric] = useState(metrics[0]?.name ?? '')
  const [threshold, setThreshold] = useState(2)

  const q = useQuery({
    queryKey: ['anomalies', datasetId, metric, threshold],
    queryFn: () => analyticsService.anomalies(datasetId, metric, threshold),
    enabled: !!metric,
  })
  const rows = q.data?.anomalies ?? []

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <select value={metric} onChange={(e) => setMetric(e.target.value)} className="input-cyber">
          {metrics.map((c) => <option key={c.name} value={c.name}>{c.display_name}</option>)}
        </select>
        <label className="text-xs text-text-muted flex items-center gap-2">
          z &gt; {threshold.toFixed(1)}
          <input type="range" min={1} max={4} step={0.5} value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} />
        </label>
      </div>
      <div className="card">
        {q.isFetching ? (
          <div className="flex justify-center py-8"><Loader2 className="w-5 h-5 animate-spin text-neon-blue" /></div>
        ) : rows.length === 0 ? (
          <p className="text-text-muted text-sm py-6 text-center">No anomalies above this threshold.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="border-b border-border">{Object.keys(rows[0]).slice(0, 8).map((k) => <th key={k} className="text-left py-2 px-3 text-text-muted">{k}</th>)}</tr></thead>
              <tbody>
                {rows.slice(0, 20).map((r, i) => (
                  <tr key={i} className="border-b border-border/40">
                    {Object.keys(rows[0]).slice(0, 8).map((k) => <td key={k} className="py-1.5 px-3 text-text-primary">{typeof r[k] === 'number' ? formatNumber(r[k] as number) : String(r[k] ?? '')}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Compare periods ──────────────────────────────────────────────────────────
export function CompareTab({ datasetId, cols }: { datasetId: string; cols: DatasetColumn[] }) {
  const dateCols = cols.filter((c) => c.col_type === 'date' || c.col_type === 'datetime')
  const metrics = cols.filter((c) => c.is_metric)
  const [dateCol, setDateCol] = useState(dateCols[0]?.name ?? '')
  const [metric, setMetric] = useState(metrics[0]?.name ?? '')
  const [a, setA] = useState({ start: '', end: '' })
  const [b, setB] = useState({ start: '', end: '' })

  const q = useQuery({
    queryKey: ['compare', datasetId, dateCol, metric, a, b],
    queryFn: () => analyticsService.compare(datasetId, { date_col: dateCol, metric, period_a: [a.start, a.end], period_b: [b.start, b.end], agg: 'SUM' }),
    enabled: !!dateCol && !!metric && !!a.start && !!a.end && !!b.start && !!b.end,
  })
  const res = q.data

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <select value={dateCol} onChange={(e) => setDateCol(e.target.value)} className="input-cyber">
          {dateCols.map((c) => <option key={c.name} value={c.name}>{c.display_name}</option>)}
        </select>
        <select value={metric} onChange={(e) => setMetric(e.target.value)} className="input-cyber">
          {metrics.map((c) => <option key={c.name} value={c.name}>{c.display_name}</option>)}
        </select>
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        <div className="card space-y-2">
          <p className="text-xs text-text-muted">Period A</p>
          <div className="flex gap-2">
            <input type="date" value={a.start} onChange={(e) => setA({ ...a, start: e.target.value })} className="input-cyber flex-1" />
            <input type="date" value={a.end} onChange={(e) => setA({ ...a, end: e.target.value })} className="input-cyber flex-1" />
          </div>
        </div>
        <div className="card space-y-2">
          <p className="text-xs text-text-muted">Period B</p>
          <div className="flex gap-2">
            <input type="date" value={b.start} onChange={(e) => setB({ ...b, start: e.target.value })} className="input-cyber flex-1" />
            <input type="date" value={b.end} onChange={(e) => setB({ ...b, end: e.target.value })} className="input-cyber flex-1" />
          </div>
        </div>
      </div>
      {q.isFetching ? (
        <div className="flex justify-center py-6"><Loader2 className="w-5 h-5 animate-spin text-neon-blue" /></div>
      ) : res ? (
        <div className="grid grid-cols-3 gap-3">
          <div className="stat-card"><div className="stat-label">Period A</div><div className="stat-value">{formatNumber(res.period_a.value)}</div></div>
          <div className="stat-card"><div className="stat-label">Period B</div><div className="stat-value">{formatNumber(res.period_b.value)}</div></div>
          <div className="stat-card">
            <div className="stat-label">Change</div>
            <div className={cn('stat-value', res.direction === 'up' ? 'text-neon-green' : res.direction === 'down' ? 'text-red-400' : '')}>
              {res.pct_change !== null ? formatPercent(res.pct_change) : '—'}
            </div>
          </div>
        </div>
      ) : (
        <p className="text-text-muted text-sm text-center py-4">Pick two date ranges to compare.</p>
      )}
    </div>
  )
}

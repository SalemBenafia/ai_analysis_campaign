'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, BarChart3, Bot, Coins, Timer, Users } from 'lucide-react'
import { adminService } from '@/lib/api/services'
import { EChartWrapper } from '@/components/features/charts/echart-wrapper'
import { SkeletonCard } from '@/components/common/loading-page'
import { formatNumber } from '@/lib/utils'

// Categorical palette validated for the dark card surface (#111827):
// lightness band, chroma, CVD separation and contrast all pass.
const C = { input: '#0891b2', output: '#a855f7', bar: '#0891b2' }
const AXIS_LABEL = { color: '#94a3b8', fontSize: 10 }
const GRID_LINE = { lineStyle: { color: '#1e2d4a' } }

function StatTile({ icon: Icon, label, value, hint }: {
  icon: typeof Bot; label: string; value: string; hint?: string
}) {
  return (
    <div className="card py-3 px-4">
      <p className="text-[11px] uppercase tracking-wide text-text-muted flex items-center gap-1.5">
        <Icon className="w-3.5 h-3.5" /> {label}
      </p>
      <p className="text-xl font-bold text-text-primary mt-1">{value}</p>
      {hint && <p className="text-[11px] text-text-muted mt-0.5">{hint}</p>}
    </div>
  )
}

function tokensByDayOption(rows: Array<{ date: string; input_tokens: number; output_tokens: number }>) {
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'line' } },
    legend: { data: ['Input tokens', 'Output tokens'], textStyle: { color: '#94a3b8' }, top: 'bottom' },
    grid: { left: '3%', right: '4%', bottom: '16%', top: '8%', containLabel: true },
    xAxis: { type: 'category', data: rows.map((r) => r.date), axisLabel: AXIS_LABEL, axisLine: GRID_LINE },
    yAxis: { type: 'value', axisLabel: AXIS_LABEL, splitLine: GRID_LINE },
    series: [
      {
        type: 'line', name: 'Input tokens', data: rows.map((r) => r.input_tokens),
        smooth: true, lineStyle: { width: 2, color: C.input }, itemStyle: { color: C.input },
        areaStyle: { opacity: 0.15, color: C.input }, symbolSize: 6,
      },
      {
        type: 'line', name: 'Output tokens', data: rows.map((r) => r.output_tokens),
        smooth: true, lineStyle: { width: 2, color: C.output }, itemStyle: { color: C.output },
        areaStyle: { opacity: 0.15, color: C.output }, symbolSize: 6,
      },
    ],
  }
}

function tokensByModelOption(rows: Array<{ model: string; tokens: number }>) {
  const sorted = [...rows].reverse() // largest at the top after axis inversion
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    grid: { left: '3%', right: '10%', bottom: '4%', top: '4%', containLabel: true },
    xAxis: { type: 'value', axisLabel: AXIS_LABEL, splitLine: GRID_LINE },
    yAxis: {
      type: 'category',
      data: sorted.map((r) => r.model),
      axisLabel: { ...AXIS_LABEL, width: 150, overflow: 'truncate' },
      axisLine: GRID_LINE,
    },
    series: [{
      type: 'bar',
      data: sorted.map((r) => r.tokens),
      itemStyle: { color: C.bar, borderRadius: [0, 4, 4, 0] },
      barMaxWidth: 18,
      label: { show: true, position: 'right', color: '#94a3b8', fontSize: 10, formatter: (p: { value: number }) => formatNumber(p.value) },
    }],
  }
}

export default function AdminAnalyticsPage() {
  const [days, setDays] = useState(14)
  const q = useQuery({
    queryKey: ['admin-analytics', days],
    queryFn: () => adminService.analytics(days),
  })

  if (q.isLoading) {
    return (
      <div className="p-6 max-w-6xl mx-auto space-y-3">
        {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
      </div>
    )
  }
  if (q.isError || !q.data) {
    return <p className="p-6 text-red-400 text-sm">Could not load analytics.</p>
  }

  const { users, content, ai } = q.data

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-text-primary flex items-center gap-2">
            <BarChart3 className="w-6 h-6 text-neon-blue" /> Analytics
          </h1>
          <p className="text-text-secondary text-sm mt-1">Platform activity and AI token consumption</p>
        </div>
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="input-cyber text-xs py-1.5"
          aria-label="Time window"
        >
          <option value={7}>Last 7 days</option>
          <option value={14}>Last 14 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </div>

      {/* AI headline numbers */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile icon={Bot} label="AI calls" value={formatNumber(ai.total_calls)} hint={`${formatNumber(ai.calls_24h)} in the last 24h`} />
        <StatTile icon={Coins} label="Total tokens" value={formatNumber(ai.total_tokens)} hint={`${formatNumber(ai.input_tokens)} in · ${formatNumber(ai.output_tokens)} out`} />
        <StatTile icon={Timer} label="Avg latency" value={ai.avg_latency_ms != null ? `${formatNumber(Math.round(ai.avg_latency_ms))} ms` : '—'} />
        <StatTile icon={Activity} label="Success rate" value={ai.success_rate != null ? `${(ai.success_rate * 100).toFixed(1)}%` : '—'} />
      </div>

      {/* Platform numbers */}
      <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
        <StatTile icon={Users} label="Users" value={formatNumber(users.total)} hint={`${users.active} active · +${users.new_7d} this week`} />
        <StatTile icon={Activity} label="Datasets" value={formatNumber(content.datasets)} />
        <StatTile icon={Activity} label="Insights" value={formatNumber(content.insights)} />
        <StatTile icon={Activity} label="Dashboards" value={formatNumber(content.dashboards)} />
        <StatTile icon={Activity} label="Reports" value={formatNumber(content.reports)} />
        <StatTile icon={Activity} label="AI messages" value={formatNumber(content.messages)} hint={`${content.conversations} conversations`} />
      </div>

      {/* Tokens over time */}
      <div className="card">
        <h3 className="text-sm font-semibold text-text-primary mb-2">Token usage — last {q.data.window_days} days</h3>
        {ai.tokens_by_day.length === 0 ? (
          <p className="text-xs text-text-muted py-8 text-center">No AI usage recorded yet — token tracking starts with the next AI call.</p>
        ) : (
          <EChartWrapper option={tokensByDayOption(ai.tokens_by_day)} height={260} />
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Tokens by model */}
        <div className="card">
          <h3 className="text-sm font-semibold text-text-primary mb-2">Tokens by model</h3>
          {ai.by_model.length === 0 ? (
            <p className="text-xs text-text-muted py-8 text-center">No data yet.</p>
          ) : (
            <EChartWrapper option={tokensByModelOption(ai.by_model)} height={Math.max(160, ai.by_model.length * 44)} />
          )}
        </div>

        {/* By feature */}
        <div className="card">
          <h3 className="text-sm font-semibold text-text-primary mb-2">Usage by feature</h3>
          {ai.by_feature.length === 0 ? (
            <p className="text-xs text-text-muted py-8 text-center">No data yet.</p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-text-muted">
                  <th className="text-left py-2 pr-3 font-medium">Feature</th>
                  <th className="text-right py-2 px-3 font-medium">Calls</th>
                  <th className="text-right py-2 px-3 font-medium">Tokens</th>
                  <th className="text-right py-2 pl-3 font-medium">Avg latency</th>
                </tr>
              </thead>
              <tbody>
                {ai.by_feature.map((f) => (
                  <tr key={f.feature} className="border-b border-border/40">
                    <td className="py-2 pr-3 text-text-primary">{f.feature}</td>
                    <td className="py-2 px-3 text-right text-text-secondary">{formatNumber(f.calls)}</td>
                    <td className="py-2 px-3 text-right text-text-secondary">{formatNumber(f.tokens)}</td>
                    <td className="py-2 pl-3 text-right text-text-secondary">
                      {f.avg_latency_ms != null ? `${formatNumber(Math.round(f.avg_latency_ms))} ms` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Top consumers */}
      <div className="card">
        <h3 className="text-sm font-semibold text-text-primary mb-2">Top AI consumers</h3>
        {ai.top_users.length === 0 ? (
          <p className="text-xs text-text-muted py-8 text-center">No data yet.</p>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-text-muted">
                <th className="text-left py-2 pr-3 font-medium">User</th>
                <th className="text-right py-2 px-3 font-medium">Calls</th>
                <th className="text-right py-2 pl-3 font-medium">Tokens</th>
              </tr>
            </thead>
            <tbody>
              {ai.top_users.map((u) => (
                <tr key={u.email} className="border-b border-border/40">
                  <td className="py-2 pr-3 text-text-primary">{u.email}</td>
                  <td className="py-2 px-3 text-right text-text-secondary">{formatNumber(u.calls)}</td>
                  <td className="py-2 pl-3 text-right text-text-secondary">{formatNumber(u.tokens)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

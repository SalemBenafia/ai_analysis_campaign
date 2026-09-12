'use client'

import { useQuery } from '@tanstack/react-query'
import { Database, BarChart2, MessageSquare, FileText, Wand2, Plus, Lightbulb, Pin } from 'lucide-react'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { datasetService, reportService, insightService } from '@/lib/api/services'
import { SkeletonCard } from '@/components/common/loading-page'
import { ChartRender } from '@/components/features/charts/chart-render'
import { useInsightExecution } from '@/hooks/use-insights'
import { formatBytes, formatNumber } from '@/lib/utils'
import { useAuth } from '@/hooks/use-auth'
import type { Dataset, Insight } from '@/types'

function PinnedInsightCard({ insight }: { insight: Insight }) {
  const execQ = useInsightExecution(insight.id)
  return (
    <Link href="/insights" className="card hover:border-neon-blue/30 transition-colors">
      <div className="flex items-center gap-2 mb-2">
        <Pin className="w-3.5 h-3.5 text-neon-blue" />
        <span className="text-sm font-medium text-text-primary truncate">{insight.name}</span>
      </div>
      <div className="h-32 flex items-center justify-center">
        {execQ.data?.echart_config ? <ChartRender config={execQ.data.echart_config} height={128} /> : <span className="text-xs text-text-muted">Loading…</span>}
      </div>
    </Link>
  )
}

function StatusBadge({ status }: { status: Dataset['status'] }) {
  const cls = {
    ready: 'bg-neon-green/10 text-neon-green border-neon-green/30',
    processing: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30',
    error: 'bg-red-500/10 text-red-400 border-red-500/30',
    uploading: 'bg-neon-blue/10 text-neon-blue border-neon-blue/30',
  }[status]
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border ${cls}`}>
      {status}
    </span>
  )
}

export default function DashboardPage() {
  const { principal } = useAuth()
  const datasetsQ = useQuery({ queryKey: ['datasets'], queryFn: () => datasetService.list() })
  const reportsQ = useQuery({ queryKey: ['reports'], queryFn: () => reportService.list() })
  const insightsQ = useQuery({ queryKey: ['insights'], queryFn: () => insightService.list() })
  const pinned = (insightsQ.data?.insights ?? []).filter((i) => i.is_pinned).slice(0, 3)

  const [today, setToday] = useState('')
  useEffect(() => {
    setToday(new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' }))
  }, [])

  const datasets = datasetsQ.data?.datasets ?? []
  const reports = reportsQ.data?.reports ?? []
  const readyDatasets = datasets.filter((d) => d.status === 'ready')

  const stats = [
    { icon: Database, label: 'Datasets', value: datasets.length, sub: readyDatasets.length + ' ready' },
    { icon: BarChart2, label: 'Total Rows', value: formatNumber(readyDatasets.reduce((a, d) => a + (d.row_count ?? 0), 0)), sub: 'across all datasets' },
    { icon: FileText, label: 'Reports', value: reports.length, sub: reports.filter((r) => r.status === 'ready').length + ' ready' },
    { icon: MessageSquare, label: 'AI Copilot', value: 'Ready', sub: 'Ask your data anything' },
  ]

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-text-primary">
          Welcome back, {principal?.first_name} 👋
        </h1>
        <p className="text-text-secondary text-sm mt-1">{today}</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {datasetsQ.isLoading
          ? Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
          : stats.map(({ icon: Icon, label, value, sub }) => (
              <div key={label} className="stat-card">
                <div className="flex items-center gap-2 mb-2">
                  <Icon className="w-4 h-4 text-neon-blue" />
                  <span className="stat-label">{label}</span>
                </div>
                <div className="stat-value">{value}</div>
                <div className="text-xs text-text-muted">{sub}</div>
              </div>
            ))}
      </div>

      {/* Pinned insights */}
      {pinned.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-text-primary flex items-center gap-2">
              <Lightbulb className="w-5 h-5 text-neon-blue" /> Pinned Insights
            </h2>
            <Link href="/insights" className="text-neon-blue text-sm hover:underline">View all</Link>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {pinned.map((insight) => <PinnedInsightCard key={insight.id} insight={insight} />)}
          </div>
        </div>
      )}

      {/* Recent datasets */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-text-primary">Recent Datasets</h2>
          <Link href="/datasets" className="text-neon-blue text-sm hover:underline flex items-center gap-1">
            <Plus className="w-3 h-3" /> Add dataset
          </Link>
        </div>
        {datasets.length === 0 ? (
          <div className="card text-center py-12 border-dashed">
            <Database className="w-10 h-10 text-text-muted mx-auto mb-3" />
            <p className="text-text-secondary text-sm mb-4">No datasets yet. Upload your first Meta Ads export.</p>
            <Link href="/datasets" className="btn-primary inline-flex items-center gap-2">
              <Plus className="w-4 h-4" /> Upload dataset
            </Link>
          </div>
        ) : (
          <div className="space-y-2">
            {datasets.slice(0, 5).map((ds) => (
              <Link
                key={ds.id}
                href={'/datasets/' + ds.id}
                className="card flex items-center justify-between hover:border-neon-blue/30 transition-colors group"
              >
                <div className="flex items-center gap-3">
                  <Database className="w-4 h-4 text-neon-blue flex-shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-text-primary group-hover:text-neon-blue transition-colors">
                      {ds.name}
                    </p>
                    <p className="text-xs text-text-muted">
                      {formatBytes(ds.file_size_bytes)} · {ds.row_count ? formatNumber(ds.row_count) + ' rows' : ds.file_format.toUpperCase()}
                    </p>
                  </div>
                </div>
                <StatusBadge status={ds.status} />
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Quick actions */}
      <div>
        <h2 className="text-lg font-semibold text-text-primary mb-4">Quick Actions</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { href: '/datasets', icon: Database, label: 'Upload Data' },
            { href: '/copilot', icon: MessageSquare, label: 'Ask AI Copilot' },
            { href: '/builder', icon: Wand2, label: 'Visual Builder' },
            { href: '/reports', icon: FileText, label: 'New Report' },
          ].map(({ href, icon: Icon, label }) => (
            <Link
              key={label}
              href={href}
              className="card flex flex-col items-center gap-3 py-6 hover:border-neon-blue/30 hover:bg-background-hover transition-all group"
            >
              <Icon className="w-6 h-6 text-neon-blue group-hover:scale-110 transition-transform" />
              <span className="text-xs font-medium text-text-secondary group-hover:text-text-primary">{label}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}

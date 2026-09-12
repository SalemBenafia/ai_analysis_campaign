'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Pin, PinOff, Trash2, Pencil, LayoutGrid, Loader2, Sparkles } from 'lucide-react'
import { useInsightExecution } from '@/hooks/use-insights'
import { ChartRender } from '@/components/features/charts/chart-render'
import { AddToDashboardDialog } from './add-to-dashboard-dialog'
import { cn } from '@/lib/utils'
import type { Insight } from '@/types'

interface InsightCardProps {
  insight: Insight
  onDelete: (id: string) => void
  onTogglePin: (id: string, pinned: boolean) => void
}

export function InsightCard({ insight, onDelete, onTogglePin }: InsightCardProps) {
  const [showAdd, setShowAdd] = useState(false)
  const [explain, setExplain] = useState(false)
  const execQ = useInsightExecution(insight.id, explain)

  const config = execQ.data?.echart_config

  return (
    <div className="card flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-medium text-text-primary truncate">{insight.name}</h3>
          {insight.description && <p className="text-xs text-text-muted truncate">{insight.description}</p>}
        </div>
        <button
          onClick={() => onTogglePin(insight.id, !insight.is_pinned)}
          className={cn('flex-shrink-0', insight.is_pinned ? 'text-neon-blue' : 'text-text-muted hover:text-text-primary')}
          title={insight.is_pinned ? 'Unpin' : 'Pin'}
        >
          {insight.is_pinned ? <Pin className="w-4 h-4" /> : <PinOff className="w-4 h-4" />}
        </button>
      </div>

      <div className="min-h-[180px] flex items-center justify-center rounded bg-background/40">
        {execQ.isLoading ? (
          <Loader2 className="w-5 h-5 animate-spin text-neon-blue" />
        ) : execQ.isError ? (
          <p className="text-xs text-red-400">Failed to run</p>
        ) : config ? (
          <ChartRender config={config} height={180} />
        ) : (
          <p className="text-xs text-text-muted">No data</p>
        )}
      </div>

      {execQ.data?.ai_explanation && (
        <p className="text-xs text-text-secondary border-l-2 border-neon-purple/50 pl-2">{execQ.data.ai_explanation}</p>
      )}

      <div className="flex items-center gap-2 text-text-muted">
        <button onClick={() => setExplain(true)} className="hover:text-neon-purple" title="Explain with AI">
          <Sparkles className="w-4 h-4" />
        </button>
        <Link href={`/builder?insight=${insight.id}`} className="hover:text-neon-blue" title="Edit in builder">
          <Pencil className="w-4 h-4" />
        </Link>
        <button onClick={() => setShowAdd(true)} className="hover:text-neon-blue" title="Add to dashboard">
          <LayoutGrid className="w-4 h-4" />
        </button>
        <button onClick={() => onDelete(insight.id)} className="hover:text-red-400 ml-auto" title="Delete">
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      {showAdd && <AddToDashboardDialog title={insight.name} insightId={insight.id} onClose={() => setShowAdd(false)} />}
    </div>
  )
}

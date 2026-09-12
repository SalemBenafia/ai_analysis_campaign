'use client'

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { X, Lightbulb } from 'lucide-react'
import { dashboardService, insightService } from '@/lib/api/services'
import { useUIStore } from '@/store/use-ui-store'

export function AddWidgetDrawer({ dashboardId, onClose }: { dashboardId: string; onClose: () => void }) {
  const { addToast } = useUIStore()
  const qc = useQueryClient()
  const [title, setTitle] = useState('')

  const insightsQ = useQuery({ queryKey: ['insights'], queryFn: () => insightService.list() })

  const addMutation = useMutation({
    mutationFn: (insightId: string) => {
      const insight = insightsQ.data?.insights.find((i) => i.id === insightId)
      return dashboardService.addWidget(dashboardId, {
        title: title || insight?.name || 'Widget',
        insight_id: insightId,
      })
    },
    onSuccess: () => {
      addToast({ type: 'success', title: 'Widget added' })
      qc.invalidateQueries({ queryKey: ['dashboard', dashboardId] })
      onClose()
    },
    onError: () => addToast({ type: 'error', title: 'Failed to add widget' }),
  })

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50" onClick={onClose}>
      <div className="w-full max-w-md h-full bg-background-secondary border-l border-border p-5 overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-text-primary">Add Widget from Insight</h3>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary"><X className="w-4 h-4" /></button>
        </div>

        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Optional widget title" className="input-cyber w-full mb-4" />

        <div className="space-y-2">
          {(insightsQ.data?.insights ?? []).length === 0 && (
            <p className="text-sm text-text-muted">No saved insights yet. Create one in the Insights page or Builder.</p>
          )}
          {(insightsQ.data?.insights ?? []).map((insight) => (
            <button
              key={insight.id}
              onClick={() => addMutation.mutate(insight.id)}
              disabled={addMutation.isPending}
              className="w-full flex items-center gap-3 p-3 rounded-md border border-border hover:border-neon-blue/40 text-left transition-colors disabled:opacity-40"
            >
              <Lightbulb className="w-4 h-4 text-neon-blue flex-shrink-0" />
              <div className="min-w-0">
                <p className="text-sm text-text-primary truncate">{insight.name}</p>
                {insight.description && <p className="text-xs text-text-muted truncate">{insight.description}</p>}
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

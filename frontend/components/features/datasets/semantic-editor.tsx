'use client'

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { FunctionSquare, Pencil, Plus, Trash2, Loader2 } from 'lucide-react'
import { semanticService } from '@/lib/api/services'
import { useSemanticMembers } from '@/hooks/use-semantic'
import { useUIStore } from '@/store/use-ui-store'
import { MetricFormulaDialog } from './metric-formula-dialog'
import type { ComputedMetric, DatasetColumn } from '@/types'

export function SemanticEditor({ datasetId, cols }: { datasetId: string; cols: DatasetColumn[] }) {
  const { addToast } = useUIStore()
  const qc = useQueryClient()
  const membersQ = useSemanticMembers(datasetId)
  // null = closed; { metric: undefined } = create; { metric } = edit
  const [dialog, setDialog] = useState<{ metric?: ComputedMetric } | null>(null)

  const toggleMutation = useMutation({
    mutationFn: ({ columnId, patch }: { columnId: string; patch: Record<string, boolean> }) =>
      semanticService.updateColumn(datasetId, columnId, patch),
    onSuccess: () => {
      addToast({ type: 'success', title: 'Updated — refreshing model' })
      qc.invalidateQueries({ queryKey: ['semantic-members', datasetId] })
      qc.invalidateQueries({ queryKey: ['dataset', datasetId] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (metricId: string) => semanticService.deleteMetric(datasetId, metricId),
    onSuccess: () => {
      addToast({ type: 'success', title: 'Metric deleted' })
      qc.invalidateQueries({ queryKey: ['semantic-members', datasetId] })
    },
  })

  const computed = membersQ.data?.computed_metrics ?? []
  const measures = membersQ.data?.measures ?? []

  return (
    <div className="space-y-5">
      {/* Computed metrics */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <FunctionSquare className="w-4 h-4 text-neon-purple" /> Computed Metrics
          </h3>
          <button onClick={() => setDialog({})} className="btn-ghost flex items-center gap-1.5 text-xs">
            <Plus className="w-3.5 h-3.5" /> New Metric
          </button>
        </div>
        {membersQ.isLoading ? (
          <div className="flex justify-center py-4"><Loader2 className="w-4 h-4 animate-spin text-neon-blue" /></div>
        ) : computed.length === 0 ? (
          <p className="text-xs text-text-muted">No computed metrics. Marketing metrics (ROAS, CTR…) are auto-detected on upload.</p>
        ) : (
          <div className="space-y-1.5">
            {computed.map((m) => (
              <div key={m.id} className="flex items-center gap-2 text-sm bg-background/40 rounded px-3 py-2">
                <span className="text-neon-purple font-medium">{m.display_name}</span>
                <span className="text-xs text-text-muted truncate flex-1">{m.description}</span>
                {m.is_auto && <span className="text-[10px] text-text-muted border border-border rounded px-1.5 py-0.5">auto</span>}
                <button onClick={() => setDialog({ metric: m })} className="text-text-muted hover:text-neon-blue" title="Edit formula"><Pencil className="w-3.5 h-3.5" /></button>
                <button onClick={() => deleteMutation.mutate(m.id)} className="text-text-muted hover:text-red-400"><Trash2 className="w-3.5 h-3.5" /></button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Column roles */}
      <div className="card">
        <h3 className="text-sm font-semibold text-text-primary mb-3">Column Roles</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left py-2 px-3 text-text-muted">Column</th>
                <th className="text-left py-2 px-3 text-text-muted">Type</th>
                <th className="text-center py-2 px-3 text-text-muted">Metric</th>
                <th className="text-center py-2 px-3 text-text-muted">Dimension</th>
              </tr>
            </thead>
            <tbody>
              {cols.map((col) => (
                <tr key={col.id ?? col.name} className="border-b border-border/40">
                  <td className="py-2 px-3 text-text-primary">{col.display_name}</td>
                  <td className="py-2 px-3 text-text-muted">{col.col_type}</td>
                  <td className="py-2 px-3 text-center">
                    <input
                      type="checkbox"
                      checked={col.is_metric}
                      disabled={!col.id || toggleMutation.isPending}
                      onChange={(e) => col.id && toggleMutation.mutate({ columnId: col.id, patch: { is_metric: e.target.checked } })}
                    />
                  </td>
                  <td className="py-2 px-3 text-center">
                    <input
                      type="checkbox"
                      checked={col.is_dimension}
                      disabled={!col.id || toggleMutation.isPending}
                      onChange={(e) => col.id && toggleMutation.mutate({ columnId: col.id, patch: { is_dimension: e.target.checked } })}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!cols.some((c) => c.id) && (
          <p className="text-[11px] text-text-muted mt-2">Re-upload needed for role editing on legacy datasets.</p>
        )}
      </div>

      {dialog && (
        <MetricFormulaDialog
          datasetId={datasetId}
          measures={measures}
          metric={dialog.metric}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  )
}

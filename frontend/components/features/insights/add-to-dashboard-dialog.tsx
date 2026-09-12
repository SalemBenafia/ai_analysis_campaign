'use client'

import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { X, Plus } from 'lucide-react'
import { dashboardService, copilotService } from '@/lib/api/services'
import { useUIStore } from '@/store/use-ui-store'

interface AddToDashboardDialogProps {
  title: string
  // one of these two sources:
  insightId?: string
  messageId?: string
  onClose: () => void
}

export function AddToDashboardDialog({ title, insightId, messageId, onClose }: AddToDashboardDialogProps) {
  const { addToast } = useUIStore()
  const [selected, setSelected] = useState('')
  const [newName, setNewName] = useState('')
  const [widgetTitle, setWidgetTitle] = useState(title)

  const dashboardsQ = useQuery({ queryKey: ['dashboards'], queryFn: () => dashboardService.list() })

  const mutation = useMutation({
    mutationFn: async () => {
      let dashboardId = selected
      if (!dashboardId && newName) {
        const created = await dashboardService.create({ name: newName })
        dashboardId = created.dashboard.id
      }
      if (!dashboardId) throw new Error('No dashboard')
      if (messageId) {
        return copilotService.addToDashboard(messageId, dashboardId, widgetTitle)
      }
      return dashboardService.addWidget(dashboardId, { title: widgetTitle, insight_id: insightId })
    },
    onSuccess: () => {
      addToast({ type: 'success', title: 'Added to dashboard' })
      onClose()
    },
    onError: () => addToast({ type: 'error', title: 'Failed to add widget' }),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="card w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-text-primary">Add to Dashboard</h3>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary"><X className="w-4 h-4" /></button>
        </div>
        <div className="space-y-3">
          <input value={widgetTitle} onChange={(e) => setWidgetTitle(e.target.value)} placeholder="Widget title" className="input-cyber w-full" />
          <select value={selected} onChange={(e) => { setSelected(e.target.value); setNewName('') }} className="input-cyber w-full">
            <option value="">Choose dashboard…</option>
            {(dashboardsQ.data?.dashboards ?? []).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          {!selected && (
            <div className="flex items-center gap-2">
              <Plus className="w-4 h-4 text-text-muted" />
              <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="…or create new dashboard" className="input-cyber flex-1" />
            </div>
          )}
          <button
            onClick={() => mutation.mutate()}
            disabled={(!selected && !newName) || !widgetTitle || mutation.isPending}
            className="btn-primary w-full disabled:opacity-40"
          >
            {mutation.isPending ? 'Adding…' : 'Add Widget'}
          </button>
        </div>
      </div>
    </div>
  )
}

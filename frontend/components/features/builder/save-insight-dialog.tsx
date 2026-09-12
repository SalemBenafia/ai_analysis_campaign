'use client'

import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { insightService } from '@/lib/api/services'
import { useUIStore } from '@/store/use-ui-store'

interface SaveInsightDialogProps {
  datasetId: string
  definition: Record<string, unknown>
  existingId?: string
  onClose: () => void
  onSaved?: () => void
}

export function SaveInsightDialog({ datasetId, definition, existingId, onClose, onSaved }: SaveInsightDialogProps) {
  const { addToast } = useUIStore()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  const mutation = useMutation({
    mutationFn: () =>
      existingId
        ? insightService.update(existingId, { name, description, insight_definition: definition })
        : insightService.create({ dataset_id: datasetId, name, description, insight_type: 'custom', insight_definition: definition }),
    onSuccess: () => {
      addToast({ type: 'success', title: existingId ? 'Insight updated' : 'Insight saved' })
      onSaved?.()
      onClose()
    },
    onError: () => addToast({ type: 'error', title: 'Save failed' }),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="card w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold text-text-primary">{existingId ? 'Update Insight' : 'Save Insight'}</h3>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary"><X className="w-4 h-4" /></button>
        </div>
        <div className="space-y-3">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Insight name" className="input-cyber w-full" autoFocus />
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description (optional)" rows={2} className="input-cyber w-full resize-none" />
          <button
            onClick={() => mutation.mutate()}
            disabled={!name || mutation.isPending}
            className="btn-primary w-full disabled:opacity-40"
          >
            {mutation.isPending ? 'Saving…' : existingId ? 'Update' : 'Save Insight'}
          </button>
        </div>
      </div>
    </div>
  )
}

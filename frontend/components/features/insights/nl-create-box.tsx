'use client'

import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Sparkles, Loader2, Save } from 'lucide-react'
import { datasetService, insightService } from '@/lib/api/services'
import { ChartRender } from '@/components/features/charts/chart-render'
import { buildFromDefinition } from '@/lib/charts/build-option'
import { SaveInsightDialog } from '@/components/features/builder/save-insight-dialog'
import { useUIStore } from '@/store/use-ui-store'

export function NLCreateBox() {
  const { addToast } = useUIStore()
  const [datasetId, setDatasetId] = useState('')
  const [prompt, setPrompt] = useState('')
  const [showSave, setShowSave] = useState(false)

  const datasetsQ = useQuery({ queryKey: ['datasets'], queryFn: () => datasetService.list() })
  const ready = (datasetsQ.data?.datasets ?? []).filter((d) => d.status === 'ready')

  const mutation = useMutation({
    mutationFn: () => insightService.nlCreate(datasetId, prompt),
    onError: () => addToast({ type: 'error', title: 'Could not build insight', message: 'Try rephrasing your request.' }),
  })

  const result = mutation.data
  const config = result ? buildFromDefinition(result.rows, result.definition) : null

  return (
    <div className="card space-y-3">
      <div className="flex items-center gap-2">
        <Sparkles className="w-4 h-4 text-neon-purple" />
        <h3 className="font-medium text-text-primary">Create insight with AI</h3>
      </div>
      <div className="flex flex-col sm:flex-row gap-2">
        <select value={datasetId} onChange={(e) => setDatasetId(e.target.value)} className="input-cyber sm:w-52">
          <option value="">Dataset…</option>
          {ready.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        <input
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && datasetId && prompt && mutation.mutate()}
          placeholder="e.g. top 5 campaigns by ROAS in the last 30 days"
          className="input-cyber flex-1"
        />
        <button
          onClick={() => mutation.mutate()}
          disabled={!datasetId || !prompt || mutation.isPending}
          className="btn-primary flex items-center gap-2 disabled:opacity-40 whitespace-nowrap"
        >
          {mutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
          Generate
        </button>
      </div>

      {config && (
        <div className="space-y-2">
          <ChartRender config={config} height={260} />
          <div className="flex justify-end">
            <button onClick={() => setShowSave(true)} className="btn-ghost flex items-center gap-2 text-sm">
              <Save className="w-4 h-4" /> Save this insight
            </button>
          </div>
        </div>
      )}

      {showSave && result && (
        <SaveInsightDialog datasetId={datasetId} definition={result.definition} onClose={() => setShowSave(false)} />
      )}
    </div>
  )
}

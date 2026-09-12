'use client'

import { Suspense, useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { useQuery } from '@tanstack/react-query'
import { Wand2 } from 'lucide-react'
import { datasetService, insightService } from '@/lib/api/services'
import { VisualBuilder } from '@/components/features/builder/visual-builder'
import { useBuilderStore } from '@/components/features/builder/builder-state'

function BuilderInner() {
  const params = useSearchParams()
  const editId = params.get('insight') || undefined
  const [selectedDs, setSelectedDs] = useState('')
  const loadDefinition = useBuilderStore((s) => s.loadDefinition)

  const datasetsQ = useQuery({ queryKey: ['datasets'], queryFn: () => datasetService.list() })
  const ready = (datasetsQ.data?.datasets ?? []).filter((d) => d.status === 'ready')

  // Deep-link: load an existing insight into the builder for editing.
  const insightQ = useQuery({
    queryKey: ['insight-edit', editId],
    queryFn: () => insightService.list(),
    enabled: !!editId,
  })

  useEffect(() => {
    if (!editId || !insightQ.data) return
    const insight = insightQ.data.insights.find((i) => i.id === editId)
    if (insight?.dataset_id) {
      setSelectedDs(insight.dataset_id)
      loadDefinition(insight.dataset_id, insight.insight_definition)
    }
  }, [editId, insightQ.data, loadDefinition])

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary flex items-center gap-2">
            <Wand2 className="w-6 h-6 text-neon-blue" />
            Visual Builder
          </h1>
          <p className="text-text-secondary text-sm mt-1">
            Drag fields onto the shelves to build charts. Metrics like ROAS are ready to use.
          </p>
        </div>
        <select
          value={selectedDs}
          onChange={(e) => setSelectedDs(e.target.value)}
          className="input-cyber min-w-[200px]"
        >
          <option value="">Select dataset…</option>
          {ready.map((ds) => <option key={ds.id} value={ds.id}>{ds.name}</option>)}
        </select>
      </div>

      {selectedDs ? (
        <VisualBuilder datasetId={selectedDs} editInsightId={editId} />
      ) : (
        <div className="card text-center py-16 text-text-muted">
          Select a ready dataset to start building visualizations.
        </div>
      )}
    </div>
  )
}

export default function BuilderPage() {
  return (
    <Suspense fallback={<div className="p-6 text-text-muted">Loading…</div>}>
      <BuilderInner />
    </Suspense>
  )
}

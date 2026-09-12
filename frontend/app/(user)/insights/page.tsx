'use client'

import { Lightbulb, Loader2 } from 'lucide-react'
import { useInsights } from '@/hooks/use-insights'
import { InsightCard } from '@/components/features/insights/insight-card'
import { NLCreateBox } from '@/components/features/insights/nl-create-box'

export default function InsightsPage() {
  const { insights, isLoading, deleteInsight, setPinned } = useInsights()

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary flex items-center gap-2">
          <Lightbulb className="w-6 h-6 text-neon-blue" />
          Insights
        </h1>
        <p className="text-text-secondary text-sm mt-1">Saved insights run live against your semantic layer.</p>
      </div>

      <NLCreateBox />

      {isLoading ? (
        <div className="flex items-center justify-center h-40 text-text-muted">
          <Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading insights…
        </div>
      ) : insights.length === 0 ? (
        <div className="card text-center py-16 text-text-muted">
          No saved insights yet. Create one above, or build one in the Visual Builder.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {insights.map((insight) => (
            <InsightCard
              key={insight.id}
              insight={insight}
              onDelete={deleteInsight}
              onTogglePin={(id, pinned) => setPinned({ id, pinned })}
            />
          ))}
        </div>
      )}
    </div>
  )
}

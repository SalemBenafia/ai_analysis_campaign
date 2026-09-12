'use client'

import { useQuery } from '@tanstack/react-query'
import { Loader2, Trash2, GripVertical } from 'lucide-react'
import { dashboardService } from '@/lib/api/services'
import { ChartRender } from '@/components/features/charts/chart-render'
import type { Widget } from '@/types'

interface WidgetCardProps {
  dashboardId: string
  widget: Widget
  editing: boolean
  onDelete: (id: string) => void
}

export function WidgetCard({ dashboardId, widget, editing, onDelete }: WidgetCardProps) {
  const q = useQuery({
    queryKey: ['widget-data', dashboardId, widget.id],
    queryFn: () => dashboardService.widgetData(dashboardId, widget.id),
    refetchInterval: widget.refresh_interval ? widget.refresh_interval * 1000 : false,
    staleTime: 10_000,
  })

  return (
    <div className="card h-full flex flex-col overflow-hidden">
      <div className="flex items-center gap-2 mb-2">
        {editing && <GripVertical className="w-4 h-4 text-text-muted drag-handle cursor-move flex-shrink-0" />}
        <h4 className="text-sm font-medium text-text-primary truncate flex-1">{widget.title}</h4>
        {editing && (
          <button onClick={() => onDelete(widget.id)} className="text-text-muted hover:text-red-400 flex-shrink-0">
            <Trash2 className="w-4 h-4" />
          </button>
        )}
      </div>
      <div className="flex-1 min-h-0 flex items-center justify-center">
        {q.isLoading ? (
          <Loader2 className="w-5 h-5 animate-spin text-neon-blue" />
        ) : q.isError ? (
          <p className="text-xs text-red-400">Failed to load</p>
        ) : q.data?.echart_config ? (
          <ChartRender config={q.data.echart_config} height="100%" />
        ) : (
          <p className="text-xs text-text-muted">No data</p>
        )}
      </div>
    </div>
  )
}

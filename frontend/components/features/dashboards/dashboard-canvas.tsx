'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import GridLayout, { WidthProvider, type Layout } from 'react-grid-layout'
import { useQueryClient } from '@tanstack/react-query'
import { dashboardService } from '@/lib/api/services'
import { WidgetCard } from './widget-card'
import type { Widget } from '@/types'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'

const ReactGridLayout = WidthProvider(GridLayout)

interface DashboardCanvasProps {
  dashboardId: string
  widgets: Widget[]
  editing: boolean
}

export function DashboardCanvas({ dashboardId, widgets, editing }: DashboardCanvasProps) {
  const qc = useQueryClient()
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const layout: Layout[] = useMemo(
    () =>
      widgets.map((w, i) => ({
        i: w.id,
        x: w.position?.x ?? (i * 4) % 12,
        y: w.position?.y ?? Math.floor(i / 3) * 4,
        w: w.position?.w ?? 4,
        h: w.position?.h ?? 4,
        minW: 2,
        minH: 3,
      })),
    [widgets],
  )

  function persist(next: Layout[]) {
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => {
      dashboardService.saveLayout(
        dashboardId,
        next.map((l) => ({ widget_id: l.i, x: l.x, y: l.y, w: l.w, h: l.h })),
      )
    }, 700)
  }

  function handleDelete(widgetId: string) {
    dashboardService.deleteWidget(dashboardId, widgetId).then(() => {
      qc.invalidateQueries({ queryKey: ['dashboard', dashboardId] })
    })
  }

  useEffect(() => () => { if (saveTimer.current) clearTimeout(saveTimer.current) }, [])

  if (widgets.length === 0) {
    return (
      <div className="card text-center py-16 text-text-muted">
        This dashboard is empty. Click “Add Widget” to add insights.
      </div>
    )
  }

  return (
    <ReactGridLayout
      className="layout"
      layout={layout}
      cols={12}
      rowHeight={80}
      isDraggable={editing}
      isResizable={editing}
      draggableHandle=".drag-handle"
      onLayoutChange={(l) => editing && persist(l)}
      margin={[16, 16]}
    >
      {widgets.map((w) => (
        <div key={w.id}>
          <WidgetCard dashboardId={dashboardId} widget={w} editing={editing} onDelete={handleDelete} />
        </div>
      ))}
    </ReactGridLayout>
  )
}

'use client'

import { use, useState } from 'react'
import dynamic from 'next/dynamic'
import Link from 'next/link'
import { ArrowLeft, Plus, Pencil, Check, Loader2 } from 'lucide-react'
import { useDashboard } from '@/hooks/use-dashboards'
import { AddWidgetDrawer } from '@/components/features/dashboards/add-widget-drawer'

// react-grid-layout needs window — load client-only.
const DashboardCanvas = dynamic(
  () => import('@/components/features/dashboards/dashboard-canvas').then((m) => m.DashboardCanvas),
  { ssr: false, loading: () => <div className="flex justify-center py-16"><Loader2 className="w-6 h-6 animate-spin text-neon-blue" /></div> },
)

export default function DashboardDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const { data, isLoading } = useDashboard(id)
  const [editing, setEditing] = useState(false)
  const [showAdd, setShowAdd] = useState(false)

  if (isLoading) {
    return <div className="flex items-center justify-center h-64 text-text-muted"><Loader2 className="w-6 h-6 animate-spin" /></div>
  }
  if (!data) return <div className="p-6 text-text-muted">Dashboard not found.</div>

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/dashboards" className="text-text-muted hover:text-text-primary"><ArrowLeft className="w-5 h-5" /></Link>
          <h1 className="text-xl font-bold text-text-primary">{data.dashboard.name}</h1>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowAdd(true)} className="btn-ghost flex items-center gap-2 text-sm">
            <Plus className="w-4 h-4" /> Add Widget
          </button>
          <button onClick={() => setEditing((e) => !e)} className="btn-primary flex items-center gap-2 text-sm">
            {editing ? <><Check className="w-4 h-4" /> Done</> : <><Pencil className="w-4 h-4" /> Edit Layout</>}
          </button>
        </div>
      </div>

      {editing && (
        <p className="text-xs text-neon-blue">Drag widgets by their handle and resize from the corner. Layout saves automatically.</p>
      )}

      <DashboardCanvas dashboardId={id} widgets={data.widgets} editing={editing} />

      {showAdd && <AddWidgetDrawer dashboardId={id} onClose={() => setShowAdd(false)} />}
    </div>
  )
}

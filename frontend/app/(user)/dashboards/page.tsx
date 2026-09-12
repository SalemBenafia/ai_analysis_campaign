'use client'

import { useState } from 'react'
import Link from 'next/link'
import { LayoutGrid, Plus, Trash2, Loader2 } from 'lucide-react'
import { useDashboards } from '@/hooks/use-dashboards'

export default function DashboardsPage() {
  const { dashboards, isLoading, createDashboard, deleteDashboard } = useDashboards()
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')

  async function handleCreate() {
    if (!name) return
    await createDashboard({ name })
    setName('')
    setCreating(false)
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary flex items-center gap-2">
            <LayoutGrid className="w-6 h-6 text-neon-blue" />
            Dashboards
          </h1>
          <p className="text-text-secondary text-sm mt-1">Live dashboards built from your saved insights.</p>
        </div>
        <button onClick={() => setCreating(true)} className="btn-primary flex items-center gap-2">
          <Plus className="w-4 h-4" /> New Dashboard
        </button>
      </div>

      {creating && (
        <div className="card flex items-center gap-2">
          <input value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleCreate()} placeholder="Dashboard name" className="input-cyber flex-1" autoFocus />
          <button onClick={handleCreate} className="btn-primary">Create</button>
          <button onClick={() => setCreating(false)} className="btn-ghost">Cancel</button>
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center h-40 text-text-muted"><Loader2 className="w-5 h-5 animate-spin mr-2" /> Loading…</div>
      ) : dashboards.length === 0 ? (
        <div className="card text-center py-16 text-text-muted">No dashboards yet. Create one to get started.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {dashboards.map((d) => (
            <div key={d.id} className="card flex items-center justify-between group">
              <Link href={`/dashboards/${d.id}`} className="flex items-center gap-3 min-w-0 flex-1">
                <LayoutGrid className="w-5 h-5 text-neon-blue flex-shrink-0" />
                <div className="min-w-0">
                  <p className="font-medium text-text-primary truncate">{d.name}</p>
                  {d.description && <p className="text-xs text-text-muted truncate">{d.description}</p>}
                </div>
              </Link>
              <button onClick={() => deleteDashboard(d.id)} className="text-text-muted hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity">
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

'use client'

import { useQuery } from '@tanstack/react-query'
import { Activity, Database, Cpu } from 'lucide-react'
import { adminService } from '@/lib/api/services'

export default function MonitoringPage() {
  const healthQ = useQuery({ queryKey: ['admin-health'], queryFn: adminService.health, refetchInterval: 15_000 })
  const statsQ = useQuery({ queryKey: ['admin-system-stats'], queryFn: adminService.stats, refetchInterval: 30_000 })

  const health = healthQ.data as { status?: string; checks?: Record<string, string> } | undefined
  const stats = statsQ.data as { db_pool_size?: number; db_checked_out?: number; process_memory_mb?: number } | undefined

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary flex items-center gap-2">
          <Activity className="w-6 h-6 text-neon-blue" />
          System Monitoring
        </h1>
        <p className="text-text-secondary text-sm mt-1">Real-time infrastructure health</p>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {/* Services */}
        <div className="card">
          <h2 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
            <Database className="w-4 h-4 text-neon-blue" />
            Services
          </h2>
          <div className="space-y-3">
            {health?.checks
              ? Object.entries(health.checks).map(([service, status]) => (
                  <div key={service} className="flex items-center justify-between py-2 border-b border-border/50 last:border-0">
                    <span className="text-sm text-text-secondary capitalize">{service}</span>
                    <div className="flex items-center gap-2">
                      <div className={`w-2 h-2 rounded-full ${status === 'ok' ? 'bg-neon-green animate-pulse' : 'bg-red-400'}`} />
                      <span className={`text-xs font-medium ${status === 'ok' ? 'text-neon-green' : 'text-red-400'}`}>{status}</span>
                    </div>
                  </div>
                ))
              : <p className="text-text-muted text-sm">Loading…</p>}
          </div>
        </div>

        {/* Resources */}
        <div className="card">
          <h2 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
            <Cpu className="w-4 h-4 text-neon-blue" />
            Backend Resources
          </h2>
          <div className="space-y-3">
            {[
              { label: 'DB Pool Size', value: stats?.db_pool_size ?? '—' },
              { label: 'DB Connections Active', value: stats?.db_checked_out ?? '—' },
              { label: 'Process Memory', value: stats?.process_memory_mb ? stats.process_memory_mb + ' MB' : '—' },
            ].map(({ label, value }) => (
              <div key={label} className="flex items-center justify-between py-2 border-b border-border/50 last:border-0">
                <span className="text-sm text-text-secondary">{label}</span>
                <span className="text-sm font-medium text-neon-blue">{String(value)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

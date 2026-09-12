'use client'

import { useQuery } from '@tanstack/react-query'
import { Users, Database, FileText, Activity, ShieldCheck } from 'lucide-react'
import { adminService } from '@/lib/api/services'
import { SkeletonCard } from '@/components/common/loading-page'
import { useAuth } from '@/hooks/use-auth'

export default function AdminDashboardPage() {
  const { principal } = useAuth()
  const statsQ = useQuery({ queryKey: ['admin-user-stats'], queryFn: adminService.userStats })
  const healthQ = useQuery({ queryKey: ['admin-health'], queryFn: adminService.health, refetchInterval: 30_000 })

  const stats = statsQ.data as { total_users?: number; active_users?: number; total_datasets?: number; total_reports?: number } | undefined
  const health = healthQ.data as { status?: string; checks?: Record<string, string> } | undefined

  const statCards = [
    { icon: Users, label: 'Total Users', value: stats?.total_users ?? '-' },
    { icon: Activity, label: 'Active Users', value: stats?.active_users ?? '-' },
    { icon: Database, label: 'Datasets', value: stats?.total_datasets ?? '-' },
    { icon: FileText, label: 'Reports', value: stats?.total_reports ?? '-' },
  ]

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Admin Dashboard</h1>
        <p className="text-text-secondary text-sm mt-1">Welcome, {principal?.first_name}</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {statsQ.isLoading
          ? Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
          : statCards.map(({ icon: Icon, label, value }) => (
              <div key={label} className="stat-card">
                <div className="flex items-center gap-2 mb-2">
                  <Icon className="w-4 h-4 text-neon-blue" />
                  <span className="stat-label">{label}</span>
                </div>
                <div className="stat-value">{value}</div>
              </div>
            ))}
      </div>

      {/* System health */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <ShieldCheck className="w-4 h-4 text-neon-blue" />
          <h2 className="text-sm font-semibold text-text-primary">System Health</h2>
          <span className={`ml-auto text-xs font-medium px-2 py-0.5 rounded-full border ${health?.status === 'ok' ? 'text-neon-green border-neon-green/30 bg-neon-green/10' : 'text-yellow-400 border-yellow-500/30 bg-yellow-500/10'}`}>
            {health?.status ?? 'checking…'}
          </span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {health?.checks
            ? Object.entries(health.checks).map(([service, status]) => (
                <div key={service} className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${status === 'ok' ? 'bg-neon-green' : 'bg-red-400'}`} />
                  <span className="text-xs text-text-secondary capitalize">{service}</span>
                  <span className={`text-xs ml-auto ${status === 'ok' ? 'text-neon-green' : 'text-red-400'}`}>{status}</span>
                </div>
              ))
            : <p className="text-xs text-text-muted">Loading…</p>}
        </div>
      </div>
    </div>
  )
}

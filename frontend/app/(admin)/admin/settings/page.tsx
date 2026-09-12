'use client'

import { useQuery } from '@tanstack/react-query'
import { Settings } from 'lucide-react'
import { adminService } from '@/lib/api/services'
import { SkeletonCard } from '@/components/common/loading-page'

export default function AdminSettingsPage() {
  const settingsQ = useQuery({ queryKey: ['admin-settings'], queryFn: adminService.settings })
  const config = settingsQ.data as Record<string, unknown> | undefined

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary flex items-center gap-2">
          <Settings className="w-6 h-6 text-neon-blue" />
          Platform Settings
        </h1>
        <p className="text-text-secondary text-sm mt-1">Read-only view of current configuration</p>
      </div>

      {settingsQ.isLoading ? (
        <SkeletonCard />
      ) : (
        <div className="card">
          <div className="space-y-0">
            {config
              ? Object.entries(config).map(([key, value], i, arr) => (
                  <div key={key} className={`flex items-center justify-between py-3 ${i < arr.length - 1 ? 'border-b border-border/50' : ''}`}>
                    <span className="text-sm text-text-secondary font-mono">{key}</span>
                    <span className="text-sm text-text-primary font-medium">{String(value)}</span>
                  </div>
                ))
              : <p className="text-text-muted text-sm">No settings available</p>}
          </div>
        </div>
      )}
    </div>
  )
}

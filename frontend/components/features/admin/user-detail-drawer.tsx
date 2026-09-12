'use client'

import { useQuery } from '@tanstack/react-query'
import { Bot, Database, Loader2, X } from 'lucide-react'
import { adminService } from '@/lib/api/services'
import { formatBytes, formatNumber } from '@/lib/utils'

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-background/40 rounded-lg px-3 py-2">
      <p className="text-[11px] uppercase tracking-wide text-text-muted">{label}</p>
      <p className="text-sm font-semibold text-text-primary mt-0.5">{value}</p>
    </div>
  )
}

export function UserDetailDrawer({ userId, onClose }: { userId: string; onClose: () => void }) {
  const q = useQuery({
    queryKey: ['admin-user-detail', userId],
    queryFn: () => adminService.userDetail(userId),
  })

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60" onClick={onClose}>
      <div
        className="w-full max-w-md h-full bg-background-card border-l border-border overflow-y-auto p-5 space-y-5"
        onClick={(e) => e.stopPropagation()}
      >
        {q.isLoading ? (
          <div className="flex justify-center py-16"><Loader2 className="w-5 h-5 animate-spin text-neon-blue" /></div>
        ) : q.isError || !q.data ? (
          <p className="text-red-400 text-sm py-6">Could not load user details.</p>
        ) : (
          <>
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-semibold text-text-primary">
                  {q.data.user.first_name} {q.data.user.last_name}
                </h3>
                <p className="text-xs text-text-muted">{q.data.user.email}</p>
              </div>
              <button onClick={onClose} className="text-text-muted hover:text-text-primary" aria-label="Close">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex flex-wrap gap-2 text-xs">
              <span className={`px-2 py-0.5 rounded-full border ${q.data.user.is_active ? 'text-neon-green border-neon-green/30 bg-neon-green/10' : 'text-red-400 border-red-500/30 bg-red-500/10'}`}>
                {q.data.user.is_active ? 'active' : 'suspended'}
              </span>
              {q.data.user.company && (
                <span className="px-2 py-0.5 rounded-full border border-border text-text-secondary">{q.data.user.company}</span>
              )}
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs">
              <Stat label="Joined" value={new Date(q.data.user.created_at).toLocaleDateString()} />
              <Stat
                label="Last login"
                value={q.data.user.last_login_at ? new Date(q.data.user.last_login_at).toLocaleString() : 'never'}
              />
            </div>

            <div>
              <p className="text-[11px] uppercase tracking-wide text-text-muted mb-2 flex items-center gap-1.5">
                <Database className="w-3.5 h-3.5" /> Resources
              </p>
              <div className="grid grid-cols-3 gap-2">
                <Stat label="Datasets" value={q.data.resources.datasets} />
                <Stat label="Dashboards" value={q.data.resources.dashboards} />
                <Stat label="Insights" value={q.data.resources.insights} />
                <Stat label="Reports" value={q.data.resources.reports} />
                <Stat label="Chats" value={q.data.resources.conversations} />
                <Stat label="Messages" value={q.data.resources.messages} />
              </div>
              <div className="grid grid-cols-2 gap-2 mt-2">
                <Stat label="Storage" value={formatBytes(q.data.resources.storage_bytes)} />
                <Stat label="Data rows" value={formatNumber(q.data.resources.dataset_rows)} />
              </div>
            </div>

            <div>
              <p className="text-[11px] uppercase tracking-wide text-text-muted mb-2 flex items-center gap-1.5">
                <Bot className="w-3.5 h-3.5" /> AI usage
              </p>
              <div className="grid grid-cols-2 gap-2">
                <Stat label="AI calls" value={formatNumber(q.data.ai_usage.calls)} />
                <Stat label="Total tokens" value={formatNumber(q.data.ai_usage.total_tokens)} />
                <Stat label="Input tokens" value={formatNumber(q.data.ai_usage.input_tokens)} />
                <Stat label="Output tokens" value={formatNumber(q.data.ai_usage.output_tokens)} />
              </div>
              {q.data.ai_usage.last_call_at && (
                <p className="text-[11px] text-text-muted mt-1.5">
                  Last AI call: {new Date(q.data.ai_usage.last_call_at).toLocaleString()}
                </p>
              )}
            </div>

            {q.data.recent_datasets.length > 0 && (
              <div>
                <p className="text-[11px] uppercase tracking-wide text-text-muted mb-2">Recent datasets</p>
                <div className="space-y-1.5">
                  {q.data.recent_datasets.map((d) => (
                    <div key={d.id} className="flex items-center justify-between text-xs bg-background/40 rounded px-3 py-2">
                      <span className="text-text-primary truncate">{d.name}</span>
                      <span className="text-text-muted shrink-0 ml-2">
                        {d.row_count != null ? `${formatNumber(d.row_count)} rows · ` : ''}{d.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

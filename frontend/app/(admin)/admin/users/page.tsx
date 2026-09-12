'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Users, UserX, Trash2, ChevronLeft, ChevronRight, Eye } from 'lucide-react'
import { adminService } from '@/lib/api/services'
import { useUIStore } from '@/store/use-ui-store'
import { SkeletonCard } from '@/components/common/loading-page'
import { UserDetailDrawer } from '@/components/features/admin/user-detail-drawer'

export default function AdminUsersPage() {
  const [page, setPage] = useState(1)
  const [detailUserId, setDetailUserId] = useState<string | null>(null)
  const qc = useQueryClient()
  const { addToast } = useUIStore()

  const usersQ = useQuery({
    queryKey: ['admin-users', page],
    queryFn: () => adminService.users(page),
  })

  const suspendMutation = useMutation({
    mutationFn: (id: string) => adminService.suspendUser(id),
    onSuccess: () => {
      addToast({ type: 'success', title: 'User status updated' })
      qc.invalidateQueries({ queryKey: ['admin-users'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => adminService.deleteUser(id),
    onSuccess: () => {
      addToast({ type: 'success', title: 'User deleted' })
      qc.invalidateQueries({ queryKey: ['admin-users'] })
    },
  })

  const users = (usersQ.data?.users ?? []) as Array<{
    id: string; email: string; first_name: string; last_name: string
    company?: string; is_active: boolean; created_at: string
  }>
  const total = usersQ.data?.total ?? 0
  const totalPages = Math.ceil(total / 20)

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary flex items-center gap-2">
            <Users className="w-6 h-6 text-neon-blue" />
            Users
          </h1>
          <p className="text-text-secondary text-sm mt-1">{total} registered users</p>
        </div>
      </div>

      {usersQ.isLoading ? (
        <div className="space-y-3">{Array.from({ length: 5 }).map((_, i) => <SkeletonCard key={i} />)}</div>
      ) : (
        <>
          <div className="card overflow-hidden p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-background-secondary">
                <tr>
                  {['User', 'Company', 'Status', 'Joined', 'Actions'].map((h) => (
                    <th key={h} className="text-left py-3 px-4 text-xs font-medium text-text-muted uppercase tracking-wider">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {users.map((u, i) => (
                  <tr
                    key={u.id}
                    onClick={() => setDetailUserId(u.id)}
                    className={`border-b border-border/50 hover:bg-background-hover cursor-pointer ${i % 2 === 0 ? '' : 'bg-background-secondary/30'}`}
                    title="View details"
                  >
                    <td className="py-3 px-4">
                      <p className="font-medium text-text-primary">{u.first_name} {u.last_name}</p>
                      <p className="text-xs text-text-muted">{u.email}</p>
                    </td>
                    <td className="py-3 px-4 text-text-secondary text-xs">{u.company || '—'}</td>
                    <td className="py-3 px-4">
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${u.is_active ? 'text-neon-green border-neon-green/30 bg-neon-green/10' : 'text-red-400 border-red-500/30 bg-red-500/10'}`}>
                        {u.is_active ? 'active' : 'suspended'}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-text-muted text-xs">{new Date(u.created_at).toLocaleDateString()}</td>
                    <td className="py-3 px-4" onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center gap-3">
                        <button
                          onClick={() => setDetailUserId(u.id)}
                          className="text-text-muted hover:text-neon-blue transition-colors"
                          title="View details"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => suspendMutation.mutate(u.id)}
                          className="text-text-muted hover:text-yellow-400 transition-colors"
                          title={u.is_active ? 'Suspend' : 'Activate'}
                        >
                          <UserX className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => { if (confirm(`Delete ${u.email}? This cannot be undone.`)) deleteMutation.mutate(u.id) }}
                          className="text-text-muted hover:text-red-400 transition-colors"
                          title="Delete user"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between text-sm">
              <p className="text-text-muted text-xs">Page {page} of {totalPages}</p>
              <div className="flex gap-2">
                <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} className="btn-ghost py-1.5 px-3 disabled:opacity-40">
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className="btn-ghost py-1.5 px-3 disabled:opacity-40">
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {detailUserId && <UserDetailDrawer userId={detailUserId} onClose={() => setDetailUserId(null)} />}
    </div>
  )
}

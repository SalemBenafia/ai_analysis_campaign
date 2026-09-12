'use client'

import { useForm } from 'react-hook-form'
import { useMutation } from '@tanstack/react-query'
import { User, Key } from 'lucide-react'
import { useAuth } from '@/hooks/use-auth'
import { useUIStore } from '@/store/use-ui-store'
import { authService } from '@/lib/api/services'
import { LoadingSpinner } from '@/components/common/loading-page'

export default function ProfilePage() {
  const { principal } = useAuth()
  const { addToast } = useUIStore()

  const pwForm = useForm<{ current_password: string; new_password: string }>()

  const changePwMutation = useMutation({
    mutationFn: (d: { current_password: string; new_password: string }) =>
      authService.changePassword(d.current_password, d.new_password),
    onSuccess: () => {
      addToast({ type: 'success', title: 'Password changed' })
      pwForm.reset()
    },
    onError: () => addToast({ type: 'error', title: 'Failed to change password' }),
  })

  if (!principal) return null

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Profile</h1>
        <p className="text-text-secondary text-sm mt-1">Manage your account settings</p>
      </div>

      {/* Info card */}
      <div className="card space-y-4">
        <div className="flex items-center gap-3 mb-2">
          <User className="w-4 h-4 text-neon-blue" />
          <h2 className="text-sm font-semibold text-text-primary">Account Details</h2>
        </div>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-text-muted text-xs mb-1">Name</p>
            <p className="text-text-primary">{principal.first_name} {principal.last_name}</p>
          </div>
          <div>
            <p className="text-text-muted text-xs mb-1">Email</p>
            <p className="text-text-primary">{principal.email}</p>
          </div>
          {principal.company && (
            <div>
              <p className="text-text-muted text-xs mb-1">Company</p>
              <p className="text-text-primary">{principal.company}</p>
            </div>
          )}
          <div>
            <p className="text-text-muted text-xs mb-1">Role</p>
            <p className="text-text-primary capitalize">{principal.principal_type}</p>
          </div>
        </div>
      </div>

      {/* Change password */}
      <div className="card">
        <div className="flex items-center gap-3 mb-4">
          <Key className="w-4 h-4 text-neon-blue" />
          <h2 className="text-sm font-semibold text-text-primary">Change Password</h2>
        </div>
        <form onSubmit={pwForm.handleSubmit((d) => changePwMutation.mutate(d))} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Current password</label>
            <input
              {...pwForm.register('current_password', { required: true })}
              type="password"
              className="input-cyber"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">New password</label>
            <input
              {...pwForm.register('new_password', { required: true, minLength: 8 })}
              type="password"
              className="input-cyber"
            />
          </div>
          <button
            type="submit"
            disabled={changePwMutation.isPending}
            className="btn-primary flex items-center gap-2"
          >
            {changePwMutation.isPending && <LoadingSpinner size={14} />}
            Update password
          </button>
        </form>
      </div>
    </div>
  )
}

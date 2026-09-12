'use client'

import { useTransition, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Eye, EyeOff, Sparkles } from 'lucide-react'
import { registerAction } from '@/app/actions/auth.actions'
import { useAuthStore } from '@/store/use-auth-store'
import { useUIStore } from '@/store/use-ui-store'
import { registerSchema, type RegisterInput } from '@/lib/auth/schemas'
import { LoadingSpinner } from '@/components/common/loading-page'

export default function RegisterPage() {
  const [showPw, setShowPw] = useState(false)
  const [pending, startTransition] = useTransition()
  const router = useRouter()
  const setPrincipal = useAuthStore((s) => s.setPrincipal)
  const { addToast } = useUIStore()

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<RegisterInput>({ resolver: zodResolver(registerSchema) })

  const onSubmit = (data: RegisterInput) => {
    startTransition(async () => {
      const result = await registerAction(data)
      if (result.ok) {
        setPrincipal(result.data)
        addToast({ type: 'success', title: 'Account created!', message: `Welcome, ${result.data.first_name}` })
        router.push('/dashboard')
      } else {
        const msg = String(result.error.message)
        setError('root', { message: msg })
        addToast({ type: 'error', title: 'Registration failed', message: msg })
      }
    })
  }

  return (
    <div className="min-h-screen bg-background bg-grid flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 mb-4">
            <div className="w-9 h-9 rounded-xl bg-neon-blue/10 border border-neon-blue/30 flex items-center justify-center">
              <Sparkles className="w-5 h-5 text-neon-blue" />
            </div>
            <span className="text-xl font-bold text-gradient">InsightAI</span>
          </div>
          <h1 className="text-2xl font-bold text-text-primary">Create account</h1>
          <p className="text-text-secondary text-sm mt-1">Start analyzing your campaigns</p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="card space-y-4">
          {errors.root && (
            <p className="text-red-400 text-sm text-center">{errors.root.message}</p>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1.5">First name</label>
              <input {...register('first_name')} className="input-cyber" placeholder="Jane" />
              {errors.first_name && <p className="text-red-400 text-xs mt-1">{errors.first_name.message}</p>}
            </div>
            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1.5">Last name</label>
              <input {...register('last_name')} className="input-cyber" placeholder="Smith" />
              {errors.last_name && <p className="text-red-400 text-xs mt-1">{errors.last_name.message}</p>}
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Email</label>
            <input {...register('email')} type="email" className="input-cyber" placeholder="you@company.com" />
            {errors.email && <p className="text-red-400 text-xs mt-1">{errors.email.message}</p>}
          </div>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Company (optional)</label>
            <input {...register('company')} className="input-cyber" placeholder="Acme Agency" />
          </div>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Password</label>
            <div className="relative">
              <input
                {...register('password')}
                type={showPw ? 'text' : 'password'}
                className="input-cyber pr-10"
                placeholder="Min 8 chars, 1 uppercase, 1 number"
              />
              <button type="button" onClick={() => setShowPw((v) => !v)} className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary">
                {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            {errors.password && <p className="text-red-400 text-xs mt-1">{errors.password.message}</p>}
          </div>

          <button type="submit" disabled={pending} className="btn-primary w-full flex items-center justify-center gap-2">
            {pending ? <LoadingSpinner size={16} /> : null}
            {pending ? 'Creating account…' : 'Create account'}
          </button>

          <p className="text-center text-xs text-text-muted">
            Already have an account?{' '}
            <Link href="/login" className="text-neon-blue hover:underline">Sign in</Link>
          </p>
        </form>
      </div>
    </div>
  )
}

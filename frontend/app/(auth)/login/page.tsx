'use client'

import { useTransition, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Eye, EyeOff, Sparkles } from 'lucide-react'
import { loginAction } from '@/app/actions/auth.actions'
import { useAuthStore } from '@/store/use-auth-store'
import { useUIStore } from '@/store/use-ui-store'
import { loginSchema, type LoginInput } from '@/lib/auth/schemas'
import { LoadingSpinner } from '@/components/common/loading-page'

export default function LoginPage() {
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
  } = useForm<LoginInput>({ resolver: zodResolver(loginSchema) })

  const onSubmit = (data: LoginInput) => {
    startTransition(async () => {
      const result = await loginAction(data)
      if (result.ok) {
        setPrincipal(result.data)
        addToast({ type: 'success', title: 'Welcome back!', message: result.data.first_name })
        router.push(result.data.principal_type === 'admin' ? '/admin/dashboard' : '/dashboard')
      } else {
        const msg = String(result.error.message)
        setError('root', { message: msg })
        addToast({ type: 'error', title: 'Login failed', message: msg })
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
          <h1 className="text-2xl font-bold text-text-primary">Welcome back</h1>
          <p className="text-text-secondary text-sm mt-1">Sign in to your account</p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="card space-y-5">
          {errors.root && (
            <p className="text-red-400 text-sm text-center">{errors.root.message}</p>
          )}

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Email</label>
            <input
              {...register('email')}
              type="email"
              autoComplete="email"
              className="input-cyber"
              placeholder="you@company.com"
            />
            {errors.email && (
              <p className="text-red-400 text-xs mt-1">{errors.email.message}</p>
            )}
          </div>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Password</label>
            <div className="relative">
              <input
                {...register('password')}
                type={showPw ? 'text' : 'password'}
                autoComplete="current-password"
                className="input-cyber pr-10"
                placeholder="••••••••"
              />
              <button
                type="button"
                onClick={() => setShowPw((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary"
              >
                {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            {errors.password && (
              <p className="text-red-400 text-xs mt-1">{errors.password.message}</p>
            )}
          </div>

          <button
            type="submit"
            disabled={pending}
            className="btn-primary w-full flex items-center justify-center gap-2"
          >
            {pending ? <LoadingSpinner size={16} /> : null}
            {pending ? 'Signing in…' : 'Sign in'}
          </button>

          <p className="text-center text-xs text-text-muted">
            No account?{' '}
            <Link href="/register" className="text-neon-blue hover:underline">
              Create one
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}

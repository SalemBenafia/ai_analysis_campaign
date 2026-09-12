'use client'

import { useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/store/use-auth-store'
import { logoutAction } from '@/app/actions/auth.actions'
import { authService } from '@/lib/api/services'


export function useAuth() {
  const { principal, isLoading, setPrincipal, clear } = useAuthStore()
  const router = useRouter()
  const qc = useQueryClient()

  // Hydrate auth store on page reload: try /me/ (user token) then /me/admin (admin token).
  useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      try {
        const p = await authService.me()
        setPrincipal(p)
        return p
      } catch {
        try {
          const p = await authService.meAdmin()
          setPrincipal(p)
          return p
        } catch {
          clear()
          return null
        }
      }
    },
    enabled: !principal && isLoading,
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

  const logout = useCallback(async () => {
    await logoutAction()
    clear()
    qc.clear()
    router.push('/login')
  }, [clear, qc, router])

  return {
    principal,
    isLoading,
    isUser: principal?.principal_type === 'user',
    isAdmin: principal?.principal_type === 'admin',
    logout,
  }
}

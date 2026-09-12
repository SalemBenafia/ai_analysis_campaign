'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { AppSidebar } from '@/components/layouts/app-sidebar'
import { LoadingPage } from '@/components/common/loading-page'
import { useAuth } from '@/hooks/use-auth'

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { principal, isLoading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!isLoading && !principal) router.push('/login')
    if (!isLoading && principal?.principal_type === 'user') router.push('/dashboard')
  }, [principal, isLoading, router])

  if (isLoading) return <LoadingPage />
  if (!principal || principal.principal_type !== 'admin') return null

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <AppSidebar isAdmin />
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  )
}

'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { AppSidebar } from '@/components/layouts/app-sidebar'
import { LoadingPage } from '@/components/common/loading-page'
import { useAuth } from '@/hooks/use-auth'

export default function UserLayout({ children }: { children: React.ReactNode }) {
  const { principal, isLoading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!isLoading && !principal) router.push('/login')
    if (!isLoading && principal?.principal_type === 'admin') router.push('/admin/dashboard')
  }, [principal, isLoading, router])

  if (isLoading) return <LoadingPage />
  if (!principal || principal.principal_type !== 'user') return null

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <AppSidebar />
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  )
}

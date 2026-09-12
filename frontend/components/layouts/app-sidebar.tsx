'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard, Database, Wand2, MessageSquare, FileText,
  Settings, LogOut, ChevronLeft, ChevronRight, Sparkles, User,
  Lightbulb, LayoutGrid, BarChart3,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/hooks/use-auth'
import { useUIStore } from '@/store/use-ui-store'

const USER_NAV = [
  { href: '/dashboard', label: 'Home', icon: LayoutDashboard },
  { href: '/datasets', label: 'Datasets', icon: Database },
  { href: '/builder', label: 'Visual Builder', icon: Wand2 },
  { href: '/insights', label: 'Insights', icon: Lightbulb },
  { href: '/dashboards', label: 'Dashboards', icon: LayoutGrid },
  { href: '/copilot', label: 'AI Copilot', icon: MessageSquare },
  { href: '/reports', label: 'Reports', icon: FileText },
]

const ADMIN_NAV = [
  { href: '/admin/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/admin/users', label: 'Users', icon: User },
  { href: '/admin/analytics', label: 'Analytics', icon: BarChart3 },
  { href: '/admin/monitoring', label: 'Monitoring', icon: Sparkles },
  { href: '/admin/settings', label: 'Settings', icon: Settings },
]

export function AppSidebar({ isAdmin = false }: { isAdmin?: boolean }) {
  const pathname = usePathname()
  const { principal, logout } = useAuth()
  const { sidebarCollapsed, toggleSidebar } = useUIStore()
  const nav = isAdmin ? ADMIN_NAV : USER_NAV

  return (
    <aside
      className={cn(
        'h-screen flex flex-col bg-background-secondary border-r border-border transition-all duration-300 flex-shrink-0',
        sidebarCollapsed ? 'w-16' : 'w-60',
      )}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 h-16 border-b border-border">
        <div className="w-8 h-8 rounded-lg bg-neon-blue/10 border border-neon-blue/30 flex items-center justify-center flex-shrink-0">
          <Sparkles className="w-4 h-4 text-neon-blue" />
        </div>
        {!sidebarCollapsed && (
          <span className="font-bold text-sm text-gradient tracking-wide">InsightAI</span>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2 py-4 space-y-0.5 overflow-y-auto">
        {nav.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(href + '/')
          return (
            <Link
              key={href}
              href={href}
              className={cn('sidebar-item', active && 'active', sidebarCollapsed && 'justify-center px-2')}
              title={sidebarCollapsed ? label : undefined}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {!sidebarCollapsed && <span>{label}</span>}
            </Link>
          )
        })}
      </nav>

      {/* User + collapse */}
      <div className="border-t border-border p-2 space-y-1">
        {!sidebarCollapsed && principal && (
          <div className="px-3 py-2">
            <p className="text-xs font-medium text-text-primary truncate">
              {principal.first_name} {principal.last_name}
            </p>
            <p className="text-xs text-text-muted truncate">{principal.email}</p>
          </div>
        )}
        <button
          onClick={logout}
          className={cn('sidebar-item w-full', sidebarCollapsed && 'justify-center px-2')}
          title={sidebarCollapsed ? 'Logout' : undefined}
        >
          <LogOut className="w-4 h-4 flex-shrink-0" />
          {!sidebarCollapsed && <span>Logout</span>}
        </button>
        <button
          onClick={toggleSidebar}
          className={cn('sidebar-item w-full', sidebarCollapsed && 'justify-center px-2')}
        >
          {sidebarCollapsed ? (
            <ChevronRight className="w-4 h-4" />
          ) : (
            <>
              <ChevronLeft className="w-4 h-4" />
              <span>Collapse</span>
            </>
          )}
        </button>
      </div>
    </aside>
  )
}

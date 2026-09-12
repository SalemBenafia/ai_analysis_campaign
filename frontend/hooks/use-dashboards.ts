'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { dashboardService } from '@/lib/api/services'
import { useUIStore } from '@/store/use-ui-store'

export function useDashboards() {
  const { addToast } = useUIStore()
  const qc = useQueryClient()

  const query = useQuery({ queryKey: ['dashboards'], queryFn: () => dashboardService.list() })

  const createMutation = useMutation({
    mutationFn: (data: { name: string; description?: string }) => dashboardService.create(data),
    onSuccess: () => {
      addToast({ type: 'success', title: 'Dashboard created' })
      qc.invalidateQueries({ queryKey: ['dashboards'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => dashboardService.delete(id),
    onSuccess: () => {
      addToast({ type: 'success', title: 'Dashboard deleted' })
      qc.invalidateQueries({ queryKey: ['dashboards'] })
    },
  })

  return {
    dashboards: query.data?.dashboards ?? [],
    isLoading: query.isLoading,
    createDashboard: createMutation.mutateAsync,
    deleteDashboard: deleteMutation.mutate,
  }
}

export function useDashboard(id: string) {
  return useQuery({
    queryKey: ['dashboard', id],
    queryFn: () => dashboardService.get(id),
    enabled: !!id,
  })
}

'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { insightService } from '@/lib/api/services'
import { useUIStore } from '@/store/use-ui-store'

export function useInsights() {
  const { addToast } = useUIStore()
  const qc = useQueryClient()

  const query = useQuery({ queryKey: ['insights'], queryFn: () => insightService.list() })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => insightService.delete(id),
    onSuccess: () => {
      addToast({ type: 'success', title: 'Insight deleted' })
      qc.invalidateQueries({ queryKey: ['insights'] })
    },
  })

  const pinMutation = useMutation({
    mutationFn: ({ id, pinned }: { id: string; pinned: boolean }) =>
      insightService.update(id, { is_pinned: pinned }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['insights'] }),
  })

  return {
    insights: query.data?.insights ?? [],
    isLoading: query.isLoading,
    deleteInsight: deleteMutation.mutate,
    setPinned: pinMutation.mutate,
  }
}

export function useInsightExecution(id: string, explain = false) {
  return useQuery({
    queryKey: ['insight-exec', id, explain],
    queryFn: () => insightService.execute(id, explain),
    enabled: !!id,
    staleTime: 30_000,
  })
}

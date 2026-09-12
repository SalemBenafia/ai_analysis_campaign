'use client'

import { useQuery } from '@tanstack/react-query'
import { semanticService } from '@/lib/api/services'

export function useSemanticMembers(datasetId: string) {
  return useQuery({
    queryKey: ['semantic-members', datasetId],
    queryFn: () => semanticService.members(datasetId),
    enabled: !!datasetId,
  })
}

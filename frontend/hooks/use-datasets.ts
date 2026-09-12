'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useUIStore } from '@/store/use-ui-store'
import { useDatasetStore } from '@/store/use-dataset-store'
import { datasetService } from '@/lib/api/services'
import type { Dataset } from '@/types'

export function useDatasets() {
  const { addToast } = useUIStore()
  const { setDatasets } = useDatasetStore()
  const qc = useQueryClient()

  const query = useQuery({
    queryKey: ['datasets'],
    queryFn: async () => {
      const result = await datasetService.list()
      // Guard: API may return the wrapper object or the array directly.
      const datasets = Array.isArray(result)
        ? result
        : Array.isArray((result as { datasets?: unknown }).datasets)
          ? (result as { datasets: Dataset[] }).datasets
          : []
      setDatasets(datasets)
      return datasets
    },
  })

  const uploadMutation = useMutation({
    mutationFn: (file: File) => datasetService.upload(file),
    onSuccess: () => {
      addToast({ type: 'success', title: 'Upload started', message: 'Processing your dataset…' })
      qc.invalidateQueries({ queryKey: ['datasets'] })
    },
    onError: () => addToast({ type: 'error', title: 'Upload failed' }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => datasetService.delete(id),
    onSuccess: () => {
      addToast({ type: 'success', title: 'Dataset deleted' })
      qc.invalidateQueries({ queryKey: ['datasets'] })
    },
  })

  return {
    datasets: Array.isArray(query.data) ? query.data : [],
    isLoading: query.isLoading,
    upload: uploadMutation.mutate,
    uploading: uploadMutation.isPending,
    deleteDataset: deleteMutation.mutate,
  }
}

export function useDataset(id: string) {
  const { setActiveDataset } = useDatasetStore()
  return useQuery({
    queryKey: ['dataset', id],
    queryFn: async () => {
      const data = await datasetService.get(id)
      setActiveDataset(data.dataset, data.columns)
      return data
    },
    enabled: !!id,
  })
}

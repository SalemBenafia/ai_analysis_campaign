import { create } from 'zustand'
import type { Dataset, DatasetColumn } from '@/types'

interface DatasetState {
  datasets: Dataset[]
  activeDataset: Dataset | null
  activeColumns: DatasetColumn[]
  setDatasets: (datasets: Dataset[]) => void
  setActiveDataset: (ds: Dataset | null, cols?: DatasetColumn[]) => void
}

export const useDatasetStore = create<DatasetState>((set) => ({
  datasets: [],
  activeDataset: null,
  activeColumns: [],
  setDatasets: (datasets) => set({ datasets }),
  setActiveDataset: (activeDataset, activeColumns = []) => set({ activeDataset, activeColumns }),
}))

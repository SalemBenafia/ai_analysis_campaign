import { create } from 'zustand'
import type { Principal } from '@/types'

interface AuthState {
  principal: Principal | null
  isLoading: boolean
  setPrincipal: (p: Principal | null) => void
  setLoading: (v: boolean) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  principal: null,
  isLoading: true,
  setPrincipal: (principal) => set({ principal, isLoading: false }),
  setLoading: (isLoading) => set({ isLoading }),
  clear: () => set({ principal: null, isLoading: false }),
}))

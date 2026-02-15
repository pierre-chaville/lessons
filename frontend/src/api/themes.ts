import { apiClient } from './client'
import type { Theme, ThemeCreate, ThemeUpdate } from './types'

export const themesApi = {
  list: () => apiClient.get<Theme[]>('/themes').then((r) => r.data),

  get: (id: number) => apiClient.get<Theme>(`/themes/${id}`).then((r) => r.data),

  create: (data: ThemeCreate) =>
    apiClient.post<Theme>('/themes', data).then((r) => r.data),

  update: (id: number, data: ThemeUpdate) =>
    apiClient.patch<Theme>(`/themes/${id}`, data).then((r) => r.data),

  delete: (id: number) => apiClient.delete(`/themes/${id}`),
}

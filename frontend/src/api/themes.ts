import { apiClient } from './client'
import type { Theme, ThemeCreate, ThemeUpdate } from './types'

export const themesApi = {
  list: () => apiClient.get<Theme[]>('/themes').then((r) => r.data),

  get: (hashid: string) => apiClient.get<Theme>(`/themes/${hashid}`).then((r) => r.data),

  create: (data: ThemeCreate) =>
    apiClient.post<Theme>('/themes', data).then((r) => r.data),

  update: (hashid: string, data: ThemeUpdate) =>
    apiClient.patch<Theme>(`/themes/${hashid}`, data).then((r) => r.data),

  delete: (hashid: string) => apiClient.delete(`/themes/${hashid}`),
}

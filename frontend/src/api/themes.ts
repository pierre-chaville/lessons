import { apiClient } from './client'
import type {
  Theme,
  ThemeCreate,
  ThemeExport,
  ThemeImportResult,
  ThemeTransferNode,
  ThemeTreeNode,
  ThemeUpdate,
} from './types'

export const themesApi = {
  list: () => apiClient.get<Theme[]>('/themes').then((r) => r.data),

  tree: () => apiClient.get<ThemeTreeNode[]>('/themes/tree').then((r) => r.data),

  get: (hashid: string) => apiClient.get<Theme>(`/themes/${hashid}`).then((r) => r.data),

  create: (data: ThemeCreate) =>
    apiClient.post<Theme>('/themes', data).then((r) => r.data),

  update: (hashid: string, data: ThemeUpdate) =>
    apiClient.patch<Theme>(`/themes/${hashid}`, data).then((r) => r.data),

  delete: (hashid: string) => apiClient.delete(`/themes/${hashid}`),

  reorder: (hashid: string, direction: 'up' | 'down') =>
    apiClient.patch<Theme[]>(`/themes/${hashid}/reorder`, { direction }).then((r) => r.data),

  exportJson: () => apiClient.get<ThemeExport>('/themes/export').then((r) => r.data),

  /** Merge a theme tree: matched by name under the same parent, missing ones created. */
  importJson: (themes: ThemeTransferNode[]) =>
    apiClient.post<ThemeImportResult>('/themes/import', { themes }).then((r) => r.data),
}

import { apiClient } from './client'
import type {
  GlossaryEntry,
  GlossaryEntryCreate,
  GlossaryEntryUpdate,
} from './types'

export const glossaryApi = {
  list: () => apiClient.get<GlossaryEntry[]>('/glossary').then((r) => r.data),

  get: (hashid: string) => apiClient.get<GlossaryEntry>(`/glossary/${hashid}`).then((r) => r.data),

  create: (data: GlossaryEntryCreate) =>
    apiClient.post<GlossaryEntry>('/glossary', data).then((r) => r.data),

  update: (hashid: string, data: GlossaryEntryUpdate) =>
    apiClient.patch<GlossaryEntry>(`/glossary/${hashid}`, data).then((r) => r.data),

  delete: (hashid: string) => apiClient.delete(`/glossary/${hashid}`),
}

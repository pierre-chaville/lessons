import { apiClient } from './client'
import type {
  GlossaryCompletionLaunch,
  GlossaryCompletionStatus,
  GlossaryEntry,
  GlossaryEntryCreate,
  GlossaryEntryList,
  GlossaryEntryUpdate,
  GlossaryImportResult,
  GlossaryListParams,
} from './types'

export const glossaryApi = {
  list: (params?: GlossaryListParams) =>
    apiClient.get<GlossaryEntryList>('/glossary', { params }).then((r) => r.data),

  get: (hashid: string) => apiClient.get<GlossaryEntry>(`/glossary/${hashid}`).then((r) => r.data),

  create: (data: GlossaryEntryCreate) =>
    apiClient.post<GlossaryEntry>('/glossary', data).then((r) => r.data),

  update: (hashid: string, data: GlossaryEntryUpdate) =>
    apiClient.patch<GlossaryEntry>(`/glossary/${hashid}`, data).then((r) => r.data),

  delete: (hashid: string) => apiClient.delete(`/glossary/${hashid}`),

  exportYaml: () =>
    apiClient
      .get<Blob>('/glossary/export/yaml', { responseType: 'blob' })
      .then((r) => r.data),

  /** Backup of the legacy transliteration glossary (read-only). */
  exportLegacyYaml: () =>
    apiClient
      .get<Blob>('/glossary/legacy/export/yaml', { responseType: 'blob' })
      .then((r) => r.data),

  /** Queue an LLM task completing entries without transliteration (publisher/admin). */
  complete: () =>
    apiClient.post<GlossaryCompletionLaunch>('/glossary/complete').then((r) => r.data),

  /** Pending entry count and latest completion task (publisher/admin). */
  completionStatus: () =>
    apiClient.get<GlossaryCompletionStatus>('/glossary/complete/status').then((r) => r.data),

  importYaml: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return apiClient
      .post<GlossaryImportResult>('/glossary/import/yaml', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },
}

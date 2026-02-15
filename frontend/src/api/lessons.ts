import { apiClient } from './client'
import type {
  LessonListItem,
  LessonDetail,
  LessonCreate,
  LessonUpdate,
  AudioUrlResponse,
} from './types'

export const lessonsApi = {
  list: (params?: { course_id?: number }) =>
    apiClient.get<LessonListItem[]>('/lessons', { params }).then((r) => r.data),

  get: (id: number) =>
    apiClient.get<LessonDetail>(`/lessons/${id}`).then((r) => r.data),

  create: (data: LessonCreate) =>
    apiClient.post<LessonDetail>('/lessons', data).then((r) => r.data),

  update: (id: number, data: LessonUpdate) =>
    apiClient.patch<LessonDetail>(`/lessons/${id}`, data).then((r) => r.data),

  delete: (id: number) => apiClient.delete(`/lessons/${id}`),

  getAudioUrl: (id: number) =>
    apiClient.get<AudioUrlResponse>(`/lessons/${id}/audio-url`).then((r) => r.data),

  // ── PDF downloads — return raw Blob data ────────────────────────────────────

  getPdfSummary: (id: number) =>
    apiClient
      .get<Blob>(`/lessons/${id}/pdf/summary`, { responseType: 'blob' })
      .then((r) => r.data),

  getPdfTranscript: (id: number, transcript_type: 'initial' | 'corrected') =>
    apiClient
      .get<Blob>(`/lessons/${id}/pdf/transcript`, {
        params: { transcript_type },
        responseType: 'blob',
      })
      .then((r) => r.data),

  getPdfEdited: (id: number) =>
    apiClient
      .get<Blob>(`/lessons/${id}/pdf/edited`, { responseType: 'blob' })
      .then((r) => r.data),

  getPdfSources: (id: number) =>
    apiClient
      .get<Blob>(`/lessons/${id}/pdf/sources`, { responseType: 'blob' })
      .then((r) => r.data),

  getPdfDetailedSources: (id: number) =>
    apiClient
      .get<Blob>(`/lessons/${id}/pdf/sources/detailed`, { responseType: 'blob' })
      .then((r) => r.data),
}

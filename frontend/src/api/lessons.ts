import { apiClient } from './client'
import type {
  LessonListItem,
  LessonDetail,
  LessonCreate,
  LessonUpdate,
  LessonStatus,
  AudioUrlResponse,
} from './types'

export const lessonsApi = {
  list: (params?: { course_id?: number; course_ids?: string }) =>
    apiClient.get<LessonListItem[]>('/lessons', { params }).then((r) => r.data),

  get: (hashid: string) =>
    apiClient.get<LessonDetail>(`/lessons/${hashid}`).then((r) => r.data),

  create: (data: LessonCreate) =>
    apiClient.post<LessonDetail>('/lessons', data).then((r) => r.data),

  update: (hashid: string, data: LessonUpdate) =>
    apiClient.patch<LessonDetail>(`/lessons/${hashid}`, data).then((r) => r.data),

  delete: (hashid: string) => apiClient.delete(`/lessons/${hashid}`),

  updateStatus: (hashid: string, status: LessonStatus) =>
    apiClient.patch<LessonDetail>(`/lessons/${hashid}/status`, { status }).then((r) => r.data),

  getAudioUrl: (hashid: string) =>
    apiClient.get<AudioUrlResponse>(`/lessons/${hashid}/audio-url`).then((r) => r.data),

  // ── PDF downloads — return raw Blob data ────────────────────────────────────

  getPdfSummary: (hashid: string) =>
    apiClient
      .get<Blob>(`/lessons/${hashid}/pdf/summary`, { responseType: 'blob' })
      .then((r) => r.data),

  getPdfTranscript: (hashid: string, transcript_type: 'initial' | 'corrected') =>
    apiClient
      .get<Blob>(`/lessons/${hashid}/pdf/transcript`, {
        params: { transcript_type },
        responseType: 'blob',
      })
      .then((r) => r.data),

  getPdfEdited: (hashid: string) =>
    apiClient
      .get<Blob>(`/lessons/${hashid}/pdf/edited`, { responseType: 'blob' })
      .then((r) => r.data),

  getPdfSources: (hashid: string) =>
    apiClient
      .get<Blob>(`/lessons/${hashid}/pdf/sources`, { responseType: 'blob' })
      .then((r) => r.data),

  getPdfDetailedSources: (hashid: string) =>
    apiClient
      .get<Blob>(`/lessons/${hashid}/pdf/sources/detailed`, { responseType: 'blob' })
      .then((r) => r.data),
}

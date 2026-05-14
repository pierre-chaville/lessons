import { apiClient } from './client'
import type {
  LessonListItem,
  LessonDetail,
  LessonCreate,
  LessonUpdate,
  LessonStatus,
  AudioUrlResponse,
  ContentType,
  LessonVersion,
  VersionDiffResponse,
  AuditLogRow,
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

  realignEdited: (hashid: string) =>
    apiClient.post<LessonDetail>(`/lessons/${hashid}/edited/realign`).then((r) => r.data),

  delete: (hashid: string) => apiClient.delete(`/lessons/${hashid}`),

  updateStatus: (hashid: string, status: LessonStatus) =>
    apiClient.patch<LessonDetail>(`/lessons/${hashid}/status`, { status }).then((r) => r.data),

  listVersions: (
    hashid: string,
    params: { content_type: ContentType; limit?: number; before?: number },
  ) =>
    apiClient
      .get<LessonVersion[]>(`/lessons/${hashid}/versions`, { params })
      .then((r) => r.data),

  getVersion: (hashid: string, versionId: string) =>
    apiClient
      .get<LessonVersion>(`/lessons/${hashid}/versions/${versionId}`)
      .then((r) => r.data),

  getVersionDiff: (hashid: string, versionAId: string, versionBId: string) =>
    apiClient
      .get<VersionDiffResponse>(`/lessons/${hashid}/versions/${versionAId}/diff/${versionBId}`)
      .then((r) => r.data),

  restoreVersion: (hashid: string, versionId: string, reason: string) =>
    apiClient
      .post<LessonVersion>(`/lessons/${hashid}/versions/${versionId}/restore`, { reason })
      .then((r) => r.data),

  checkpointVersion: (hashid: string, contentType: ContentType, reason: string) =>
    apiClient
      .post<LessonVersion>(`/lessons/${hashid}/versions/checkpoint`, {
        content_type: contentType,
        reason,
      })
      .then((r) => r.data),

  getLessonAuditLog: (hashid: string, params?: { limit?: number; before_id?: number }) =>
    apiClient
      .get<AuditLogRow[]>(`/lessons/${hashid}/audit-log`, { params })
      .then((r) => r.data),

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

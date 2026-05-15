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

  realignSummary: (hashid: string) =>
    apiClient.post<LessonDetail>(`/lessons/${hashid}/summary/realign`).then((r) => r.data),

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

  exportDocument: (
    hashid: string,
    exportType: 'summary' | 'edited' | 'transcript' | 'sources' | 'sources_detailed',
    options: {
      format: 'md' | 'docx' | 'pdf'
      include_fields?: string[]
      transcript_type?: 'initial' | 'corrected'
      lang?: string
    },
  ) => {
    const query = new URLSearchParams()
    query.append('format', options.format)
    ;(options.include_fields ?? []).forEach((field) => query.append('include_fields', field))
    if (exportType === 'transcript' && options.transcript_type) {
      query.append('transcript_type', options.transcript_type)
    }
    if (options.lang) {
      query.append('lang', options.lang)
    }
    return apiClient
      .get<Blob>(`/lessons/${hashid}/exports/${exportType}?${query.toString()}`, {
        responseType: 'blob',
      })
      .then((r) => r.data)
  },
}

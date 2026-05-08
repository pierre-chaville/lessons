import { apiClient } from './client'
import type {
  Booklet,
  BookletItem,
  BookletLessonItem,
  BookletDetail,
  BookletCreate,
  BookletListResponse,
  BookletStatus,
  BookletUpdate,
} from './types'

export const bookletsApi = {
  list: (params?: { status?: string; search?: string; course_id?: number; offset?: number; limit?: number }) =>
    apiClient.get<BookletListResponse>('/booklets', { params }).then((r) => r.data),

  create: (data: BookletCreate) =>
    apiClient.post<Booklet>('/booklets', data).then((r) => r.data),

  get: (id: number) =>
    apiClient.get<BookletDetail>(`/booklets/${id}`).then((r) => r.data),

  update: (id: number, data: BookletUpdate) =>
    apiClient.patch<Booklet>(`/booklets/${id}`, data).then((r) => r.data),

  delete: (id: number) =>
    apiClient.delete(`/booklets/${id}`),

  changeStatus: (id: number, new_status: BookletStatus, reason?: string) =>
    apiClient.post<Booklet>(`/booklets/${id}/status`, { new_status, reason }).then((r) => r.data),

  addLesson: (id: number, lesson_id: number, position?: number) =>
    apiClient
      .post<BookletLessonItem>(`/booklets/${id}/lessons`, { lesson_id, position })
      .then((r) => r.data),

  addChapter: (
    id: number,
    data: {
      position?: number
      chapter_title: string
      chapter_subtitle?: string | null
      chapter_body?: string | null
      chapter_starts_new_page?: boolean
    },
  ) =>
    apiClient
      .post<BookletItem>(`/booklets/${id}/items`, { item_type: 'chapter', ...data })
      .then((r) => r.data),

  updateChapter: (
    id: number,
    item_id: number,
    data: {
      chapter_title?: string | null
      chapter_subtitle?: string | null
      chapter_body?: string | null
      chapter_starts_new_page?: boolean
    },
  ) =>
    apiClient
      .patch<BookletItem>(`/booklets/${id}/items/${item_id}`, data)
      .then((r) => r.data),

  removeLesson: (id: number, lesson_id: number) =>
    apiClient.delete(`/booklets/${id}/lessons/${lesson_id}`),

  removeItem: (id: number, item_id: number) =>
    apiClient.delete(`/booklets/${id}/items/${item_id}`),

  reorderLessons: (id: number, lesson_ids: number[]) =>
    apiClient
      .post<BookletLessonItem[]>(`/booklets/${id}/reorder`, { lesson_ids })
      .then((r) => r.data),

  reorderItems: (id: number, item_ids: number[]) =>
    apiClient
      .post<BookletItem[]>(`/booklets/${id}/reorder`, { item_ids })
      .then((r) => r.data),

  downloadPdf: (id: number) =>
    apiClient
      .get<Blob>(`/booklets/${id}/download-pdf`, { responseType: 'blob' })
      .then((r) => r.data),

  downloadMarkdown: (id: number) =>
    apiClient
      .get<Blob>(`/booklets/${id}/download-markdown`, { responseType: 'blob' })
      .then((r) => r.data),
}

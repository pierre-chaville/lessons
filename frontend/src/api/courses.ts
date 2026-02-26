import { apiClient } from './client'
import type { Course, CourseCreate, CourseUpdate } from './types'

export const coursesApi = {
  list: () => apiClient.get<Course[]>('/courses').then((r) => r.data),

  get: (hashid: string) => apiClient.get<Course>(`/courses/${hashid}`).then((r) => r.data),

  create: (data: CourseCreate) =>
    apiClient.post<Course>('/courses', data).then((r) => r.data),

  update: (hashid: string, data: CourseUpdate) =>
    apiClient.patch<Course>(`/courses/${hashid}`, data).then((r) => r.data),

  delete: (hashid: string) => apiClient.delete(`/courses/${hashid}`),
}

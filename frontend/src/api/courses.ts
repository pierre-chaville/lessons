import { apiClient } from './client'
import type { Course, CourseCreate, CourseUpdate } from './types'

export const coursesApi = {
  list: () => apiClient.get<Course[]>('/courses').then((r) => r.data),

  get: (id: number) => apiClient.get<Course>(`/courses/${id}`).then((r) => r.data),

  create: (data: CourseCreate) =>
    apiClient.post<Course>('/courses', data).then((r) => r.data),

  update: (id: number, data: CourseUpdate) =>
    apiClient.patch<Course>(`/courses/${id}`, data).then((r) => r.data),

  delete: (id: number) => apiClient.delete(`/courses/${id}`),
}

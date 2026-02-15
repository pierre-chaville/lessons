import { apiClient } from './client'
import type { Task, TaskCreate } from './types'

export const tasksApi = {
  list: () => apiClient.get<Task[]>('/tasks').then((r) => r.data),

  get: (id: number) => apiClient.get<Task>(`/tasks/${id}`).then((r) => r.data),

  create: (data: TaskCreate) =>
    apiClient.post<Task>('/tasks', data).then((r) => r.data),

  delete: (id: number) => apiClient.delete(`/tasks/${id}`),
}

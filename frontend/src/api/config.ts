import { apiClient } from './client'
import type { AppConfig } from './types'

export const configApi = {
  get: () => apiClient.get<AppConfig>('/config').then((r) => r.data),

  update: (data: Partial<AppConfig>) =>
    apiClient.put<AppConfig>('/config', data).then((r) => r.data),

  reset: () => apiClient.post<AppConfig>('/config/reset').then((r) => r.data),
}

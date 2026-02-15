import { apiClient } from './client'
import type { AppConfig } from './types'

// Backend PUT /config wraps the body as { config: ... } (ConfigUpdate schema)
// and returns { message, config }. Reset also returns { message, config }.
interface ConfigResponse {
  message: string
  config: AppConfig
}

export const configApi = {
  get: () => apiClient.get<AppConfig>('/config').then((r) => r.data),

  update: (data: AppConfig) =>
    apiClient
      .put<ConfigResponse>('/config', { config: data })
      .then((r) => r.data.config),

  reset: () =>
    apiClient
      .post<ConfigResponse>('/config/reset')
      .then((r) => r.data.config),
}

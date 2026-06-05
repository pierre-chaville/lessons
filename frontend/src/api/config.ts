import { apiClient } from './client'
import type { AppConfig, PreferenceVersion, VersionDiffResponse } from './types'

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

  listVersions: (params?: { limit?: number; before?: number }) =>
    apiClient
      .get<PreferenceVersion[]>('/config/versions', { params })
      .then((r) => r.data),

  getVersion: (versionId: string) =>
    apiClient
      .get<PreferenceVersion>(`/config/versions/${versionId}`)
      .then((r) => r.data),

  getVersionYaml: (versionId: string) =>
    apiClient
      .get<{ yaml: string }>(`/config/versions/${versionId}/yaml`)
      .then((r) => r.data.yaml),

  getVersionDiff: (versionAId: string, versionBId: string) =>
    apiClient
      .get<VersionDiffResponse>(`/config/versions/${versionAId}/diff/${versionBId}`)
      .then((r) => r.data),

  restoreVersion: (versionId: string, reason: string) =>
    apiClient
      .post<PreferenceVersion>(`/config/versions/${versionId}/restore`, { reason })
      .then((r) => r.data),
}

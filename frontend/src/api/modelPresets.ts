import { apiClient } from './client'
import type {
  ModelPreset,
  ModelPresetCreate,
  ModelPresetExport,
  ModelPresetImportResult,
  ModelPresetTransfer,
  ModelPresetUpdate,
} from './types'

export const modelPresetsApi = {
  list: () => apiClient.get<ModelPreset[]>('/model-presets').then((r) => r.data),

  get: (id: number) =>
    apiClient.get<ModelPreset>(`/model-presets/${id}`).then((r) => r.data),

  create: (data: ModelPresetCreate) =>
    apiClient.post<ModelPreset>('/model-presets', data).then((r) => r.data),

  update: (id: number, data: ModelPresetUpdate) =>
    apiClient.patch<ModelPreset>(`/model-presets/${id}`, data).then((r) => r.data),

  delete: (id: number) => apiClient.delete(`/model-presets/${id}`),

  exportJson: () =>
    apiClient.get<ModelPresetExport>('/model-presets/export').then((r) => r.data),

  /** Upsert by id: existing ids are overwritten, missing ids are created with that id. */
  importJson: (presets: ModelPresetTransfer[]) =>
    apiClient
      .post<ModelPresetImportResult>('/model-presets/import', { presets })
      .then((r) => r.data),
}

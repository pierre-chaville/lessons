import { apiClient } from './client'
import type { HebrewDisplaySettings, UserPreferences } from './types'

/** The signed-in user's own resources (no user id: always the token's user). */
export const meApi = {
  getPreferences: () => apiClient.get<UserPreferences>('/me/preferences').then((r) => r.data),

  updateHebrewDisplay: (settings: HebrewDisplaySettings) =>
    apiClient.put<HebrewDisplaySettings>('/me/preferences/hebrew-display', settings).then((r) => r.data),
}

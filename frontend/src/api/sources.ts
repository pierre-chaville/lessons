import { apiClient } from './client'

/** Shape returned by the backend /sefaria-cache/:slug endpoint. */
export interface SefariaCacheEntry {
  id: number
  type: string | null
  work: string | null
  ref: string | null
  he_ref: string | null
  standard_slug: string
  text_english: string | null
  text_hebrew: string | null
  fetched_at: string
}

/**
 * Fetch source text from the backend Sefaria cache.
 */
export const sourcesApi = {
  getSefariaCache: (slug: string) =>
    apiClient
      .get<SefariaCacheEntry>(`/sefaria-cache/${encodeURIComponent(slug)}`)
      .then((r) => r.data),
}

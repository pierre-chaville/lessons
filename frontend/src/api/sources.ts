import axios from 'axios'

/** Shape of a Sefaria /api/texts/:ref response (partial — only used fields). */
export interface SefariaText {
  ref: string
  heRef: string
  text: string | string[]
  he: string | string[]
  titleVariants: string[]
  heTitleVariants: string[]
}

/**
 * Fetch source text from the Sefaria public API.
 * Uses a plain axios instance — not the authenticated apiClient.
 */
export const sourcesApi = {
  getSefaria: (slug: string) =>
    axios
      .get<SefariaText>(`https://www.sefaria.org/api/texts/${encodeURIComponent(slug)}`)
      .then((r) => r.data),
}

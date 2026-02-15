import { apiClient } from './client'
import type { SearchLessonResult, SearchParams } from './types'

export const searchApi = {
  search: (params: SearchParams) =>
    apiClient.get<SearchLessonResult[]>('/search', { params }).then((r) => r.data),
}

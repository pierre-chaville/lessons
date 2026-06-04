import { apiClient } from './client'
import type { RagSearchRequest, RagSearchResponse, SearchLessonResult, SearchParams } from './types'

export const searchApi = {
  search: (params: SearchParams) =>
    apiClient.get<SearchLessonResult[]>('/search', { params }).then((r) => r.data),

  askAi: (data: RagSearchRequest) =>
    apiClient.post<RagSearchResponse>('/search/ai', data).then((r) => r.data),
}

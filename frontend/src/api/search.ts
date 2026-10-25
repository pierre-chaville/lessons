import { apiBaseUrl, apiClient, getAuthHeaders } from './client'
import type { RagSearchRequest, RagSearchResponse, SearchLessonResult, SearchParams } from './types'

export type RagProgressStep = 'search' | 'rerank' | 'generate'

type AskAiOptions = {
  onProgress?: (step: RagProgressStep) => void
  onToken?: (token: string) => void
}

const PROGRESS_STEPS = new Set<RagProgressStep>(['search', 'rerank', 'generate'])

type StreamEvent = {
  type?: string
  step?: string
  content?: string
  message?: string
  answer?: string
  citations?: RagSearchResponse['citations']
}

function handleStreamEvent(
  event: StreamEvent,
  callbacks: {
    onProgress?: (step: RagProgressStep) => void
    onToken?: (token: string) => void
  },
): RagSearchResponse | null {
  if (event.type === 'progress' && event.step && PROGRESS_STEPS.has(event.step as RagProgressStep)) {
    callbacks.onProgress?.(event.step as RagProgressStep)
    return null
  }

  if (event.type === 'token' && typeof event.content === 'string' && event.content) {
    callbacks.onToken?.(event.content)
    return null
  }

  if (event.type === 'result') {
    return {
      answer: event.answer ?? '',
      citations: event.citations ?? [],
    }
  }

  if (event.type === 'error') {
    throw new Error(event.message || 'AI search failed')
  }

  return null
}

async function readAskAiStream(
  response: Response,
  options: AskAiOptions = {},
): Promise<RagSearchResponse> {
  if (!response.body) {
    throw new Error('Missing response body')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: RagSearchResponse | null = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) continue
      const nextResult = handleStreamEvent(JSON.parse(trimmed) as StreamEvent, options)
      if (nextResult) result = nextResult
    }
  }

  if (buffer.trim()) {
    const nextResult = handleStreamEvent(JSON.parse(buffer.trim()) as StreamEvent, options)
    if (nextResult) result = nextResult
  }

  if (!result) {
    throw new Error('AI search completed without a result')
  }

  return result
}

export const searchApi = {
  search: (params: SearchParams) =>
    apiClient.get<SearchLessonResult[]>('/search', { params }).then((r) => r.data),

  askAi: async (data: RagSearchRequest, options: AskAiOptions = {}): Promise<RagSearchResponse> => {
    const response = await fetch(`${apiBaseUrl}/search/ai`, {
      method: 'POST',
      headers: await getAuthHeaders(),
      body: JSON.stringify(data),
    })

    if (!response.ok) {
      throw new Error(`AI search failed (${response.status})`)
    }

    return readAskAiStream(response, options)
  },
}

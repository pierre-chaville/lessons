import { computed, ref, watch } from 'vue'

import { lessonsApi } from '@/api/lessons'
import type { HebrewMode, LessonHebrewTerm } from '@/api/types'
import { useHebrewDisplay } from '@/composables/useHebrewDisplay'
import { buildHebrewTermIndex, renderHebrewTerms } from '@/utils/hebrewText'

export interface LessonHebrewSource {
  hashid: string
  editedMarkdown: string | null | undefined
  summary: string | null | undefined
  editedMode: HebrewMode
  summaryMode: HebrewMode
}

/**
 * Glossary terms of a lesson and a renderer applying the user's Hebrew display
 * settings to its Hebrew-mode texts (edited text and summary).
 *
 * @example
 * const { renderHebrew, termsById } = useLessonHebrewTerms(() => ({ ... }))
 * renderMarkdown(renderHebrew(lesson.summary, lesson.summary_hebrew_mode))
 */
export function useLessonHebrewTerms(source: () => LessonHebrewSource) {
  const { settings, loadFromServer } = useHebrewDisplay()

  const terms = ref<LessonHebrewTerm[]>([])
  const index = computed(() => buildHebrewTermIndex(terms.value))
  const termsById = computed(() => index.value.byId)
  let requestId = 0

  const needsTerms = computed(() => {
    const { editedMode, summaryMode } = source()
    return editedMode !== 'translit' || summaryMode !== 'translit'
  })

  const loadTerms = async (hashid: string) => {
    const current = ++requestId
    try {
      const result = await lessonsApi.hebrewTerms(hashid)
      if (current === requestId) terms.value = result
    } catch {
      // Without glossary data, Hebrew terms are shown as written.
      if (current === requestId) terms.value = []
    }
  }

  // Reload when the lesson or its Hebrew texts change (new terms may appear).
  watch(
    () => {
      const { hashid, editedMarkdown, summary, editedMode, summaryMode } = source()
      return [hashid, editedMarkdown, summary, editedMode, summaryMode, needsTerms.value] as const
    },
    ([hashid]) => {
      if (needsTerms.value) {
        void loadFromServer()
        void loadTerms(hashid)
      } else {
        requestId += 1
        terms.value = []
      }
    },
    { immediate: true },
  )

  // Rendering is memoized: the lesson view re-renders often (audio playback).
  // Settings and index are replaced (never mutated) on change, so identity tells when to reset.
  let cache = new Map<string, string>()
  let cacheIndex: unknown = null
  let cacheSettings: unknown = null

  /** Markdown with Hebrew terms in the user's display mode (unchanged for transliterated texts). */
  const renderHebrew = (markdown: string | null | undefined, mode: HebrewMode): string => {
    if (!markdown || mode === 'translit') return markdown || ''
    // Read reactive state here so templates re-render when it changes.
    const currentIndex = index.value
    const currentSettings = settings.value
    if (currentIndex !== cacheIndex || currentSettings !== cacheSettings) {
      cache = new Map()
      cacheIndex = currentIndex
      cacheSettings = currentSettings
    }
    const cached = cache.get(markdown)
    if (cached !== undefined) return cached
    const rendered = renderHebrewTerms(markdown, currentIndex, currentSettings)
    cache.set(markdown, rendered)
    return rendered
  }

  return { renderHebrew, termsById, needsTerms }
}

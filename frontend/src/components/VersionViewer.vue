<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { marked } from 'marked'
import { useI18n } from 'vue-i18n'
import { lessonsApi } from '@/api/lessons'
import type { ContentType, LessonVersion } from '@/api/types'

type TranscriptSegment = {
  start?: number
  end?: number
  text?: string
}

const props = defineProps<{
  lessonHashid: string
  contentType: ContentType
  versionId: string | null
}>()

const { t } = useI18n()
const loading = ref(false)
const error = ref<string | null>(null)
const version = ref<LessonVersion | null>(null)

marked.setOptions({ breaks: true, gfm: true })

const renderMarkdown = (markdown: string | null | undefined): string => {
  if (!markdown) return ''
  return marked(markdown) as string
}

const asText = computed(() => {
  if (!version.value) return ''
  if (typeof version.value.content === 'string') return version.value.content
  return ''
})

const asSegments = computed<TranscriptSegment[]>(() => {
  if (!version.value || !Array.isArray(version.value.content)) return []
  return version.value.content as TranscriptSegment[]
})

const asEditedMarkdown = computed(() => {
  if (!version.value) return ''
  const content = version.value.content
  if (content && typeof content === 'object' && 'markdown' in content) {
    const markdown = (content as { markdown?: unknown }).markdown
    return typeof markdown === 'string' ? markdown : ''
  }
  return typeof content === 'string' ? content : ''
})

const formatTimestamp = (seconds?: number): string => {
  if (seconds === undefined || seconds === null) return '--:--'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
}

const isLegacyBackfillWithoutContent = (candidate: LessonVersion | null): boolean => {
  if (!candidate) return false
  if (candidate.content !== null && candidate.content !== undefined) return false
  if (candidate.version_number !== 1) return false
  return candidate.sealed_reason === 'backfill'
}

const fallbackContentFromCurrentLesson = (contentType: ContentType, lesson: Record<string, unknown>): unknown => {
  if (contentType === 'title' || contentType === 'brief' || contentType === 'summary') {
    const value = lesson[contentType]
    return typeof value === 'string' ? value : ''
  }
  if (contentType === 'corrected_transcript') {
    const value = lesson.corrected_transcript
    return Array.isArray(value) ? value : []
  }
  if (contentType === 'edited_transcript') {
    const value = lesson.edited_transcript
    return value && typeof value === 'object' ? value : { markdown: '' }
  }
  return null
}

const loadVersion = async () => {
  if (!props.versionId) {
    version.value = null
    return
  }
  loading.value = true
  error.value = null
  try {
    const loadedVersion = await lessonsApi.getVersion(props.lessonHashid, props.versionId)
    if (isLegacyBackfillWithoutContent(loadedVersion)) {
      try {
        const lesson = await lessonsApi.get(props.lessonHashid)
        loadedVersion.content = fallbackContentFromCurrentLesson(props.contentType, lesson as Record<string, unknown>)
      } catch {
        // Keep empty content if lesson fetch fails.
      }
    }
    version.value = loadedVersion
  } catch (e: any) {
    version.value = null
    error.value = e?.response?.data?.detail || t('history.versionLoadFailed')
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.lessonHashid, props.versionId],
  () => {
    loadVersion()
  },
  { immediate: true },
)
</script>

<template>
  <div class="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
    <div v-if="loading" class="text-sm text-gray-500 dark:text-gray-400">
      {{ t('history.loadingVersionContent') }}
    </div>
    <div v-else-if="error" class="text-sm text-red-600 dark:text-red-400">
      {{ error }}
    </div>
    <div v-else-if="!version" class="text-sm text-gray-500 dark:text-gray-400">
      {{ t('history.noVersionSelected') }}
    </div>
    <div v-else-if="!version.content" class="text-sm text-gray-500 dark:text-gray-400">
      {{ t('history.emptyVersion') }}
    </div>

    <div
      v-else-if="contentType === 'title' || contentType === 'brief'"
      class="whitespace-pre-wrap text-sm leading-6 text-gray-900 dark:text-gray-100"
    >
      {{ asText }}
    </div>

    <div
      v-else-if="contentType === 'summary'"
      class="prose prose-indigo max-w-none dark:prose-invert"
      v-html="renderMarkdown(asText)"
    />

    <div
      v-else-if="contentType === 'edited_transcript'"
      class="prose prose-indigo max-w-none dark:prose-invert"
      v-html="renderMarkdown(asEditedMarkdown)"
    />

    <div v-else class="space-y-3">
      <div
        v-for="(segment, index) in asSegments"
        :key="index"
        class="rounded-md border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-900"
      >
        <div class="mb-1 text-xs font-semibold text-gray-500 dark:text-gray-400">
          {{ formatTimestamp(segment.start) }} - {{ formatTimestamp(segment.end) }}
        </div>
        <div class="whitespace-pre-wrap text-sm leading-6 text-gray-900 dark:text-gray-100">
          {{ segment.text ?? '' }}
        </div>
      </div>
    </div>
  </div>
</template>

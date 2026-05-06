<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ContentType, VersionDiffResponse } from '@/api/types'
import { lessonsApi } from '@/api/lessons'

const props = defineProps<{
  lessonHashid: string
  versionAId: string
  versionBId: string
  contentType: ContentType
}>()

const loading = ref(false)
const error = ref<string | null>(null)
const diff = ref<VersionDiffResponse | null>(null)
const { t } = useI18n()

const fetchDiff = async () => {
  if (!props.versionAId || !props.versionBId) return
  loading.value = true
  error.value = null
  try {
    diff.value = await lessonsApi.getVersionDiff(
      props.lessonHashid,
      props.versionAId,
      props.versionBId,
    )
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('history.diffLoadFailed')
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.lessonHashid, props.versionAId, props.versionBId, props.contentType],
  fetchDiff,
  { immediate: true },
)

const statusBadgeClass = (status: string) => {
  if (status === 'added') return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
  if (status === 'removed') return 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
  if (status === 'modified') return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
  return 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
}

const statusLabel = (status: string) => {
  if (status === 'added') return t('history.statusAdded')
  if (status === 'removed') return t('history.statusRemoved')
  if (status === 'modified') return t('history.statusModified')
  return t('history.statusUnchanged')
}
</script>

<template>
  <div class="space-y-3">
    <div v-if="loading" class="text-sm text-gray-500 dark:text-gray-400">{{ t('history.loadingDiff') }}</div>
    <div v-else-if="error" class="text-sm text-red-600 dark:text-red-400">{{ error }}</div>
    <template v-else-if="diff">
      <div
        v-if="diff.type === 'text'"
        dir="auto"
        class="rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 p-3"
      >
        <pre
          class="whitespace-pre-wrap text-xs leading-5 text-gray-800 dark:text-gray-200"
        >{{ diff.diff }}</pre>
      </div>

      <div v-else class="space-y-2 max-h-80 overflow-auto">
        <div
          v-for="segment in diff.segments"
          :key="segment.segment_index"
          class="rounded-md border border-gray-200 dark:border-gray-700 p-3"
        >
          <div class="mb-2 flex items-center gap-2">
            <span class="text-xs font-semibold text-gray-500 dark:text-gray-400">
              {{ t('history.segmentLabel', { index: segment.segment_index }) }}
            </span>
            <span
              :class="[
                'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
                statusBadgeClass(segment.status),
              ]"
            >
              {{ statusLabel(segment.status) }}
            </span>
          </div>
          <pre
            dir="auto"
            class="whitespace-pre-wrap text-xs leading-5 text-gray-800 dark:text-gray-200"
          >{{ segment.text_diff }}</pre>
        </div>
      </div>
    </template>
  </div>
</template>


<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Dialog } from '@headlessui/vue'
import { useI18n } from 'vue-i18n'
import type { ClerkUser } from '@/api/users'
import { usersApi } from '@/api/users'
import { lessonsApi } from '@/api/lessons'
import type { ContentType, LessonVersion } from '@/api/types'
import { usePermissions } from '@/composables/usePermissions'
import DiffViewer from '@/components/DiffViewer.vue'
import RestoreVersionModal from '@/components/RestoreVersionModal.vue'

const props = defineProps<{
  lessonId: number
  lessonHashid: string
  contentType: ContentType
}>()
const emit = defineEmits<{ (e: 'restored'): void }>()
const { t } = useI18n()

const { can } = usePermissions()
const canRestore = computed(() => can('lessons', 'update'))

const loading = ref(false)
const error = ref<string | null>(null)
const versions = ref<LessonVersion[]>([])
const users = ref<ClerkUser[]>([])
const hasMore = ref(true)

const compareVersion = ref<LessonVersion | null>(null)
const restoreTarget = ref<LessonVersion | null>(null)

const currentVersion = computed(() => versions.value.find((v) => v.is_current) ?? null)

const loadUsers = async () => {
  if (!canRestore.value || users.value.length > 0) return
  try {
    users.value = await usersApi.list()
  } catch {
    users.value = []
  }
}

const getUserName = (id: string | null) => {
  if (!id) return t('history.pipeline')
  const u = users.value.find((x) => x.id === id)
  if (!u) return id
  return [u.first_name, u.last_name].filter(Boolean).join(' ') || u.email || id
}

const loadVersions = async (reset = false) => {
  loading.value = true
  error.value = null
  try {
    const before = reset ? undefined : versions.value[versions.value.length - 1]?.version_number
    const rows = await lessonsApi.listVersions(props.lessonHashid, {
      content_type: props.contentType,
      limit: 20,
      before,
    })
    if (reset) versions.value = rows
    else versions.value.push(...rows)
    hasMore.value = rows.length === 20
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('history.versionLoadFailed')
  } finally {
    loading.value = false
  }
}

const sealCurrentSession = async () => {
  if (!currentVersion.value) return
  loading.value = true
  error.value = null
  try {
    await lessonsApi.checkpointVersion(
      props.lessonHashid,
      props.contentType,
      'manual_checkpoint',
    )
    await loadVersions(true)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('history.sealFailed')
  } finally {
    loading.value = false
  }
}

const onRestored = async () => {
  restoreTarget.value = null
  await loadVersions(true)
  emit('restored')
}

watch(
  () => [props.lessonHashid, props.contentType],
  async () => {
    versions.value = []
    hasMore.value = true
    await Promise.all([loadUsers(), loadVersions(true)])
  },
  { immediate: true },
)

const sourceBadge = (source: LessonVersion['version_source']) => {
  if (source === 'human') return t('history.sourceHuman')
  if (source === 'pipeline') return t('history.sourcePipeline')
  return t('history.sourceRestore')
}

const contentTypeLabel = (contentType: ContentType): string => {
  const map: Record<ContentType, string> = {
    title: t('history.contentTypeTitle'),
    corrected_transcript: t('history.contentTypeCorrectedTranscript'),
    edited_transcript: t('history.contentTypeEditedTranscript'),
    brief: t('history.contentTypeBrief'),
    summary: t('history.contentTypeSummary'),
  }
  return map[contentType] ?? contentType
}

const formatDateTime = (iso: string | null) => {
  if (!iso) return 'n/a'
  return new Date(iso).toLocaleString()
}

const sessionMinutes = (v: LessonVersion) => {
  if (!v.last_edited_at) return 0
  const start = new Date(v.created_at).getTime()
  const end = new Date(v.last_edited_at).getTime()
  return Math.max(0, Math.round((end - start) / 60000))
}

const sealedReasonLabel = (reason: string | null) => {
  if (!reason) return ''
  const map: Record<string, string> = {
    status_changed: t('history.sealedReasonStatusChanged'),
    different_user: t('history.sealedReasonDifferentUser'),
    manual_checkpoint: t('history.sealedReasonManualCheckpoint'),
    window_expired: t('history.sealedReasonWindowExpired'),
    restored_over: t('history.sealedReasonRestoredOver'),
    pipeline_rerun: t('history.sealedReasonPipelineRerun'),
    source_changed: t('history.sealedReasonSourceChanged'),
    backfill: t('history.sealedReasonBackfill'),
  }
  return map[reason] ?? reason
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white">
        {{ t('history.versionHistoryFor', { contentType: contentTypeLabel(contentType) }) }}
      </h3>
      <button
        v-if="canRestore && currentVersion && !currentVersion.is_sealed"
        @click="sealCurrentSession"
        class="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
      >
        {{ t('history.sealCurrentSession') }}
      </button>
    </div>

    <p v-if="error" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>
    <div v-if="loading && versions.length === 0" class="text-sm text-gray-500 dark:text-gray-400">
      {{ t('history.loadingHistory') }}
    </div>

    <div class="space-y-3">
      <div
        v-for="version in versions"
        :key="version.id"
        class="rounded-md border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-900"
      >
        <div class="mb-2 flex items-center justify-between gap-3">
          <div class="flex items-center gap-2">
            <span class="text-sm font-semibold text-gray-900 dark:text-gray-100">
              v{{ version.version_number }}
            </span>
            <span class="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-700 dark:bg-gray-700 dark:text-gray-300">
              {{ sourceBadge(version.version_source) }}
            </span>
            <span
              v-if="version.is_current"
              class="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300"
            >
              {{ t('history.current') }}
            </span>
            <span
              v-if="version.is_sealed"
              class="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700 dark:bg-amber-900/30 dark:text-amber-300"
            >
              {{ t('history.sealed') }}{{ version.sealed_reason ? `: ${sealedReasonLabel(version.sealed_reason)}` : '' }}
            </span>
          </div>
          <div class="flex items-center gap-2">
            <button
              class="rounded border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
              @click="compareVersion = version"
            >
              {{ t('history.view') }}
            </button>
            <button
              v-if="currentVersion && version.id !== currentVersion.id"
              class="rounded border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
              @click="compareVersion = version"
            >
              {{ t('history.compareToCurrent') }}
            </button>
            <button
              v-if="canRestore && currentVersion && version.id !== currentVersion.id"
              class="rounded bg-indigo-600 px-2 py-1 text-xs font-medium text-white hover:bg-indigo-700"
              @click="restoreTarget = version"
            >
              {{ t('history.restore') }}
            </button>
          </div>
        </div>

        <div class="text-xs text-gray-600 dark:text-gray-400">
          {{ t('history.sessionInfo', {
            started: formatDateTime(version.created_at),
            lastEdited: formatDateTime(version.last_edited_at),
            edits: version.edit_count,
            minutes: sessionMinutes(version),
          }) }}
        </div>
        <div class="mt-1 text-xs text-gray-600 dark:text-gray-400">
          {{ t('history.authorLabel') }}: {{ version.version_source === 'pipeline' ? t('history.pipeline') : getUserName(version.created_by_id) }}
        </div>
        <div
          v-if="version.change_summary"
          class="mt-2 rounded bg-gray-50 px-2 py-1 text-xs text-gray-700 dark:bg-gray-800 dark:text-gray-300"
        >
          {{ version.change_summary }}
        </div>
        <div v-if="version.restored_from_id" class="mt-1 text-xs text-indigo-600 dark:text-indigo-400">
          {{ t('history.restoredFromVersionId', { id: version.restored_from_id }) }}
        </div>
      </div>
    </div>

    <div class="flex justify-center">
      <button
        v-if="hasMore"
        @click="loadVersions(false)"
        :disabled="loading"
        class="rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
      >
        {{ t('history.loadMore') }}
      </button>
    </div>

    <Dialog v-if="compareVersion && currentVersion" :open="true" @close="compareVersion = null" class="relative z-50">
      <div class="fixed inset-0 bg-black/30" aria-hidden="true" />
      <div class="fixed inset-0 flex items-center justify-center p-4">
        <div class="w-full max-w-4xl rounded-lg bg-white p-4 dark:bg-gray-800">
          <div class="mb-3 flex items-center justify-between">
            <h4 class="text-sm font-semibold text-gray-900 dark:text-white">
              {{ t('history.compareVersionsTitle', {
                from: currentVersion.version_number,
                to: compareVersion.version_number,
              }) }}
            </h4>
            <button class="text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200" @click="compareVersion = null">
              {{ t('lessons.close') }}
            </button>
          </div>
          <DiffViewer
            :lesson-hashid="lessonHashid"
            :version-a-id="currentVersion.id"
            :version-b-id="compareVersion.id"
            :content-type="contentType"
          />
        </div>
      </div>
    </Dialog>

    <RestoreVersionModal
      :is-open="!!restoreTarget"
      :lesson-hashid="lessonHashid"
      :content-type="contentType"
      :target-version="restoreTarget"
      :current-version="currentVersion"
      @close="restoreTarget = null"
      @restored="onRestored"
    />
  </div>
</template>


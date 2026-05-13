<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ClerkUser } from '@/api/users'
import { usersApi } from '@/api/users'
import { lessonsApi } from '@/api/lessons'
import type { ContentType, LessonVersion } from '@/api/types'
import { usePermissions } from '@/composables/usePermissions'
import { useVersionLabel } from '@/composables/useVersionLabel'
import RestoreVersionModal from '@/components/RestoreVersionModal.vue'

const props = defineProps<{
  lessonId: number
  lessonHashid: string
  contentType: ContentType
  selectedVersionId: string | null
  activeCompare: {
    versionAId: string
    versionBId: string
    fromVersionNumber?: number | null
    toVersionNumber?: number | null
  } | null
}>()

const emit = defineEmits<{
  (e: 'update:selectedVersionId', value: string | null): void
  (e: 'restored'): void
  (e: 'versions-loaded', versions: LessonVersion[]): void
  (
    e: 'compare',
    payload: {
      versionAId: string
      versionBId: string
      fromVersionNumber: number
      toVersionNumber: number
    },
  ): void
}>()

const { t } = useI18n()
const { can } = usePermissions()
const canRestore = computed(() => can('lessons', 'update'))

const loading = ref(false)
const error = ref<string | null>(null)
const versions = ref<LessonVersion[]>([])
const users = ref<ClerkUser[]>([])
const hasMore = ref(true)

const restoreTarget = ref<LessonVersion | null>(null)

const currentVersion = computed(() => versions.value.find((v) => v.is_current) ?? null)

const loadUsers = async () => {
  if (users.value.length > 0) return
  try {
    users.value = await usersApi.list()
  } catch {
    users.value = []
  }
}

const getUserName = (id: string | null) => {
  if (!id) return t('history.pipeline')
  const user = users.value.find((x) => x.id === id)
  if (!user) return id
  return [user.first_name, user.last_name].filter(Boolean).join(' ') || user.email || id
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
    if (reset) {
      versions.value = rows
    } else {
      versions.value.push(...rows)
    }
    hasMore.value = rows.length === 20
    emit('versions-loaded', versions.value)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('history.versionLoadFailed')
  } finally {
    loading.value = false
  }
}

const ensureSelectedVersion = () => {
  if (versions.value.length === 0) {
    emit('update:selectedVersionId', null)
    return
  }
  if (!props.selectedVersionId) {
    emit('update:selectedVersionId', null)
    return
  }
  const exists = versions.value.some((version) => version.id === props.selectedVersionId)
  if (!exists) {
    emit('update:selectedVersionId', null)
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
    ensureSelectedVersion()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('history.sealFailed')
  } finally {
    loading.value = false
  }
}

const onRestored = async () => {
  restoreTarget.value = null
  await loadVersions(true)
  ensureSelectedVersion()
  emit('restored')
}

const sourceBadge = (source: LessonVersion['version_source']) => {
  if (source === 'human') return t('history.sourceHuman')
  if (source === 'pipeline') return t('history.sourcePipeline')
  return t('history.sourceRestore')
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

const viewVersion = (version: LessonVersion) => {
  const selected = currentVersion.value?.id === version.id ? null : version.id
  emit('update:selectedVersionId', selected)
}

const previousVersion = (index: number): LessonVersion | null => {
  if (index >= versions.value.length - 1) return null
  return versions.value[index + 1]
}

watch(
  () => [props.lessonHashid, props.contentType],
  async () => {
    versions.value = []
    hasMore.value = true
    await Promise.all([loadUsers(), loadVersions(true)])
    ensureSelectedVersion()
  },
  { immediate: true },
)

watch(
  () => props.selectedVersionId,
  () => {
    ensureSelectedVersion()
  },
)
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between gap-2">
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white">
        {{ t('history.timelineTitle') }}
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
        v-for="(version, index) in versions"
        :key="version.id"
        :class="[
          'rounded-md border bg-white p-3 dark:bg-gray-900',
          (selectedVersionId ?? currentVersion?.id) === version.id
            ? 'border-indigo-300 ring-1 ring-indigo-200 dark:border-indigo-500/70 dark:ring-indigo-500/40'
            : 'border-gray-200 dark:border-gray-700',
        ]"
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
              {{ t('history.sealed') }}
            </span>
            <span
              v-if="activeCompare && (activeCompare.versionAId === version.id || activeCompare.versionBId === version.id)"
              class="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
            >
              {{
                t('history.comparingChip', {
                  from: activeCompare.fromVersionNumber ?? '?',
                  to: activeCompare.toVersionNumber ?? '?',
                })
              }}
            </span>
          </div>
        </div>

        <div class="mb-2 flex flex-wrap items-center gap-2">
          <button
            class="rounded border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
            @click="viewVersion(version)"
          >
            {{ t('history.view') }}
          </button>
          <button
            v-if="currentVersion && version.id !== currentVersion.id"
            class="rounded border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
            @click="
              emit('compare', {
                versionAId: version.id,
                versionBId: currentVersion.id,
                fromVersionNumber: version.version_number,
                toVersionNumber: currentVersion.version_number,
              })
            "
          >
            {{ t('history.compareToCurrent') }}
          </button>
          <button
            v-if="previousVersion(index)"
            class="rounded border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
            @click="
              emit('compare', {
                versionAId: previousVersion(index)!.id,
                versionBId: version.id,
                fromVersionNumber: previousVersion(index)!.version_number,
                toVersionNumber: version.version_number,
              })
            "
          >
            {{ t('history.compareToPrevious') }}
          </button>
          <button
            v-if="canRestore && currentVersion && version.id !== currentVersion.id"
            class="rounded bg-indigo-600 px-2 py-1 text-xs font-medium text-white hover:bg-indigo-700"
            @click="restoreTarget = version"
          >
            {{ t('history.restore') }}
          </button>
        </div>

        <div
          v-if="version.is_sealed && version.sealed_reason"
          class="mt-1 text-xs text-amber-700 dark:text-amber-300"
        >
          {{ t('history.sealed') }}: {{ sealedReasonLabel(version.sealed_reason) }}
        </div>

        <div class="text-xs text-gray-600 dark:text-gray-400">
          {{ useVersionLabel(version, t, getUserName) }}
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

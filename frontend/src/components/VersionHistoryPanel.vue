<script setup lang="ts">
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { ExclamationTriangleIcon } from '@heroicons/vue/24/outline'
import { useI18n } from 'vue-i18n'
import type { ContentType, LessonVersion } from '@/api/types'
import VersionTimeline from '@/components/VersionTimeline.vue'
import VersionViewer from '@/components/VersionViewer.vue'
import VersionDiffViewer from '@/components/VersionDiffViewer.vue'

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
  (
    e: 'update:activeCompare',
    value: {
      versionAId: string
      versionBId: string
      fromVersionNumber?: number | null
      toVersionNumber?: number | null
    } | null,
  ): void
  (e: 'close'): void
  (e: 'restored'): void
}>()

const { t } = useI18n()
const versions = ref<LessonVersion[]>([])
const isTimelineExpandedMobile = ref(false)

const selectedVersion = computed(() => {
  if (versions.value.length === 0) return null
  if (!props.selectedVersionId) return versions.value.find((v) => v.is_current) ?? versions.value[0]
  return versions.value.find((v) => v.id === props.selectedVersionId) ?? null
})

const contentTypeLabel = computed(() => {
  const map: Record<ContentType, string> = {
    title: t('history.contentTypeTitle'),
    corrected_transcript: t('history.contentTypeCorrectedTranscript'),
    edited_transcript: t('history.contentTypeEditedTranscript'),
    brief: t('history.contentTypeBrief'),
    summary: t('history.contentTypeSummary'),
  }
  return map[props.contentType] ?? props.contentType
})

const selectedVersionLabel = computed(() => {
  if (!selectedVersion.value) return ''
  const actor =
    selectedVersion.value.version_source === 'pipeline'
      ? t('history.pipeline')
      : selectedVersion.value.created_by_id || t('audit.system')
  const seal = selectedVersion.value.is_sealed ? t('history.sealed') : t('history.current')
  const timestamp = new Date(selectedVersion.value.created_at).toLocaleString()
  return t('history.contextBannerLabel', {
    version: selectedVersion.value.version_number,
    source: actor,
    seal,
    timestamp,
  })
})

const onSelectVersion = (versionId: string | null) => {
  emit('update:activeCompare', null)
  emit('update:selectedVersionId', versionId)
}

const onCompare = (payload: {
  versionAId: string
  versionBId: string
  fromVersionNumber: number
  toVersionNumber: number
}) => {
  emit('update:activeCompare', payload)
}

const clearCompare = () => {
  emit('update:activeCompare', null)
}

const compareTitle = computed(() => {
  if (!props.activeCompare) return ''
  if (
    props.activeCompare.fromVersionNumber !== undefined
    && props.activeCompare.fromVersionNumber !== null
    && props.activeCompare.toVersionNumber !== undefined
    && props.activeCompare.toVersionNumber !== null
  ) {
    return t('history.compareVersionsTitle', {
      from: props.activeCompare.fromVersionNumber,
      to: props.activeCompare.toVersionNumber,
    })
  }
  return t('history.compareGenericTitle')
})

const onPanelKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && props.activeCompare) {
    clearCompare()
  }
}

onMounted(() => {
  window.addEventListener('keydown', onPanelKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onPanelKeydown)
})

watch(
  () => props.selectedVersionId,
  () => {
    isTimelineExpandedMobile.value = false
  },
)

watch(
  () => [props.activeCompare, versions.value] as const,
  ([compare]) => {
    if (!compare) return
    if (compare.fromVersionNumber != null && compare.toVersionNumber != null) return
    const fromVersion = versions.value.find((version) => version.id === compare.versionAId)
    const toVersion = versions.value.find((version) => version.id === compare.versionBId)
    if (!fromVersion || !toVersion) return
    emit('update:activeCompare', {
      ...compare,
      fromVersionNumber: fromVersion.version_number,
      toVersionNumber: toVersion.version_number,
    })
  },
)
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between gap-3">
      <div class="text-sm text-gray-600 dark:text-gray-300">
        <span class="font-medium text-gray-900 dark:text-white">{{ t('lessons.title') }}</span>
        <span class="mx-2">></span>
        <span>{{ t('history.historyForLabel', { contentType: contentTypeLabel }) }}</span>
      </div>
      <button
        @click="emit('close')"
        class="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
      >
        {{ t('history.returnToEditing') }}
      </button>
    </div>

    <div class="sticky top-2 z-10 flex items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-800 dark:bg-amber-900/20">
      <div class="flex items-center gap-2 text-sm text-amber-900 dark:text-amber-200">
        <ExclamationTriangleIcon class="h-5 w-5 flex-shrink-0" />
        <span>{{ selectedVersionLabel }}</span>
      </div>
      <button
        @click="emit('close')"
        class="rounded-md border border-amber-300 px-3 py-1.5 text-xs font-medium text-amber-900 hover:bg-amber-100 dark:border-amber-700 dark:text-amber-200 dark:hover:bg-amber-900/50"
      >
        {{ t('history.returnToEditing') }}
      </button>
    </div>

    <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
      <section class="rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-800 md:col-span-1">
        <button
          class="mb-3 flex w-full items-center justify-between rounded-md border border-gray-200 px-3 py-2 text-left text-sm font-medium text-gray-700 dark:border-gray-600 dark:text-gray-200 md:hidden"
          @click="isTimelineExpandedMobile = !isTimelineExpandedMobile"
        >
          <span>
            {{ t('history.timelineTitle') }}
            <template v-if="selectedVersion">- v{{ selectedVersion.version_number }}</template>
          </span>
          <span>{{ isTimelineExpandedMobile ? '−' : '+' }}</span>
        </button>
        <div :class="isTimelineExpandedMobile ? 'block' : 'hidden md:block'">
          <VersionTimeline
            :lesson-id="lessonId"
            :lesson-hashid="lessonHashid"
            :content-type="contentType"
            :selected-version-id="selectedVersionId"
            :active-compare="activeCompare"
            @update:selected-version-id="onSelectVersion"
            @compare="onCompare"
            @restored="emit('restored')"
            @versions-loaded="versions = $event"
          />
        </div>
      </section>

      <section class="md:col-span-2">
        <div v-if="activeCompare" class="space-y-3">
          <div class="flex items-center justify-between rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-800">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">
              {{ compareTitle }}
            </h3>
            <button
              class="rounded border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
              @click="clearCompare"
            >
              {{ t('history.backToVersionView') }}
            </button>
          </div>
          <VersionDiffViewer
            :lesson-hashid="lessonHashid"
            :version-a-id="activeCompare.versionAId"
            :version-b-id="activeCompare.versionBId"
            :content-type="contentType"
          />
        </div>
        <VersionViewer
          v-else
          :lesson-hashid="lessonHashid"
          :content-type="contentType"
          :version-id="selectedVersionId ?? selectedVersion?.id ?? null"
        />
      </section>
    </div>
  </div>
</template>

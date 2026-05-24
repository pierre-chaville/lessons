<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'
import type { ContentType, LessonVersion } from '@/api/types'
import { lessonsApi } from '@/api/lessons'
import DiffViewer from '@/components/DiffViewer.vue'

const props = defineProps<{
  isOpen: boolean
  lessonHashid: string
  contentType: ContentType
  targetVersion: LessonVersion | null
  currentVersion: LessonVersion | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'restored', version: LessonVersion): void
}>()

const reason = ref('')
const saving = ref(false)
const error = ref<string | null>(null)
const { t } = useI18n()

watch(
  () => props.isOpen,
  (open) => {
    if (open) {
      reason.value = ''
      error.value = null
    }
  },
)

const canConfirm = computed(() => reason.value.trim().length > 0 && !saving.value)

const onConfirm = async () => {
  if (!props.targetVersion || !canConfirm.value) return
  saving.value = true
  error.value = null
  try {
    const restored = await lessonsApi.restoreVersion(
      props.lessonHashid,
      props.targetVersion.id,
      reason.value.trim(),
    )
    emit('restored', restored)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('history.restoreFailed')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog :open="isOpen" @close="emit('close')" class="relative z-50">
    <div class="fixed inset-0 bg-black/30" aria-hidden="true" />
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="flex w-full max-w-3xl max-h-[90vh] flex-col overflow-hidden rounded-lg bg-white dark:bg-gray-800 shadow-xl">
        <div class="overflow-y-auto px-6 pt-6 pb-4">
          <DialogTitle class="mb-3 text-lg font-semibold text-gray-900 dark:text-white">
            {{ t('history.restoreVersionTitle', { version: targetVersion?.version_number }) }}
          </DialogTitle>

          <p class="mb-3 text-sm text-gray-600 dark:text-gray-400">
            {{ t('history.restoreVersionHint') }}
          </p>

          <div v-if="targetVersion && currentVersion" class="mb-4">
            <div class="mb-2 text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">
              {{ t('history.diffPreview') }}
            </div>
            <DiffViewer
              :lesson-hashid="lessonHashid"
              :version-a-id="currentVersion.id"
              :version-b-id="targetVersion.id"
              :content-type="contentType"
            />
          </div>

          <label class="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">{{ t('history.reasonRequired') }}</label>
          <textarea
            v-model="reason"
            rows="4"
            class="mb-3 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
            :placeholder="t('history.restoreReasonPlaceholder')"
          />

          <p v-if="error" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>
        </div>

        <div class="flex justify-end gap-2 border-t border-gray-200 px-6 py-4 dark:border-gray-700">
          <button
            @click="emit('close')"
            :disabled="saving"
            class="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
          >
            {{ t('lessons.cancel') }}
          </button>
          <button
            @click="onConfirm"
            :disabled="!canConfirm"
            class="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {{ saving ? t('history.restoring') : t('history.confirmRestore') }}
          </button>
        </div>
      </DialogPanel>
    </div>
  </Dialog>
</template>


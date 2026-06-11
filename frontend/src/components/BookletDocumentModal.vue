<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'

type ExportFormat = 'md' | 'docx' | 'pdf'

const props = withDefaults(
  defineProps<{
    isOpen: boolean
    submitting?: boolean
    defaultFormat?: ExportFormat
    defaultFields?: string[]
    defaultIncludeTableOfContents?: boolean
  }>(),
  {
    submitting: false,
    defaultFormat: 'docx',
    defaultFields: () => [],
    defaultIncludeTableOfContents: true,
  },
)

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'export', payload: { format: ExportFormat; includeFields: string[]; includeTableOfContents: boolean }): void
}>()

const { t } = useI18n()

const selectedFormat = ref<ExportFormat>(props.defaultFormat)
const selectedFields = ref<string[]>([...props.defaultFields])
const includeTableOfContents = ref<boolean>(props.defaultIncludeTableOfContents)

watch(
  () => props.isOpen,
  (open) => {
    if (!open) return
    selectedFormat.value = props.defaultFormat
    selectedFields.value = [...props.defaultFields]
    includeTableOfContents.value = props.defaultIncludeTableOfContents
  },
)

const exportFieldOptions: Array<{ key: string; label: string }> = [
  { key: 'date', label: t('lessons.date') },
  { key: 'hebrew_year', label: t('lessons.hebrewYear') },
  { key: 'duration', label: t('lessons.duration') },
  { key: 'course_name', label: t('lessons.course') },
  { key: 'themes', label: t('lessons.themes') },
  { key: 'brief', label: t('lessons.brief') },
  { key: 'summary', label: t('lessons.summary') },
  { key: 'edited_version', label: t('lessons.editedTranscript') },
]

const exportFormatOptions: Array<{ value: ExportFormat; label: string }> = [
  { value: 'docx', label: 'WORD' },
  { value: 'pdf', label: 'PDF' },
  { value: 'md', label: 'MARKDOWN' },
]

const onConfirm = () => {
  emit('export', {
    format: selectedFormat.value,
    includeFields: [...selectedFields.value],
    includeTableOfContents: includeTableOfContents.value,
  })
}
</script>

<template>
  <Dialog :open="isOpen" @close="emit('close')" class="relative z-50">
    <div class="fixed inset-0 bg-black/30" aria-hidden="true" />
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="w-full max-w-xl rounded-lg bg-white dark:bg-gray-800 p-6 shadow-xl">
        <DialogTitle class="mb-3 text-lg font-semibold text-gray-900 dark:text-white">
          {{ t('booklets.exportModalTitle') }}
        </DialogTitle>

        <div class="space-y-5">
          <div>
            <p class="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
              {{ t('lessons.exportFormatLabel') }}
            </p>
            <div class="flex gap-2">
              <button
                v-for="formatOption in exportFormatOptions"
                :key="formatOption.value"
                type="button"
                @click="selectedFormat = formatOption.value"
                :class="[
                  'px-3 py-1.5 text-sm rounded-md border transition-colors',
                  selectedFormat === formatOption.value
                    ? 'border-indigo-600 bg-indigo-50 text-indigo-700 dark:border-indigo-400 dark:bg-indigo-900/40 dark:text-indigo-200'
                    : 'border-gray-300 text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700'
                ]"
              >
                {{ formatOption.label }}
              </button>
            </div>
          </div>

          <div>
            <label
              class="inline-flex items-center gap-2 rounded border border-gray-200 dark:border-gray-700 px-3 py-2 text-sm text-gray-700 dark:text-gray-300"
            >
              <input
                v-model="includeTableOfContents"
                type="checkbox"
                class="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              />
              {{ t('booklets.includeTableOfContents') }}
            </label>
          </div>

          <div>
            <p class="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
              {{ t('lessons.exportFieldsLabel') }}
            </p>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <label
                v-for="field in exportFieldOptions"
                :key="field.key"
                class="inline-flex items-center gap-2 rounded border border-gray-200 dark:border-gray-700 px-3 py-2 text-sm text-gray-700 dark:text-gray-300"
              >
                <input
                  v-model="selectedFields"
                  type="checkbox"
                  :value="field.key"
                  class="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                />
                {{ field.label }}
              </label>
            </div>
          </div>
        </div>

        <div class="mt-6 flex justify-end gap-2">
          <button
            @click="emit('close')"
            :disabled="submitting"
            class="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700 disabled:opacity-50"
          >
            {{ t('lessons.cancel') }}
          </button>
          <button
            @click="onConfirm"
            :disabled="submitting"
            class="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {{ submitting ? t('lessons.exporting') : t('lessons.exportAction') }}
          </button>
        </div>
      </DialogPanel>
    </div>
  </Dialog>
</template>

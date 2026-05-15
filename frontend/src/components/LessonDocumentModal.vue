<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'

type ModalMode = 'export' | 'import'
type ViewType = 'summary' | 'edited' | 'transcript'
type ExportFormat = 'md' | 'docx' | 'pdf'

const props = withDefaults(
  defineProps<{
    isOpen: boolean
    mode: ModalMode
    viewType: ViewType
    submitting?: boolean
    defaultFormat?: ExportFormat
    defaultFields?: string[]
  }>(),
  {
    submitting: false,
    defaultFormat: 'pdf',
    defaultFields: () => [],
  },
)

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'export', payload: { format: ExportFormat; includeFields: string[] }): void
  (e: 'import', payload: { file: File | null }): void
}>()

const { t } = useI18n()

const selectedFormat = ref<ExportFormat>(props.defaultFormat)
const selectedFields = ref<string[]>([...props.defaultFields])
const selectedFile = ref<File | null>(null)

watch(
  () => props.isOpen,
  (open) => {
    if (!open) return
    selectedFormat.value = props.defaultFormat
    selectedFields.value = [...props.defaultFields]
    selectedFile.value = null
  },
)

const exportFieldOptions = computed(() => [
  { key: 'title', label: t('lessons.lessonTitle') },
  { key: 'date', label: t('lessons.date') },
  { key: 'duration', label: t('lessons.duration') },
  { key: 'course_name', label: t('lessons.course') },
  { key: 'themes', label: t('lessons.themes') },
  { key: 'brief', label: t('lessons.brief') },
])

const exportFormatOptions: Array<{ value: ExportFormat; label: string }> = [
  { value: 'docx', label: 'WORD' },
  { value: 'pdf', label: 'PDF' },
  { value: 'md', label: 'MARKDOWN' },
]

const viewLabel = computed(() => {
  if (props.viewType === 'summary') return t('lessons.summary')
  if (props.viewType === 'edited') return t('lessons.editedTranscript')
  return t('lessons.transcript')
})

const canExport = computed(() => !props.submitting)
const canImport = computed(() => !props.submitting && !!selectedFile.value)

const onFileSelected = (event: Event) => {
  const target = event.target as HTMLInputElement
  selectedFile.value = target.files?.[0] ?? null
}

const onConfirm = () => {
  if (props.mode === 'export') {
    emit('export', { format: selectedFormat.value, includeFields: [...selectedFields.value] })
    return
  }
  emit('import', { file: selectedFile.value })
}
</script>

<template>
  <Dialog :open="isOpen" @close="emit('close')" class="relative z-50">
    <div class="fixed inset-0 bg-black/30" aria-hidden="true" />
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="w-full max-w-xl rounded-lg bg-white dark:bg-gray-800 p-6 shadow-xl">
        <DialogTitle class="mb-3 text-lg font-semibold text-gray-900 dark:text-white">
          {{ mode === 'export' ? t('lessons.exportModalTitle', { tab: viewLabel }) : t('lessons.importModalTitle', { tab: viewLabel }) }}
        </DialogTitle>

        <div v-if="mode === 'export'" class="space-y-5">
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

        <div v-else class="space-y-4">
          <p class="text-sm text-gray-600 dark:text-gray-400">
            {{ t('lessons.importFileHelp') }}
          </p>
          <input
            type="file"
            accept=".md,.docx"
            class="block w-full text-sm text-gray-700 dark:text-gray-300
                   file:mr-4 file:rounded-md file:border-0
                   file:bg-indigo-50 file:px-3 file:py-2
                   file:text-sm file:font-semibold file:text-indigo-700
                   hover:file:bg-indigo-100 dark:file:bg-indigo-900/30 dark:file:text-indigo-200"
            @change="onFileSelected"
          />
          <p v-if="selectedFile" class="text-xs text-gray-500 dark:text-gray-400">
            {{ selectedFile.name }}
          </p>
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
            :disabled="mode === 'export' ? !canExport : !canImport"
            class="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {{
              mode === 'export'
                ? (submitting ? t('lessons.exporting') : t('lessons.exportAction'))
                : (submitting ? t('lessons.importing') : t('lessons.importAction'))
            }}
          </button>
        </div>
      </DialogPanel>
    </div>
  </Dialog>
</template>


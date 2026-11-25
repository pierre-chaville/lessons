<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  ExclamationTriangleIcon,
  MagnifyingGlassIcon,
  PencilIcon,
  SparklesIcon,
  TrashIcon,
  XMarkIcon,
} from '@heroicons/vue/24/outline'
import { isAxiosError } from 'axios'
import { useI18n } from 'vue-i18n'

import { glossaryApi } from '@/api/glossary'
import { GLOSSARY_STATUSES, GLOSSARY_TYPES } from '@/api/types'
import type {
  GlossaryCompletionStatus,
  GlossaryEntry,
  GlossaryEntryCreate,
  GlossaryStatus,
  GlossaryType,
} from '@/api/types'
import GlossaryEntryFormDialog from '@/components/glossary/GlossaryEntryFormDialog.vue'
import { usePermissions } from '@/composables/usePermissions'
import { useToast } from '@/composables/useToast'

const PER_PAGE = 50
const SEARCH_DEBOUNCE_MS = 300
const COMPLETION_POLL_MS = 3000

const { t } = useI18n()
const { can } = usePermissions()
const toast = useToast()

const entries = ref<GlossaryEntry[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(true)
const isSaving = ref(false)
const isDeleting = ref(false)

const searchInput = ref('')
const search = ref('')
const typeFilter = ref<GlossaryType | ''>('')
const statusFilter = ref<GlossaryStatus | ''>('')
let searchTimeout: ReturnType<typeof setTimeout> | null = null

const showFormModal = ref(false)
const showDeleteModal = ref(false)
const editingEntry = ref<GlossaryEntry | null>(null)
const deletingEntry = ref<GlossaryEntry | null>(null)
const importInputRef = ref<HTMLInputElement | null>(null)

const showCompleteModal = ref(false)
const isLaunchingCompletion = ref(false)
const completionPendingCount = ref(0)
const completionTaskId = ref<number | null>(null)
const completionTaskStatus = ref<string | null>(null)
let completionPollTimer: ReturnType<typeof setTimeout> | null = null

const isCompletionRunning = computed(
  () => completionTaskStatus.value === 'pending' || completionTaskStatus.value === 'running',
)
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PER_PAGE)))
const canEditEntries = computed(() => can('glossary', 'update') || can('glossary', 'delete'))

const STATUS_BADGE_CLASSES: Record<GlossaryStatus, string> = {
  validated: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  auto: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
  rejected: 'border-red-200 bg-red-50 text-red-700 dark:border-red-700 dark:bg-red-900/30 dark:text-red-300',
}

const loadEntries = async () => {
  try {
    loading.value = true
    const result = await glossaryApi.list({
      q: search.value || undefined,
      type: typeFilter.value || undefined,
      status: statusFilter.value || undefined,
      page: page.value,
      per_page: PER_PAGE,
    })
    entries.value = result.items
    total.value = result.total
  } catch {
    toast.error(t('glossary.fetchFailed'))
  } finally {
    loading.value = false
  }
}

const goToPage = (target: number) => {
  page.value = Math.min(Math.max(1, target), pageCount.value)
}

const openCreateModal = () => {
  editingEntry.value = null
  showFormModal.value = true
}

const openEditModal = (entry: GlossaryEntry) => {
  editingEntry.value = entry
  showFormModal.value = true
}

const closeFormModal = () => {
  showFormModal.value = false
}

const openDeleteModal = (entry: GlossaryEntry) => {
  deletingEntry.value = entry
  showDeleteModal.value = true
}

const closeDeleteModal = () => {
  deletingEntry.value = null
  showDeleteModal.value = false
}

const saveEntry = async (payload: GlossaryEntryCreate) => {
  const editing = editingEntry.value
  try {
    isSaving.value = true
    if (editing) {
      await glossaryApi.update(editing.hashid, payload)
    } else {
      await glossaryApi.create(payload)
    }
    await loadEntries()
    closeFormModal()
  } catch (error) {
    if (isAxiosError(error) && error.response?.status === 409) {
      toast.error(t('glossary.duplicate', { hebrew: payload.hebrew }))
    } else {
      toast.error(editing ? t('glossary.updateFailed') : t('glossary.createFailed'))
    }
  } finally {
    isSaving.value = false
  }
}

const deleteEntry = async () => {
  if (!deletingEntry.value) return
  try {
    isDeleting.value = true
    await glossaryApi.delete(deletingEntry.value.hashid)
    await loadEntries()
    closeDeleteModal()
  } catch {
    toast.error(t('glossary.deleteFailed'))
  } finally {
    isDeleting.value = false
  }
}

const downloadBlob = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

const exportYaml = async () => {
  try {
    downloadBlob(await glossaryApi.exportYaml(), 'glossary.yaml')
    toast.success(t('glossary.exportSuccess'))
  } catch {
    toast.error(t('glossary.exportFailed'))
  }
}

const exportLegacyYaml = async () => {
  try {
    downloadBlob(await glossaryApi.exportLegacyYaml(), 'glossary_legacy.yaml')
    toast.success(t('glossary.exportSuccess'))
  } catch {
    toast.error(t('glossary.exportFailed'))
  }
}

const openImportDialog = () => {
  importInputRef.value?.click()
}

const importYaml = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const result = await glossaryApi.importYaml(file)
    await loadEntries()
    toast.success(t('glossary.importSuccess', { created: result.created, updated: result.updated }))
  } catch {
    toast.error(t('glossary.importFailed'))
  } finally {
    input.value = ''
  }
}

const stopCompletionPolling = () => {
  if (completionPollTimer) clearTimeout(completionPollTimer)
  completionPollTimer = null
}

const scheduleCompletionPoll = () => {
  stopCompletionPolling()
  completionPollTimer = setTimeout(refreshCompletionStatus, COMPLETION_POLL_MS)
}

/** Report the end of a task this page saw running, then refresh the list. */
const reportFinishedCompletion = async (status: GlossaryCompletionStatus) => {
  await loadEntries()
  if (status.task_status === 'completed') {
    const completed = Number(status.task_result?.completed ?? 0)
    toast.success(t('glossary.completeDone', { count: completed }))
  } else if (status.task_status === 'failed') {
    toast.error(t('glossary.completeTaskFailed'))
  }
}

async function refreshCompletionStatus() {
  try {
    const status = await glossaryApi.completionStatus()
    const wasRunning = isCompletionRunning.value
    const watchedTaskId = completionTaskId.value
    completionTaskId.value = status.task_id
    completionTaskStatus.value = status.task_status
    if (wasRunning && !isCompletionRunning.value && watchedTaskId === status.task_id) {
      await reportFinishedCompletion(status)
    }
    return status
  } catch {
    return null
  } finally {
    if (isCompletionRunning.value) scheduleCompletionPoll()
    else stopCompletionPolling()
  }
}

const completeWithLlm = async () => {
  const status = await refreshCompletionStatus()
  if (!status) {
    toast.error(t('glossary.completeFailed'))
    return
  }
  if (isCompletionRunning.value) {
    toast.success(t('glossary.completeAlreadyRunning'))
  } else if (status.pending_entries === 0) {
    toast.success(t('glossary.completeNothing'))
  } else {
    completionPendingCount.value = status.pending_entries
    showCompleteModal.value = true
  }
}

const closeCompleteModal = () => {
  showCompleteModal.value = false
}

const confirmCompleteWithLlm = async () => {
  try {
    isLaunchingCompletion.value = true
    const result = await glossaryApi.complete()
    closeCompleteModal()
    if (result.task_id === null) {
      toast.success(t('glossary.completeNothing'))
      return
    }
    completionTaskId.value = result.task_id
    completionTaskStatus.value = 'pending'
    scheduleCompletionPoll()
  } catch {
    toast.error(t('glossary.completeFailed'))
  } finally {
    isLaunchingCompletion.value = false
  }
}

watch(searchInput, (value) => {
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    search.value = value.trim()
  }, SEARCH_DEBOUNCE_MS)
})

// A filter change restarts from page 1; any page/filter change reloads.
watch([search, typeFilter, statusFilter], () => {
  if (page.value !== 1) page.value = 1
  else loadEntries()
})
watch(page, loadEntries)

onMounted(() => {
  loadEntries()
  // Shows the banner if a completion is already running (e.g. queued by a native correction).
  if (can('glossary', 'update')) refreshCompletionStatus()
})

onBeforeUnmount(() => {
  if (searchTimeout) clearTimeout(searchTimeout)
  stopCompletionPolling()
})

defineExpose({
  openCreateModal,
  exportYaml,
  exportLegacyYaml,
  openImportDialog,
  completeWithLlm,
  isCompletionRunning,
})
</script>

<template>
  <input
    ref="importInputRef"
    type="file"
    accept=".yaml,.yml,text/yaml,application/x-yaml"
    class="hidden"
    @change="importYaml"
  />

  <GlossaryEntryFormDialog
    :open="showFormModal"
    :entry="editingEntry"
    :saving="isSaving"
    @close="closeFormModal"
    @submit="saveEntry"
  />

  <Dialog :open="showDeleteModal" class="relative z-50" @close="closeDeleteModal">
    <div class="fixed inset-0 bg-black/30" aria-hidden="true" />
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="mx-auto w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-gray-800">
        <div class="mb-4 flex items-center gap-3">
          <ExclamationTriangleIcon class="h-6 w-6 text-red-600 dark:text-red-400" />
          <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white">
            {{ t('glossary.deleteTitle') }}
          </DialogTitle>
        </div>
        <p class="mb-6 text-sm text-gray-600 dark:text-gray-300">
          {{ t('glossary.deleteConfirm', { hebrew: deletingEntry?.hebrew || '' }) }}
        </p>
        <div class="flex justify-end gap-2">
          <button class="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 dark:border-gray-600 dark:text-gray-300" @click="closeDeleteModal">
            <XMarkIcon class="mr-1 inline h-4 w-4" />
            {{ t('lessons.cancel') }}
          </button>
          <button class="inline-flex items-center gap-2 rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50" :disabled="isDeleting" @click="deleteEntry">
            <TrashIcon class="h-4 w-4" />
            {{ isDeleting ? t('glossary.deleting') : t('glossary.delete') }}
          </button>
        </div>
      </DialogPanel>
    </div>
  </Dialog>

  <Dialog :open="showCompleteModal" class="relative z-50" @close="closeCompleteModal">
    <div class="fixed inset-0 bg-black/30" aria-hidden="true" />
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="mx-auto w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-gray-800">
        <div class="mb-4 flex items-center gap-3">
          <SparklesIcon class="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
          <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white">
            {{ t('glossary.completeConfirmTitle') }}
          </DialogTitle>
        </div>
        <p class="mb-6 text-sm text-gray-600 dark:text-gray-300">
          {{ t('glossary.completeConfirm', { count: completionPendingCount }, completionPendingCount) }}
        </p>
        <div class="flex justify-end gap-2">
          <button class="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 dark:border-gray-600 dark:text-gray-300" @click="closeCompleteModal">
            <XMarkIcon class="mr-1 inline h-4 w-4" />
            {{ t('lessons.cancel') }}
          </button>
          <button
            class="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
            :disabled="isLaunchingCompletion"
            @click="confirmCompleteWithLlm"
          >
            <SparklesIcon class="h-4 w-4" />
            {{ t('glossary.completeConfirmAction') }}
          </button>
        </div>
      </DialogPanel>
    </div>
  </Dialog>

  <div class="w-full">
    <div
      v-if="isCompletionRunning"
      class="mb-6 flex items-center gap-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 dark:border-amber-700 dark:bg-amber-900/20"
    >
      <svg class="h-5 w-5 animate-spin text-amber-600 dark:text-amber-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
      </svg>
      <div>
        <span class="font-medium text-amber-800 dark:text-amber-300">
          {{ t('glossary.completionRunning') }}
        </span>
        <span class="ml-2 text-sm text-amber-700 dark:text-amber-400">
          — {{ t('glossary.completionRunningMessage') }}
        </span>
      </div>
    </div>

    <div class="mb-6 flex flex-wrap items-center gap-3 rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800">
      <div class="relative min-w-[14rem] flex-1">
        <MagnifyingGlassIcon class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
        <input
          v-model="searchInput"
          type="search"
          dir="auto"
          :placeholder="t('glossary.searchPlaceholder')"
          :aria-label="t('glossary.searchPlaceholder')"
          class="w-full rounded-md border border-gray-300 bg-white py-2 pl-9 pr-3 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
        />
      </div>
      <select
        v-model="typeFilter"
        :aria-label="t('glossary.fields.type')"
        class="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
      >
        <option value="">{{ t('glossary.allTypes') }}</option>
        <option v-for="value in GLOSSARY_TYPES" :key="value" :value="value">{{ t(`glossary.types.${value}`) }}</option>
      </select>
      <select
        v-model="statusFilter"
        :aria-label="t('glossary.fields.status')"
        class="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
      >
        <option value="">{{ t('glossary.allStatuses') }}</option>
        <option v-for="value in GLOSSARY_STATUSES" :key="value" :value="value">{{ t(`glossary.statuses.${value}`) }}</option>
      </select>
      <span class="text-sm font-medium text-gray-700 dark:text-gray-300">
        {{ t('glossary.entriesCount', { count: total }) }}
      </span>
    </div>

    <div v-if="loading" class="rounded-lg bg-white p-8 text-center text-gray-500 shadow-sm dark:bg-gray-800 dark:text-gray-400">
      {{ t('glossary.loading') }}
    </div>

    <div v-else-if="entries.length === 0" class="rounded-lg bg-white p-8 text-center text-gray-500 shadow-sm dark:bg-gray-800 dark:text-gray-400">
      {{ search || typeFilter || statusFilter ? t('glossary.noMatch') : t('glossary.empty') }}
    </div>

    <template v-else>
      <div class="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800">
        <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead class="bg-gray-50 dark:bg-gray-900">
            <tr>
              <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{{ t('glossary.fields.hebrew') }}</th>
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{{ t('glossary.fields.translit') }}</th>
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{{ t('glossary.fields.translation') }}</th>
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{{ t('glossary.fields.type') }}</th>
              <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{{ t('glossary.fields.status') }}</th>
              <th v-if="canEditEntries" class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{{ t('glossary.actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
            <tr v-for="entry in entries" :key="entry.hashid" class="align-top">
              <td class="whitespace-nowrap px-4 py-3 text-right text-lg text-gray-900 dark:text-gray-100" dir="rtl" lang="he">
                {{ entry.hebrew }}
              </td>
              <td class="px-4 py-3 text-sm">
                <div class="font-medium text-gray-900 dark:text-gray-100">
                  {{ entry.translit || '—' }}
                </div>
                <div v-if="entry.aliases.length" class="mt-1 flex flex-wrap gap-1">
                  <span
                    v-for="alias in entry.aliases"
                    :key="`${entry.hashid}-${alias}`"
                    class="inline-flex items-center rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-700 dark:border-slate-600 dark:bg-slate-700/60 dark:text-slate-200"
                  >
                    {{ alias }}
                  </span>
                </div>
              </td>
              <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                {{ entry.translation || '—' }}
                <div v-if="entry.sefaria_ref || entry.sefaria_title" class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  {{ entry.sefaria_ref || entry.sefaria_title }}
                </div>
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                {{ t(`glossary.types.${entry.type}`) }}
              </td>
              <td class="whitespace-nowrap px-4 py-3 text-sm">
                <span :class="STATUS_BADGE_CLASSES[entry.status]" class="inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium">
                  {{ t(`glossary.statuses.${entry.status}`) }}
                </span>
                <div class="mt-1 text-xs text-gray-500 dark:text-gray-400">{{ t(`glossary.sources.${entry.source}`) }}</div>
              </td>
              <td v-if="canEditEntries" class="whitespace-nowrap px-4 py-3 text-right">
                <div class="inline-flex items-center gap-2">
                  <button
                    v-if="can('glossary', 'update')"
                    class="inline-flex items-center gap-1 rounded-md bg-gray-100 px-2.5 py-1.5 text-xs text-gray-700 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
                    @click="openEditModal(entry)"
                  >
                    <PencilIcon class="h-3.5 w-3.5" />
                    {{ t('glossary.edit') }}
                  </button>
                  <button
                    v-if="can('glossary', 'delete')"
                    class="inline-flex items-center gap-1 rounded-md bg-red-50 px-2.5 py-1.5 text-xs text-red-700 hover:bg-red-100 dark:bg-red-900/30 dark:text-red-300 dark:hover:bg-red-900/40"
                    @click="openDeleteModal(entry)"
                  >
                    <TrashIcon class="h-3.5 w-3.5" />
                    {{ t('glossary.delete') }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="pageCount > 1" class="mt-4 flex items-center justify-end gap-3 text-sm text-gray-700 dark:text-gray-300">
        <button
          class="inline-flex items-center rounded-md border border-gray-300 p-1.5 disabled:opacity-40 dark:border-gray-600"
          :disabled="page <= 1"
          :aria-label="t('glossary.previousPage')"
          @click="goToPage(page - 1)"
        >
          <ChevronLeftIcon class="h-4 w-4" />
        </button>
        <span>{{ t('glossary.pageOf', { page, total: pageCount }) }}</span>
        <button
          class="inline-flex items-center rounded-md border border-gray-300 p-1.5 disabled:opacity-40 dark:border-gray-600"
          :disabled="page >= pageCount"
          :aria-label="t('glossary.nextPage')"
          @click="goToPage(page + 1)"
        >
          <ChevronRightIcon class="h-4 w-4" />
        </button>
      </div>
    </template>
  </div>
</template>

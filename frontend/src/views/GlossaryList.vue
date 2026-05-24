<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'
import {
  PlusIcon,
  PencilIcon,
  TrashIcon,
  CheckIcon,
  XMarkIcon,
  ExclamationTriangleIcon,
} from '@heroicons/vue/24/outline'
import { useI18n } from 'vue-i18n'

import { glossaryApi } from '@/api/glossary'
import type { GlossaryEntry } from '@/api/types'
import { usePermissions } from '@/composables/usePermissions'
import { useToast } from '@/composables/useToast'

const { t } = useI18n()
const { can } = usePermissions()
const toast = useToast()

const entries = ref<GlossaryEntry[]>([])
const loading = ref(true)
const isSaving = ref(false)
const isDeleting = ref(false)

const showCreateModal = ref(false)
const showEditModal = ref(false)
const showDeleteModal = ref(false)
const importInputRef = ref<HTMLInputElement | null>(null)

const editingEntry = ref<GlossaryEntry | null>(null)
const deletingEntry = ref<GlossaryEntry | null>(null)
const formData = ref({
  standard: '',
  variationsInput: '',
  exact_case: false,
})

const parseVariations = (input: string): string[] => {
  const raw = input
    .split(/\r?\n|,/)
    .map((v) => v.trim())
    .filter(Boolean)
  return [...new Set(raw)]
}

const setFormFromEntry = (entry: GlossaryEntry | null) => {
  formData.value = {
    standard: entry?.standard ?? '',
    variationsInput: (entry?.variations ?? []).join(', '),
    exact_case: entry?.exact_case ?? false,
  }
}

const loadEntries = async () => {
  try {
    loading.value = true
    entries.value = await glossaryApi.list()
  } catch {
    toast.error(t('glossary.fetchFailed'))
  } finally {
    loading.value = false
  }
}

const openCreateModal = () => {
  setFormFromEntry(null)
  showCreateModal.value = true
}

const closeCreateModal = () => {
  showCreateModal.value = false
  setFormFromEntry(null)
}

const openEditModal = (entry: GlossaryEntry) => {
  editingEntry.value = entry
  setFormFromEntry(entry)
  showEditModal.value = true
}

const closeEditModal = () => {
  showEditModal.value = false
  editingEntry.value = null
  setFormFromEntry(null)
}

const openDeleteModal = (entry: GlossaryEntry) => {
  deletingEntry.value = entry
  showDeleteModal.value = true
}

const closeDeleteModal = () => {
  deletingEntry.value = null
  showDeleteModal.value = false
}

const createEntry = async () => {
  const standard = formData.value.standard.trim()
  if (!standard) {
    toast.error(t('glossary.standardRequired'))
    return
  }
  try {
    isSaving.value = true
    await glossaryApi.create({
      standard,
      variations: parseVariations(formData.value.variationsInput),
      exact_case: formData.value.exact_case,
    })
    await loadEntries()
    closeCreateModal()
  } catch {
    toast.error(t('glossary.createFailed'))
  } finally {
    isSaving.value = false
  }
}

const updateEntry = async () => {
  if (!editingEntry.value) return
  const standard = formData.value.standard.trim()
  if (!standard) {
    toast.error(t('glossary.standardRequired'))
    return
  }
  try {
    isSaving.value = true
    await glossaryApi.update(editingEntry.value.hashid, {
      standard,
      variations: parseVariations(formData.value.variationsInput),
      exact_case: formData.value.exact_case,
    })
    await loadEntries()
    closeEditModal()
  } catch {
    toast.error(t('glossary.updateFailed'))
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

const exportYaml = async () => {
  try {
    const blob = await glossaryApi.exportYaml()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'glossary.yaml'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
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
    toast.success(t('glossary.importSuccess', { count: result.total }))
  } catch {
    toast.error(t('glossary.importFailed'))
  } finally {
    input.value = ''
  }
}

onMounted(loadEntries)

defineExpose({ openCreateModal, exportYaml, openImportDialog })
</script>

<template>
  <input
    ref="importInputRef"
    type="file"
    accept=".yaml,.yml,text/yaml,application/x-yaml"
    class="hidden"
    @change="importYaml"
  />

  <Dialog :open="showCreateModal" @close="closeCreateModal" class="relative z-50">
    <div class="fixed inset-0 bg-black/30" aria-hidden="true" />
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="mx-auto w-full max-w-lg rounded-lg bg-white p-6 shadow-xl dark:bg-gray-800">
        <DialogTitle class="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
          {{ t('glossary.createTitle') }}
        </DialogTitle>
        <div class="space-y-4">
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">{{ t('glossary.standard') }} *</label>
            <input v-model="formData.standard" class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100" />
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">{{ t('glossary.variations') }}</label>
            <textarea v-model="formData.variationsInput" rows="4" class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100" />
            <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">{{ t('glossary.variationsHint') }}</p>
          </div>
          <label class="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input v-model="formData.exact_case" type="checkbox" class="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-900" />
            {{ t('glossary.exactCase') }}
          </label>
        </div>
        <div class="mt-6 flex justify-end gap-2">
          <button class="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 dark:border-gray-600 dark:text-gray-300" @click="closeCreateModal">
            {{ t('lessons.cancel') }}
          </button>
          <button class="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50" :disabled="isSaving" @click="createEntry">
            <CheckIcon class="h-4 w-4" />
            {{ isSaving ? t('glossary.saving') : t('glossary.create') }}
          </button>
        </div>
      </DialogPanel>
    </div>
  </Dialog>

  <Dialog :open="showEditModal" @close="closeEditModal" class="relative z-50">
    <div class="fixed inset-0 bg-black/30" aria-hidden="true" />
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="mx-auto w-full max-w-lg rounded-lg bg-white p-6 shadow-xl dark:bg-gray-800">
        <DialogTitle class="mb-4 text-lg font-semibold text-gray-900 dark:text-white">
          {{ t('glossary.editTitle') }}
        </DialogTitle>
        <div class="space-y-4">
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">{{ t('glossary.standard') }} *</label>
            <input v-model="formData.standard" class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100" />
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">{{ t('glossary.variations') }}</label>
            <textarea v-model="formData.variationsInput" rows="4" class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100" />
            <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">{{ t('glossary.variationsHint') }}</p>
          </div>
          <label class="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input v-model="formData.exact_case" type="checkbox" class="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-900" />
            {{ t('glossary.exactCase') }}
          </label>
        </div>
        <div class="mt-6 flex justify-end gap-2">
          <button class="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 dark:border-gray-600 dark:text-gray-300" @click="closeEditModal">
            {{ t('lessons.cancel') }}
          </button>
          <button class="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50" :disabled="isSaving" @click="updateEntry">
            <CheckIcon class="h-4 w-4" />
            {{ isSaving ? t('glossary.saving') : t('glossary.save') }}
          </button>
        </div>
      </DialogPanel>
    </div>
  </Dialog>

  <Dialog :open="showDeleteModal" @close="closeDeleteModal" class="relative z-50">
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
          {{ t('glossary.deleteConfirm', { standard: deletingEntry?.standard || '' }) }}
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

  <div class="w-full">
    <div class="mb-6 rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800">
      <span class="text-sm font-medium text-gray-700 dark:text-gray-300">
        {{ t('glossary.entriesCount', { count: entries.length }) }}
      </span>
    </div>

    <div v-if="loading" class="rounded-lg bg-white p-8 text-center text-gray-500 shadow-sm dark:bg-gray-800 dark:text-gray-400">
      {{ t('glossary.loading') }}
    </div>

    <div v-else-if="entries.length === 0" class="rounded-lg bg-white p-8 text-center text-gray-500 shadow-sm dark:bg-gray-800 dark:text-gray-400">
      {{ t('glossary.empty') }}
    </div>

    <div v-else class="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
        <thead class="bg-gray-50 dark:bg-gray-900">
          <tr>
            <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{{ t('glossary.standard') }}</th>
            <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{{ t('glossary.variations') }}</th>
            <th class="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{{ t('glossary.exactCase') }}</th>
            <th class="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">{{ t('glossary.actions') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
          <tr v-for="entry in entries" :key="entry.hashid">
            <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">{{ entry.standard }}</td>
            <td class="px-4 py-3">
              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="variation in entry.variations"
                  :key="`${entry.hashid}-${variation}`"
                  class="inline-flex items-center rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs text-slate-700 dark:border-slate-600 dark:bg-slate-700/60 dark:text-slate-200"
                >
                  {{ variation }}
                </span>
                <span v-if="entry.variations.length === 0" class="text-xs italic text-gray-500 dark:text-gray-400">
                  {{ t('glossary.noVariations') }}
                </span>
              </div>
            </td>
            <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
              <span
                :class="entry.exact_case
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300'
                  : 'border-gray-200 bg-gray-50 text-gray-700 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-300'"
                class="inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium"
              >
                {{ entry.exact_case ? t('glossary.exactCaseYes') : t('glossary.exactCaseNo') }}
              </span>
            </td>
            <td class="px-4 py-3 text-right">
              <div class="inline-flex items-center gap-2" v-if="can('glossary', 'update') || can('glossary', 'delete')">
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  CpuChipIcon,
  PencilIcon,
  TrashIcon,
  CheckIcon,
  ExclamationTriangleIcon,
} from '@heroicons/vue/24/outline'
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'
import { modelPresetsApi } from '@/api/modelPresets'
import { useToast } from '@/composables/useToast'
import { usePermissions } from '@/composables/usePermissions'
import type { ModelPreset } from '@/api/types'

const { t } = useI18n()
const toast = useToast()
const { can } = usePermissions()

const presets = ref<ModelPreset[]>([])
const loading = ref(true)
const isSaving = ref(false)
const isDeleting = ref(false)

const showEditModal = ref(false)
const showDeleteConfirm = ref(false)
const editingPreset = ref<ModelPreset | null>(null)
const deletingPreset = ref<ModelPreset | null>(null)

const formData = ref({
  name: '',
  provider: '',
  model_id: '',
  temperature: 0.7,
  cost_input_per_m_tokens: 0,
  cost_output_per_m_tokens: 0,
  thinking_mode_text: '{}',
})

const parseThinkingMode = () => {
  const raw = formData.value.thinking_mode_text.trim()
  if (!raw) return {}
  const parsed = JSON.parse(raw)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('thinking_mode must be a JSON object')
  }
  return parsed as Record<string, unknown>
}

const fetchPresets = async () => {
  try {
    loading.value = true
    presets.value = await modelPresetsApi.list()
  } catch {
    toast.error(t('modelPresets.fetchFailed'))
  } finally {
    loading.value = false
  }
}

const openCreateModal = () => {
  editingPreset.value = null
  formData.value = {
    name: '',
    provider: 'openrouter',
    model_id: '',
    temperature: 0.7,
    cost_input_per_m_tokens: 0,
    cost_output_per_m_tokens: 0,
    thinking_mode_text: '{}',
  }
  showEditModal.value = true
}

const openEditModal = (preset: ModelPreset) => {
  editingPreset.value = preset
  formData.value = {
    name: preset.name,
    provider: preset.provider,
    model_id: preset.model_id,
    temperature: preset.temperature,
    cost_input_per_m_tokens: preset.cost_input_per_m_tokens ?? 0,
    cost_output_per_m_tokens: preset.cost_output_per_m_tokens ?? 0,
    thinking_mode_text: JSON.stringify(preset.thinking_mode ?? {}, null, 2),
  }
  showEditModal.value = true
}

const closeEditModal = () => {
  showEditModal.value = false
  editingPreset.value = null
}

const submitForm = async () => {
  if (!formData.value.name.trim() || !formData.value.provider.trim() || !formData.value.model_id.trim()) {
    toast.error(t('modelPresets.requiredFields'))
    return
  }

  let thinkingMode: Record<string, unknown>
  try {
    thinkingMode = parseThinkingMode()
  } catch {
    toast.error(t('modelPresets.invalidThinkingMode'))
    return
  }

  try {
    isSaving.value = true
    if (editingPreset.value) {
      await modelPresetsApi.update(editingPreset.value.id, {
        name: formData.value.name.trim(),
        provider: formData.value.provider.trim(),
        model_id: formData.value.model_id.trim(),
        temperature: formData.value.temperature,
        cost_input_per_m_tokens: formData.value.cost_input_per_m_tokens,
        cost_output_per_m_tokens: formData.value.cost_output_per_m_tokens,
        thinking_mode: thinkingMode,
      })
      toast.success(t('modelPresets.updateSuccess'))
    } else {
      await modelPresetsApi.create({
        name: formData.value.name.trim(),
        provider: formData.value.provider.trim(),
        model_id: formData.value.model_id.trim(),
        temperature: formData.value.temperature,
        cost_input_per_m_tokens: formData.value.cost_input_per_m_tokens,
        cost_output_per_m_tokens: formData.value.cost_output_per_m_tokens,
        thinking_mode: thinkingMode,
      })
      toast.success(t('modelPresets.createSuccess'))
    }
    await fetchPresets()
    closeEditModal()
  } catch {
    toast.error(editingPreset.value ? t('modelPresets.updateFailed') : t('modelPresets.createFailed'))
  } finally {
    isSaving.value = false
  }
}

const confirmDelete = (preset: ModelPreset) => {
  deletingPreset.value = preset
  showDeleteConfirm.value = true
}

const cancelDelete = () => {
  showDeleteConfirm.value = false
  deletingPreset.value = null
}

const deletePreset = async () => {
  if (!deletingPreset.value) return
  try {
    isDeleting.value = true
    await modelPresetsApi.delete(deletingPreset.value.id)
    toast.success(t('modelPresets.deleteSuccess'))
    await fetchPresets()
    cancelDelete()
  } catch {
    toast.error(t('modelPresets.deleteFailed'))
  } finally {
    isDeleting.value = false
  }
}

onMounted(fetchPresets)

defineExpose({ openCreateModal })
</script>

<template>
  <Dialog :open="showEditModal" @close="closeEditModal" class="relative z-50">
    <div class="fixed inset-0 bg-black/30 backdrop-blur-sm" aria-hidden="true" />
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="mx-auto max-w-2xl w-full bg-white dark:bg-gray-800 rounded-lg shadow-xl">
        <div class="p-6">
          <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            {{ editingPreset ? t('modelPresets.editTitle') : t('modelPresets.createTitle') }}
          </DialogTitle>
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {{ t('modelPresets.fields.name') }} *
              </label>
              <input
                v-model="formData.name"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                :placeholder="t('modelPresets.placeholders.name')"
              />
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {{ t('modelPresets.fields.provider') }} *
                </label>
                <input
                  v-model="formData.provider"
                  type="text"
                  class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                  :placeholder="t('modelPresets.placeholders.provider')"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {{ t('modelPresets.fields.temperature') }}
                </label>
                <input
                  v-model.number="formData.temperature"
                  type="number"
                  min="0"
                  max="2"
                  step="0.1"
                  class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                />
              </div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {{ t('modelPresets.fields.costInputPerMTokens') }}
                </label>
                <input
                  v-model.number="formData.cost_input_per_m_tokens"
                  type="number"
                  min="0"
                  step="0.000001"
                  class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                />
              </div>
              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {{ t('modelPresets.fields.costOutputPerMTokens') }}
                </label>
                <input
                  v-model.number="formData.cost_output_per_m_tokens"
                  type="number"
                  min="0"
                  step="0.000001"
                  class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                />
              </div>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {{ t('modelPresets.fields.modelId') }} *
              </label>
              <input
                v-model="formData.model_id"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                :placeholder="t('modelPresets.placeholders.modelId')"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {{ t('modelPresets.fields.thinkingMode') }}
              </label>
              <textarea
                v-model="formData.thinking_mode_text"
                rows="6"
                class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent font-mono text-sm"
                :placeholder="t('modelPresets.placeholders.thinkingMode')"
              />
            </div>
          </div>
          <div class="flex justify-end gap-3 mt-6">
            <button
              @click="closeEditModal"
              :disabled="isSaving"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-md transition-colors disabled:opacity-50"
            >
              {{ t('modelPresets.actions.cancel') }}
            </button>
            <button
              @click="submitForm"
              :disabled="isSaving"
              class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-md transition-colors"
            >
              <CheckIcon class="h-4 w-4" />
              {{ isSaving ? t('modelPresets.actions.saving') : t('modelPresets.actions.save') }}
            </button>
          </div>
        </div>
      </DialogPanel>
    </div>
  </Dialog>

  <Dialog :open="showDeleteConfirm" @close="cancelDelete" class="relative z-50">
    <div class="fixed inset-0 bg-black/30 backdrop-blur-sm" aria-hidden="true" />
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="mx-auto max-w-md w-full bg-white dark:bg-gray-800 rounded-lg shadow-xl">
        <div class="p-6">
          <div class="flex items-center gap-4 mb-4">
            <div class="flex-shrink-0 w-12 h-12 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
              <ExclamationTriangleIcon class="h-6 w-6 text-red-600 dark:text-red-400" />
            </div>
            <div>
              <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white">
                {{ t('modelPresets.deleteTitle') }}
              </DialogTitle>
              <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">
                {{ t('modelPresets.deleteMessage') }}
              </p>
            </div>
          </div>
          <p class="text-sm text-gray-700 dark:text-gray-300 mb-6 pl-16">
            <strong>{{ deletingPreset?.name }}</strong>
          </p>
          <div class="flex justify-end gap-3">
            <button
              @click="cancelDelete"
              :disabled="isDeleting"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-md transition-colors disabled:opacity-50"
            >
              {{ t('modelPresets.actions.cancel') }}
            </button>
            <button
              @click="deletePreset"
              :disabled="isDeleting"
              class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 disabled:bg-red-400 rounded-md transition-colors"
            >
              <TrashIcon class="h-4 w-4" />
              {{ isDeleting ? t('modelPresets.actions.deleting') : t('modelPresets.actions.delete') }}
            </button>
          </div>
        </div>
      </DialogPanel>
    </div>
  </Dialog>

  <div class="w-full">
    <div class="mb-6 bg-white dark:bg-gray-800 shadow-sm rounded-lg p-4 transition-colors w-full">
      <div class="flex items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <CpuChipIcon class="h-5 w-5 text-gray-500 dark:text-gray-400" />
          <span class="text-sm font-medium text-gray-700 dark:text-gray-300">
            {{ presets.length }} {{ t('modelPresets.count') }}
          </span>
        </div>
        <span
          v-if="!can('model_presets', 'update')"
          class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400"
        >
          {{ t('modelPresets.readOnly') }}
        </span>
      </div>
    </div>

    <div v-if="loading" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center text-gray-500 dark:text-gray-400 transition-colors">
      {{ t('modelPresets.loading') }}
    </div>

    <div v-else-if="presets.length === 0" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center transition-colors">
      <CpuChipIcon class="h-12 w-12 text-gray-400 dark:text-gray-500 mx-auto mb-4" />
      <p class="text-gray-500 dark:text-gray-400">
        {{ t('modelPresets.empty') }}
      </p>
    </div>

    <div v-else class="bg-white dark:bg-gray-800 shadow-sm rounded-lg overflow-hidden transition-colors">
      <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
        <thead class="bg-gray-50 dark:bg-gray-900">
          <tr>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400">{{ t('modelPresets.fields.name') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400">{{ t('modelPresets.fields.provider') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400">{{ t('modelPresets.fields.modelId') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400">{{ t('modelPresets.fields.temperature') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400">{{ t('modelPresets.fields.costInputPerMTokens') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400">{{ t('modelPresets.fields.costOutputPerMTokens') }}</th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400">{{ t('modelPresets.fields.thinkingMode') }}</th>
            <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400">{{ t('modelPresets.actions.label') }}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
          <tr v-for="preset in presets" :key="preset.id" class="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
            <td class="px-6 py-4 text-sm text-gray-900 dark:text-gray-100 font-medium">{{ preset.name }}</td>
            <td class="px-6 py-4 text-sm text-gray-700 dark:text-gray-300">{{ preset.provider }}</td>
            <td class="px-6 py-4 text-sm text-gray-700 dark:text-gray-300 font-mono">{{ preset.model_id }}</td>
            <td class="px-6 py-4 text-sm text-gray-700 dark:text-gray-300">{{ preset.temperature }}</td>
            <td class="px-6 py-4 text-sm text-gray-700 dark:text-gray-300">{{ preset.cost_input_per_m_tokens }}</td>
            <td class="px-6 py-4 text-sm text-gray-700 dark:text-gray-300">{{ preset.cost_output_per_m_tokens }}</td>
            <td class="px-6 py-4 text-sm text-gray-700 dark:text-gray-300">
              <pre class="text-xs whitespace-pre-wrap break-words max-w-md">{{ JSON.stringify(preset.thinking_mode ?? {}, null, 2) }}</pre>
            </td>
            <td class="px-6 py-4 text-right">
              <div v-if="can('model_presets', 'update')" class="inline-flex items-center gap-2">
                <button
                  @click="openEditModal(preset)"
                  class="p-1.5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-500 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
                  :title="t('modelPresets.actions.edit')"
                >
                  <PencilIcon class="h-4 w-4" />
                </button>
                <button
                  @click="confirmDelete(preset)"
                  class="p-1.5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 transition-colors"
                  :title="t('modelPresets.actions.delete')"
                >
                  <TrashIcon class="h-4 w-4" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { bookletsApi } from '@/api/booklets'
import type { Booklet, BookletTemplateField } from '@/api/types'

const emit = defineEmits<{
  (e: 'open-detail', bookletId: number): void
}>()

const { t } = useI18n()
const templateFieldOptions: BookletTemplateField[] = [
  'title',
  'date',
  'hebrew_year',
  'duration',
  'corrected_transcript',
  'edited_transcript',
  'brief',
  'summary',
  'status',
  'themes',
  'course',
]

const loading = ref(true)
const saving = ref(false)
const showCreateModal = ref(false)
const items = ref<Booklet[]>([])
const total = ref(0)
const form = ref({
  title: '',
  subtitle: '',
  description: '',
  template_data: ['title', 'summary', 'brief'] as BookletTemplateField[],
})
const canSubmit = computed(() => form.value.title.trim().length > 0 && !saving.value)

const fetchBooklets = async () => {
  try {
    loading.value = true
    const result = await bookletsApi.list({ limit: 100, offset: 0 })
    items.value = result.items
    total.value = result.total
  } finally {
    loading.value = false
  }
}

const openCreateModal = () => {
  form.value = {
    title: '',
    subtitle: '',
    description: '',
    template_data: ['title', 'summary', 'brief'],
  }
  showCreateModal.value = true
}

const closeCreateModal = () => {
  if (saving.value) return
  showCreateModal.value = false
}

const submitCreate = async () => {
  if (!canSubmit.value) return
  try {
    saving.value = true
    await bookletsApi.create({
      title: form.value.title.trim(),
      subtitle: form.value.subtitle.trim() || null,
      description: form.value.description.trim() || null,
      template_data: [...form.value.template_data],
    })
    showCreateModal.value = false
    await fetchBooklets()
  } finally {
    saving.value = false
  }
}

const statusClass = (status: string) => {
  if (status === 'ready') return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
  if (status === 'archived') return 'bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
  return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
}

onMounted(fetchBooklets)

defineExpose({ openCreateModal })
</script>

<template>
  <div>
    <div v-if="loading" class="p-8 text-center text-gray-500 dark:text-gray-400">
      {{ t('booklets.loading') }}
    </div>

    <div
      v-else-if="items.length === 0"
      class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center text-gray-500 dark:text-gray-400 transition-colors"
    >
      {{ t('booklets.noBooklets') }}
    </div>

    <div v-else class="space-y-3">
      <div
        v-for="booklet in items"
        :key="booklet.id"
        class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-4 border border-gray-200 dark:border-gray-700 transition-colors"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0 cursor-pointer flex-1" @click="emit('open-detail', booklet.id)">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white truncate">
              {{ booklet.title }}
            </h3>
            <p v-if="booklet.subtitle" class="text-xs text-gray-500 dark:text-gray-400 mt-1 truncate">
              {{ booklet.subtitle }}
            </p>
            <p v-if="booklet.description" class="text-xs text-gray-600 dark:text-gray-300 mt-2 line-clamp-2">
              {{ booklet.description }}
            </p>
          </div>
          <div class="flex flex-col items-end gap-2">
            <span :class="['inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium', statusClass(booklet.status)]">
              {{ t(`booklets.status.${booklet.status}`) }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <p v-if="!loading && total > 0" class="mt-4 text-xs text-gray-500 dark:text-gray-400">
      {{ t('booklets.count', { count: total }) }}
    </p>
  </div>

  <div
    v-if="showCreateModal"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
    @click.self="closeCreateModal"
  >
    <div class="w-full max-w-lg bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700">
      <div class="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white">
          {{ t('booklets.createTitle') }}
        </h3>
      </div>
      <form class="px-6 py-4 space-y-4" @submit.prevent="submitCreate">
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {{ t('booklets.fields.title') }}
          </label>
          <input
            v-model="form.title"
            type="text"
            class="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            :placeholder="t('booklets.placeholders.title')"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {{ t('booklets.fields.subtitle') }}
          </label>
          <input
            v-model="form.subtitle"
            type="text"
            class="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            :placeholder="t('booklets.placeholders.subtitle')"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {{ t('booklets.fields.description') }}
          </label>
          <textarea
            v-model="form.description"
            rows="3"
            class="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            :placeholder="t('booklets.placeholders.description')"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {{ t('booklets.fields.templateData') }}
          </label>
          <div class="grid grid-cols-2 gap-2 rounded-md border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700/30 p-3">
            <label
              v-for="fieldKey in templateFieldOptions"
              :key="fieldKey"
              class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300"
            >
              <input
                v-model="form.template_data"
                type="checkbox"
                :value="fieldKey"
                class="rounded border-gray-300 dark:border-gray-600"
              />
              {{ t(`booklets.templateFields.${fieldKey}`) }}
            </label>
          </div>
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <button
            type="button"
            class="px-4 py-2 text-sm rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
            @click="closeCreateModal"
          >
            {{ t('booklets.actions.cancel') }}
          </button>
          <button
            type="submit"
            :disabled="!canSubmit"
            class="px-4 py-2 text-sm rounded-md bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {{ saving ? t('booklets.actions.creating') : t('booklets.actions.create') }}
          </button>
        </div>
      </form>
    </div>
  </div>

</template>

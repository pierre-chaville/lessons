<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { auditApi } from '@/api/audit'
import { usersApi, type ClerkUser } from '@/api/users'
import { lessonsApi } from '@/api/lessons'
import type { AuditLogRow } from '@/api/types'

const rows = ref<AuditLogRow[]>([])
const users = ref<ClerkUser[]>([])
const lessonsById = ref<Record<number, { hashid: string; title: string }>>({})
const loading = ref(false)
const error = ref<string | null>(null)
const expanded = ref<Set<number>>(new Set())

const actorFilter = ref('')
const actionFilter = ref('')
const fromDate = ref('')
const toDate = ref('')
const limit = ref(100)
const { t } = useI18n()

const actorName = (id: string | null) => {
  if (!id) return t('audit.system')
  const u = users.value.find((x) => x.id === id)
  if (!u) return id
  return [u.first_name, u.last_name].filter(Boolean).join(' ') || u.username || u.email || id
}

const entityLabel = (row: AuditLogRow) => {
  if (row.entity_type === 'lesson') {
    const lessonId = Number(row.entity_id)
    if (!Number.isNaN(lessonId) && lessonsById.value[lessonId]) {
      const lesson = lessonsById.value[lessonId]
      return `${lesson.title} (${lesson.hashid})`
    }
  }
  return `${row.entity_type}:${row.entity_id}`
}

const actionLabel = (action: string) => {
  const key = `audit.actions.${action.replace(/\./g, '_')}`
  const translated = t(key)
  return translated === key ? action : translated
}

const fetchRows = async () => {
  loading.value = true
  error.value = null
  try {
    rows.value = await auditApi.query({
      actor_id: actorFilter.value || undefined,
      action: actionFilter.value || undefined,
      occurred_after: fromDate.value ? new Date(fromDate.value).toISOString() : undefined,
      occurred_before: toDate.value ? new Date(toDate.value).toISOString() : undefined,
      limit: limit.value,
    })
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('audit.loadFailed')
  } finally {
    loading.value = false
  }
}

const prettyPayload = (payload: Record<string, unknown>) => JSON.stringify(payload, null, 2)

const toggleExpanded = (id: number) => {
  if (expanded.value.has(id)) expanded.value.delete(id)
  else expanded.value.add(id)
}

const displayedRows = computed(() => rows.value)

onMounted(async () => {
  try {
    users.value = await usersApi.list()
  } catch {
    users.value = []
  }
  try {
    const lessons = await lessonsApi.list()
    lessonsById.value = lessons.reduce<Record<number, { hashid: string; title: string }>>((acc, lesson) => {
      acc[lesson.id] = { hashid: lesson.hashid, title: lesson.title }
      return acc
    }, {})
  } catch {
    lessonsById.value = {}
  }
  await fetchRows()
})
</script>

<template>
  <div class="space-y-4">
    <div class="rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800">
      <h2 class="mb-3 text-xl font-semibold text-gray-900 dark:text-white">{{ t('audit.title') }}</h2>
      <div class="grid grid-cols-1 gap-3 md:grid-cols-5">
        <input
          v-model="actorFilter"
          type="text"
          :placeholder="t('audit.actorIdPlaceholder')"
          class="rounded-md border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
        />
        <input
          v-model="actionFilter"
          type="text"
          :placeholder="t('audit.actionPrefixPlaceholder')"
          class="rounded-md border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
        />
        <input
          v-model="fromDate"
          type="date"
          class="rounded-md border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
        />
        <input
          v-model="toDate"
          type="date"
          class="rounded-md border border-gray-300 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100"
        />
        <div class="flex gap-2">
          <button
            @click="fetchRows"
            class="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            {{ t('audit.apply') }}
          </button>
        </div>
      </div>
    </div>

    <div class="rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800">
      <p v-if="error" class="mb-2 text-sm text-red-600 dark:text-red-400">{{ error }}</p>
      <p v-if="loading" class="text-sm text-gray-500 dark:text-gray-400">{{ t('audit.loading') }}</p>

      <div v-else class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead class="bg-gray-50 dark:bg-gray-900">
            <tr>
              <th class="px-3 py-2 text-left text-xs text-gray-500 dark:text-gray-400">{{ t('audit.timestamp') }}</th>
              <th class="px-3 py-2 text-left text-xs text-gray-500 dark:text-gray-400">{{ t('audit.actor') }}</th>
              <th class="px-3 py-2 text-left text-xs text-gray-500 dark:text-gray-400">{{ t('audit.action') }}</th>
              <th class="px-3 py-2 text-left text-xs text-gray-500 dark:text-gray-400">{{ t('audit.entity') }}</th>
              <th class="px-3 py-2 text-left text-xs text-gray-500 dark:text-gray-400">{{ t('audit.payload') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
            <tr v-for="row in displayedRows" :key="row.id">
              <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">
                {{ new Date(row.occurred_at).toLocaleString() }}
              </td>
              <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">
                {{ actorName(row.actor_id) }} ({{ row.actor_role }})
              </td>
              <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">{{ actionLabel(row.action) }}</td>
              <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">
                {{ entityLabel(row) }}
              </td>
              <td class="px-3 py-2 text-xs">
                <button
                  @click="toggleExpanded(row.id)"
                  class="rounded border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
                >
                  {{ expanded.has(row.id) ? t('audit.hideJson') : t('audit.showJson') }}
                </button>
                <pre
                  v-if="expanded.has(row.id)"
                  class="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-2 text-xs text-gray-800 dark:bg-gray-900 dark:text-gray-200"
                >{{ prettyPayload(row.payload) }}</pre>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>


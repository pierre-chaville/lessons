<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowPathIcon } from '@heroicons/vue/24/outline'
import { lessonsApi } from '@/api/lessons'
import { usersApi, type ClerkUser } from '@/api/users'
import type { LessonListItem } from '@/api/types'
import { formatApiDateTime } from '@/utils/dateTime'

const { t } = useI18n()

const lessons = ref<LessonListItem[]>([])
const users = ref<ClerkUser[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const restoringHashid = ref<string | null>(null)

const userNameById = computed(() => {
  const byId: Record<string, string> = {}
  for (const user of users.value) {
    byId[user.id] =
      [user.first_name, user.last_name].filter(Boolean).join(' ')
      || user.username
      || user.email
      || user.id
  }
  return byId
})

const deletedByLabel = (userId: string | null | undefined): string => {
  if (!userId) return t('audit.system')
  return userNameById.value[userId] || userId
}

const loadDeletedLessons = async () => {
  loading.value = true
  error.value = null
  try {
    lessons.value = await lessonsApi.listDeleted()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('admin.loadDeletedFailed')
  } finally {
    loading.value = false
  }
}

const restoreLesson = async (lesson: LessonListItem) => {
  if (!window.confirm(t('admin.restoreConfirm', { title: lesson.title }))) return
  restoringHashid.value = lesson.hashid
  error.value = null
  try {
    await lessonsApi.restore(lesson.hashid)
    lessons.value = lessons.value.filter((row) => row.hashid !== lesson.hashid)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('admin.restoreFailed')
  } finally {
    restoringHashid.value = null
  }
}

onMounted(async () => {
  try {
    users.value = await usersApi.list()
  } catch {
    users.value = []
  }
  await loadDeletedLessons()
})
</script>

<template>
  <div class="space-y-4">
    <div class="rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 class="text-xl font-semibold text-gray-900 dark:text-white">{{ t('admin.title') }}</h2>
          <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">{{ t('admin.description') }}</p>
        </div>
        <button
          @click="loadDeletedLessons"
          :disabled="loading"
          class="inline-flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600"
        >
          <ArrowPathIcon class="h-4 w-4" />
          {{ t('admin.refresh') }}
        </button>
      </div>
    </div>

    <div class="rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800">
      <p v-if="error" class="mb-3 text-sm text-red-600 dark:text-red-400">{{ error }}</p>
      <p v-if="loading" class="text-sm text-gray-500 dark:text-gray-400">{{ t('admin.loadingDeleted') }}</p>

      <div v-else-if="lessons.length === 0" class="rounded-lg border border-dashed border-gray-300 p-8 text-center dark:border-gray-600">
        <p class="text-sm text-gray-500 dark:text-gray-400">{{ t('admin.noDeletedLessons') }}</p>
      </div>

      <div v-else class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead class="bg-gray-50 dark:bg-gray-900">
            <tr>
              <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">{{ t('lessons.lessonTitle') }}</th>
              <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">{{ t('lessons.course') }}</th>
              <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">{{ t('admin.deletedAt') }}</th>
              <th class="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">{{ t('admin.deletedBy') }}</th>
              <th class="px-3 py-2 text-right text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">{{ t('admin.actions') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
            <tr v-for="lesson in lessons" :key="lesson.hashid">
              <td class="px-3 py-3 text-sm font-medium text-gray-900 dark:text-white">
                {{ lesson.title }}
              </td>
              <td class="px-3 py-3 text-sm text-gray-600 dark:text-gray-300">
                {{ lesson.course?.name || t('lessons.noCourse') }}
              </td>
              <td class="px-3 py-3 text-sm text-gray-600 dark:text-gray-300">
                {{ formatApiDateTime(lesson.deleted_at) }}
              </td>
              <td class="px-3 py-3 text-sm text-gray-600 dark:text-gray-300">
                {{ deletedByLabel(lesson.deleted_by) }}
              </td>
              <td class="px-3 py-3 text-right">
                <button
                  @click="restoreLesson(lesson)"
                  :disabled="restoringHashid === lesson.hashid"
                  class="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60"
                >
                  {{ restoringHashid === lesson.hashid ? t('admin.restoring') : t('admin.restore') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

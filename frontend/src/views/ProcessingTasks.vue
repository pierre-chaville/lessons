<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ClockIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  PlayIcon,
  TrashIcon,
  DocumentTextIcon,
  BookOpenIcon,
  ChatBubbleBottomCenterTextIcon,
  SparklesIcon,
} from '@heroicons/vue/24/outline'
import { Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot } from '@headlessui/vue'
import { lessonsApi } from '@/api/lessons'
import { tasksApi } from '@/api/tasks'
import { usersApi, type ClerkUser } from '@/api/users'
import { useAuth } from '@/composables/useAuth'
import { useToast } from '@/composables/useToast'
import { usePermissions } from '@/composables/usePermissions'
import { formatApiDateTime, parseApiDateTime } from '@/utils/dateTime'
import type { LessonListItem, Task, TaskStatus, TaskType } from '@/api/types'

const { t } = useI18n()
const toast = useToast()
const { can } = usePermissions()
const { user } = useAuth()

const tasks = ref<Task[]>([])
const lessons = ref<LessonListItem[]>([])
const users = ref<ClerkUser[]>([])
const loading = ref(false)
const loadingLessons = ref(false)
const selectedOwnerFilter = ref<'mine' | 'all'>('mine')
const selectedLessonId = ref<string>('all')
const selectedCreatedRange = ref<'today' | 'last7' | 'last30' | 'all'>('today')
const showDeleteModal = ref(false)
const taskToDelete = ref<Task | null>(null)
const isDeleting = ref(false)

let refreshInterval: ReturnType<typeof setInterval> | null = null

const fetchTasks = async () => {
  try {
    loading.value = true
    tasks.value = await tasksApi.list()
  } catch {
    // silent — no toast on background refresh
  } finally {
    loading.value = false
  }
}

const fetchLessons = async () => {
  try {
    loadingLessons.value = true
    lessons.value = await lessonsApi.list()
  } catch {
    lessons.value = []
  } finally {
    loadingLessons.value = false
  }
}

const fetchUsers = async () => {
  try {
    users.value = await usersApi.list()
  } catch {
    // Editors may not have access to /users; fallback to raw IDs in UI.
    users.value = []
  }
}

const sortedLessons = computed(() =>
  [...lessons.value].sort((a, b) => a.title.localeCompare(b.title)),
)
const currentUserId = computed(() => user.value?.id ?? null)

const getTaskLessonId = (task: Task): number | null => {
  const rawLessonId = task.parameters?.lesson_id
  if (typeof rawLessonId === 'number' && Number.isFinite(rawLessonId)) return rawLessonId
  if (typeof rawLessonId === 'string') {
    const parsed = Number(rawLessonId)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

const getLessonLabel = (task: Task): string => {
  const lessonId = getTaskLessonId(task)
  if (lessonId === null) return '-'
  const lesson = lessons.value.find((item) => item.id === lessonId)
  return lesson ? lesson.title : '-'
}

const getLessonHashid = (task: Task): string | null => {
  const lessonId = getTaskLessonId(task)
  if (lessonId === null) return null
  const lesson = lessons.value.find((item) => item.id === lessonId)
  return lesson?.hashid ?? null
}

const getLauncherLabel = (task: Task): string => {
  if (!task.created_by_id) return '-'
  const user = users.value.find((u) => u.id === task.created_by_id)
  if (!user) return task.created_by_id
  const fullName = [user.first_name, user.last_name].filter(Boolean).join(' ').trim()
  return fullName || user.email || task.created_by_id
}

const matchesCreatedRange = (task: Task): boolean => {
  if (selectedCreatedRange.value === 'all') return true

  const createdAt = parseApiDateTime(task.created_at)
  if (!createdAt) return false

  if (selectedCreatedRange.value === 'today') {
    const startOfToday = new Date()
    startOfToday.setHours(0, 0, 0, 0)
    return createdAt >= startOfToday
  }

  const now = new Date()
  const days = selectedCreatedRange.value === 'last7' ? 7 : 30
  const threshold = new Date(now.getTime() - days * 24 * 60 * 60 * 1000)
  return createdAt >= threshold
}

const filteredTasks = computed(() => {
  return tasks.value.filter((task) => {
    if (selectedOwnerFilter.value === 'mine') {
      if (!currentUserId.value) return false
      if (task.created_by_id !== currentUserId.value) return false
    }
    if (!matchesCreatedRange(task)) return false
    if (selectedLessonId.value === 'all') return true
    const lessonId = Number(selectedLessonId.value)
    if (!Number.isFinite(lessonId)) return true
    return getTaskLessonId(task) === lessonId
  })
})

const openDeleteModal = (task: Task) => {
  taskToDelete.value = task
  showDeleteModal.value = true
}

const closeDeleteModal = () => {
  showDeleteModal.value = false
  taskToDelete.value = null
}

const confirmDelete = async () => {
  if (!taskToDelete.value) return
  try {
    isDeleting.value = true
    await tasksApi.delete(taskToDelete.value.id)
    await fetchTasks()
    closeDeleteModal()
  } catch {
    toast.error(t('processing.deleteFailed'))
  } finally {
    isDeleting.value = false
  }
}

const formatDate = (dateString: string | null | undefined): string => {
  return formatApiDateTime(dateString)
}

const formatDuration = (seconds: number | null | undefined): string => {
  if (!seconds) return '-'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)
  if (hours > 0) return `${hours}h ${minutes}m ${secs}s`
  if (minutes > 0) return `${minutes}m ${secs}s`
  return `${secs}s`
}

const getTaskResultObject = (task: Task): Record<string, unknown> | null => {
  if (!task.result || typeof task.result !== 'object') return null
  return task.result as Record<string, unknown>
}

const getTokenUsageObject = (task: Task): Record<string, unknown> | null => {
  const result = getTaskResultObject(task)
  if (!result) return null
  const tokenUsage = result.token_usage
  if (!tokenUsage || typeof tokenUsage !== 'object') return null
  return tokenUsage as Record<string, unknown>
}

const getTokenCount = (task: Task, key: 'input_tokens' | 'output_tokens'): number | null => {
  const tokenUsage = getTokenUsageObject(task)
  if (!tokenUsage) return null
  const value = tokenUsage[key]
  const parsed = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(parsed)) return null
  return parsed
}

const formatInteger = (value: number | null): string => {
  if (value === null) return '-'
  return value.toLocaleString()
}

const getEstimatedCost = (task: Task): number | null => {
  const result = getTaskResultObject(task)
  if (!result) return null
  const raw = result.estimated_cost_usd
  const parsed = typeof raw === 'number' ? raw : Number(raw)
  if (!Number.isFinite(parsed)) return null
  return parsed
}

const formatEstimatedCost = (task: Task): string => {
  const cost = getEstimatedCost(task)
  if (cost === null) return '-'
  return `$${new Intl.NumberFormat(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 3,
  }).format(cost)}`
}

const getStatusColor = (status: TaskStatus): string => {
  switch (status) {
    case 'completed': return 'text-green-600 dark:text-green-400 bg-green-100 dark:bg-green-900/30'
    case 'running':   return 'text-blue-600 dark:text-blue-400 bg-blue-100 dark:bg-blue-900/30'
    case 'failed':    return 'text-red-600 dark:text-red-400 bg-red-100 dark:bg-red-900/30'
    default:          return 'text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-700'
  }
}

const getStatusIcon = (status: TaskStatus) => {
  switch (status) {
    case 'completed': return CheckCircleIcon
    case 'running':   return PlayIcon
    case 'failed':    return ExclamationCircleIcon
    default:          return ClockIcon
  }
}

const getTaskTypeIcon = (taskType: TaskType) => {
  switch (taskType) {
    case 'correction': return ChatBubbleBottomCenterTextIcon
    case 'sources':    return BookOpenIcon
    case 'summary':    return SparklesIcon
    case 'brief':      return SparklesIcon
    default:           return DocumentTextIcon
  }
}

const canDelete = (task: Task): boolean => task.status !== 'running'

onMounted(() => {
  fetchLessons()
  fetchUsers()
  fetchTasks()
  refreshInterval = setInterval(fetchTasks, 5000)
})

onBeforeUnmount(() => {
  if (refreshInterval !== null) clearInterval(refreshInterval)
})
</script>

<template>
  <!-- Access guard: tasks are only visible to publisher/admin -->
  <div v-if="!can('tasks', 'read')" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center transition-colors">
    <p class="text-gray-500 dark:text-gray-400">{{ t('auth.noAccessDesc') }}</p>
  </div>

  <div v-else class="w-full">
    <!-- Delete Confirmation Modal -->
    <TransitionRoot appear :show="showDeleteModal" as="template">
      <Dialog as="div" @close="closeDeleteModal" class="relative z-50">
        <TransitionChild
          as="template"
          enter="duration-300 ease-out"
          enter-from="opacity-0"
          enter-to="opacity-100"
          leave="duration-200 ease-in"
          leave-from="opacity-100"
          leave-to="opacity-0"
        >
          <div class="fixed inset-0 bg-black/25 dark:bg-black/50" />
        </TransitionChild>

        <div class="fixed inset-0 overflow-y-auto">
          <div class="flex min-h-full items-center justify-center p-4 text-center">
            <TransitionChild
              as="template"
              enter="duration-300 ease-out"
              enter-from="opacity-0 scale-95"
              enter-to="opacity-100 scale-100"
              leave="duration-200 ease-in"
              leave-from="opacity-100 scale-100"
              leave-to="opacity-0 scale-95"
            >
              <DialogPanel class="w-full max-w-md transform overflow-hidden rounded-2xl bg-white dark:bg-gray-800 p-6 text-left align-middle shadow-xl transition-all">
                <DialogTitle as="h3" class="text-lg font-medium leading-6 text-gray-900 dark:text-white">
                  {{ t('processing.deleteConfirmTitle') }}
                </DialogTitle>
                <div class="mt-2">
                  <p class="text-sm text-gray-500 dark:text-gray-400">
                    {{ t('processing.deleteConfirmMessage') }}
                  </p>
                </div>

                <div class="mt-4 flex gap-3 justify-end">
                  <button
                    type="button"
                    class="inline-flex justify-center rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
                    @click="closeDeleteModal"
                    :disabled="isDeleting"
                  >
                    {{ t('processing.cancel') }}
                  </button>
                  <button
                    type="button"
                    class="inline-flex justify-center rounded-md border border-transparent bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
                    @click="confirmDelete"
                    :disabled="isDeleting"
                  >
                    {{ isDeleting ? t('processing.deleting') : t('processing.delete') }}
                  </button>
                </div>
              </DialogPanel>
            </TransitionChild>
          </div>
        </div>
      </Dialog>
    </TransitionRoot>

    <!-- Info Section -->
    <div class="mb-6 bg-white dark:bg-gray-800 shadow-sm rounded-lg p-4 transition-colors w-full">
      <div class="flex items-center gap-2">
        <ClockIcon class="h-5 w-5 text-gray-500 dark:text-gray-400" />
        <span class="text-sm font-medium text-gray-700 dark:text-gray-300">
          {{ filteredTasks.length }} {{ filteredTasks.length === 1 ? t('processing.task') : t('processing.tasks') }}
        </span>
      </div>
      <div class="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3 max-w-5xl">
        <div>
          <label for="owner-filter" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {{ t('processing.filterByOwner') }}
          </label>
          <select
            id="owner-filter"
            v-model="selectedOwnerFilter"
            class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="mine">{{ t('processing.myTasks') }}</option>
            <option value="all">{{ t('processing.allTasks') }}</option>
          </select>
        </div>
        <div>
          <label for="lesson-filter" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {{ t('processing.filterByLesson') }}
          </label>
          <select
            id="lesson-filter"
            v-model="selectedLessonId"
            :disabled="loadingLessons"
            class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="all">{{ t('processing.allLessons') }}</option>
            <option
              v-for="lesson in sortedLessons"
              :key="lesson.id"
              :value="String(lesson.id)"
            >
              {{ lesson.id }} - {{ lesson.title }}
            </option>
          </select>
        </div>
        <div>
          <label for="created-filter" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {{ t('processing.filterByCreated') }}
          </label>
          <select
            id="created-filter"
            v-model="selectedCreatedRange"
            class="w-full rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="today">{{ t('processing.createdRanges.today') }}</option>
            <option value="last7">{{ t('processing.createdRanges.last7Days') }}</option>
            <option value="last30">{{ t('processing.createdRanges.last30Days') }}</option>
            <option value="all">{{ t('processing.createdRanges.noLimit') }}</option>
          </select>
        </div>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading && tasks.length === 0" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center text-gray-500 dark:text-gray-400 transition-colors">
      {{ t('processing.loading') }}
    </div>

    <!-- Empty State -->
    <div v-else-if="filteredTasks.length === 0" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center text-gray-500 dark:text-gray-400 transition-colors">
      {{ t('processing.noTasks') }}
    </div>

    <!-- Tasks Table -->
    <div v-else class="bg-white dark:bg-gray-800 shadow-sm rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden min-w-0">
      <div class="overflow-x-auto">
        <table class="w-full table-fixed divide-y divide-gray-200 dark:divide-gray-700">
          <colgroup>
            <col class="w-14" />
            <col class="w-24" />
            <col class="w-24" />
            <col class="w-32" />
            <col class="w-16" />
            <col />
            <col class="w-32" />
            <col class="w-20" />
            <col class="w-20" />
            <col class="w-20" />
            <col class="w-24" />
            <col class="w-14" />
          </colgroup>
          <thead class="bg-gray-50 dark:bg-gray-900/50">
            <tr>
              <th class="px-2 py-3 text-left text-xs font-medium leading-tight text-gray-500 dark:text-gray-400">
                {{ t('processing.taskId') }}
              </th>
              <th class="px-2 py-3 text-left text-xs font-medium leading-tight text-gray-500 dark:text-gray-400">
                {{ t('processing.taskType') }}
              </th>
              <th class="px-2 py-3 text-left text-xs font-medium leading-tight text-gray-500 dark:text-gray-400">
                {{ t('processing.status') }}
              </th>
              <th class="px-2 py-3 text-left text-xs font-medium leading-tight text-gray-500 dark:text-gray-400">
                {{ t('processing.launchedBy') }}
              </th>
              <th class="px-2 py-3 text-left text-xs font-medium leading-tight text-gray-500 dark:text-gray-400">
                {{ t('processing.lessonId') }}
              </th>
              <th class="px-2 py-3 text-left text-xs font-medium leading-tight text-gray-500 dark:text-gray-400">
                {{ t('processing.lessonLabel') }}
              </th>
              <th class="px-2 py-3 text-left text-xs font-medium leading-tight text-gray-500 dark:text-gray-400">
                {{ t('processing.started') }}
              </th>
              <th class="px-2 py-3 text-left text-xs font-medium leading-tight text-gray-500 dark:text-gray-400">
                {{ t('processing.duration') }}
              </th>
              <th class="px-2 py-3 text-right text-xs font-medium leading-tight text-gray-500 dark:text-gray-400">
                {{ t('processing.inputTokens') }}
              </th>
              <th class="px-2 py-3 text-right text-xs font-medium leading-tight text-gray-500 dark:text-gray-400">
                {{ t('processing.outputTokens') }}
              </th>
              <th class="px-2 py-3 text-right text-xs font-medium leading-tight text-gray-500 dark:text-gray-400">
                {{ t('processing.estimatedCost') }}
              </th>
              <th class="px-2 py-3 text-right text-xs font-medium leading-tight text-gray-500 dark:text-gray-400">
                {{ t('processing.actions') }}
              </th>
            </tr>
          </thead>
          <tbody class="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
            <template v-for="task in filteredTasks" :key="task.id">
              <tr class="hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                <td class="px-2 py-3 text-sm text-gray-900 dark:text-white font-medium truncate">
                  {{ task.id }}
                </td>
                <td class="px-2 py-3 text-sm text-gray-700 dark:text-gray-300">
                  <div class="flex min-w-0 items-center gap-2">
                    <component
                      :is="getTaskTypeIcon(task.task_type)"
                      class="h-4 w-4 text-indigo-600 dark:text-indigo-400 flex-shrink-0"
                    />
                    <span class="truncate">{{ t(`processing.taskTypes.${task.task_type}`) }}</span>
                  </div>
                </td>
                <td class="px-2 py-3 text-sm">
                  <span
                    :class="[
                      'inline-flex max-w-full items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium',
                      getStatusColor(task.status),
                    ]"
                  >
                    <component :is="getStatusIcon(task.status)" class="h-4 w-4 flex-shrink-0" />
                    <span class="truncate">{{ t(`processing.statuses.${task.status}`) }}</span>
                  </span>
                </td>
                <td class="px-2 py-3 text-sm text-gray-700 dark:text-gray-300 truncate" :title="getLauncherLabel(task)">
                  {{ getLauncherLabel(task) }}
                </td>
                <td class="px-2 py-3 text-sm text-gray-700 dark:text-gray-300 truncate">
                  {{ getTaskLessonId(task) ?? '-' }}
                </td>
                <td class="px-2 py-3 text-sm text-gray-700 dark:text-gray-300 min-w-0">
                  <a
                    v-if="getLessonHashid(task)"
                    :href="`/lessons/${getLessonHashid(task)}`"
                    class="truncate block text-indigo-600 dark:text-indigo-400 hover:underline"
                    :title="getLessonLabel(task)"
                  >
                    {{ getLessonLabel(task) }}
                  </a>
                  <span v-else class="truncate block" :title="getLessonLabel(task)">
                    {{ getLessonLabel(task) }}
                  </span>
                </td>
                <td class="px-2 py-3 text-sm text-gray-700 dark:text-gray-300 truncate" :title="formatDate(task.start_date)">
                  {{ formatDate(task.start_date) }}
                </td>
                <td class="px-2 py-3 text-sm text-gray-700 dark:text-gray-300 truncate">
                  {{ formatDuration(task.duration) }}
                </td>
                <td class="px-2 py-3 text-sm text-right text-gray-700 dark:text-gray-300 truncate">
                  {{ formatInteger(getTokenCount(task, 'input_tokens')) }}
                </td>
                <td class="px-2 py-3 text-sm text-right text-gray-700 dark:text-gray-300 truncate">
                  {{ formatInteger(getTokenCount(task, 'output_tokens')) }}
                </td>
                <td class="px-2 py-3 text-sm text-right text-gray-700 dark:text-gray-300 truncate">
                  {{ formatEstimatedCost(task) }}
                </td>
                <td class="px-2 py-3 text-right">
                  <button
                    v-if="can('tasks', 'cancel') && canDelete(task)"
                    @click="openDeleteModal(task)"
                    class="p-2 text-gray-400 hover:text-red-600 dark:hover:text-red-400 transition-colors"
                    :title="t('processing.delete')"
                  >
                    <TrashIcon class="h-5 w-5" />
                  </button>
                  <span v-else class="text-gray-400 dark:text-gray-500">-</span>
                </td>
              </tr>
              <tr v-if="task.status === 'failed' && task.error" class="bg-red-50/60 dark:bg-red-900/10">
                <td colspan="12" class="px-4 py-3 text-sm text-red-800 dark:text-red-300">
                  <span class="font-medium">{{ t('processing.error') }}:</span>
                  <span class="ml-2 break-words">{{ task.error }}</span>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>


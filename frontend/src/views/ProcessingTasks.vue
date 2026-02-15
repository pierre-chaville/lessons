<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
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
import { tasksApi } from '@/api/tasks'
import { useToast } from '@/composables/useToast'
import { usePermissions } from '@/composables/usePermissions'
import type { Task, TaskStatus, TaskType } from '@/api/types'

const { t } = useI18n()
const toast = useToast()
const { can } = usePermissions()

const tasks = ref<Task[]>([])
const loading = ref(false)
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
  if (!dateString) return '-'
  return new Date(dateString).toLocaleString()
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
    default:           return DocumentTextIcon
  }
}

const canDelete = (task: Task): boolean => task.status !== 'running'

onMounted(() => {
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
          {{ tasks.length }} {{ tasks.length === 1 ? t('processing.task') : t('processing.tasks') }}
        </span>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading && tasks.length === 0" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center text-gray-500 dark:text-gray-400 transition-colors">
      {{ t('processing.loading') }}
    </div>

    <!-- Empty State -->
    <div v-else-if="tasks.length === 0" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center text-gray-500 dark:text-gray-400 transition-colors">
      {{ t('processing.noTasks') }}
    </div>

    <!-- Tasks List -->
    <div v-else class="space-y-4">
      <div
        v-for="task in tasks"
        :key="task.id"
        class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-6 transition-all border border-gray-200 dark:border-gray-700"
      >
        <div class="flex items-start justify-between">
          <div class="flex-1">
            <!-- Header: Task Type and Status -->
            <div class="flex items-center gap-3 mb-3">
              <component 
                :is="getTaskTypeIcon(task.task_type)" 
                class="h-6 w-6 text-indigo-600 dark:text-indigo-400 flex-shrink-0"
              />
              <h3 class="text-lg font-semibold text-gray-900 dark:text-white">
                {{ t(`processing.taskTypes.${task.task_type}`) }}
              </h3>
              <span 
                :class="[
                  'inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium',
                  getStatusColor(task.status)
                ]"
              >
                <component :is="getStatusIcon(task.status)" class="h-4 w-4" />
                {{ t(`processing.statuses.${task.status}`) }}
              </span>
            </div>

            <!-- Task Details -->
            <div class="grid grid-cols-2 gap-4 text-sm text-gray-600 dark:text-gray-400">
              <div>
                <span class="font-medium">{{ t('processing.created') }}:</span>
                {{ formatDate(task.created_at) }}
              </div>
              <div v-if="task.start_date">
                <span class="font-medium">{{ t('processing.started') }}:</span>
                {{ formatDate(task.start_date) }}
              </div>
              <div v-if="task.end_date">
                <span class="font-medium">{{ t('processing.completed') }}:</span>
                {{ formatDate(task.end_date) }}
              </div>
              <div v-if="task.duration">
                <span class="font-medium">{{ t('processing.duration') }}:</span>
                {{ formatDuration(task.duration) }}
              </div>
            </div>

            <!-- Error Message -->
            <div v-if="task.error" class="mt-3 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md">
              <p class="text-sm text-red-800 dark:text-red-300">
                <span class="font-medium">{{ t('processing.error') }}:</span> {{ task.error }}
              </p>
            </div>

            <!-- Parameters (if any) -->
            <div v-if="task.parameters && Object.keys(task.parameters).length > 0" class="mt-3">
              <details class="text-sm">
                <summary class="cursor-pointer text-gray-700 dark:text-gray-300 font-medium">
                  {{ t('processing.parameters') }}
                </summary>
                <pre class="mt-2 p-2 bg-gray-50 dark:bg-gray-900 rounded text-xs overflow-x-auto">{{ JSON.stringify(task.parameters, null, 2) }}</pre>
              </details>
            </div>
          </div>

          <!-- Delete Button (admin only) -->
          <button
            v-if="can('tasks', 'cancel') && canDelete(task)"
            @click="openDeleteModal(task)"
            class="ml-4 p-2 text-gray-400 hover:text-red-600 dark:hover:text-red-400 transition-colors"
            :title="t('processing.delete')"
          >
            <TrashIcon class="h-5 w-5" />
          </button>
          <div v-else class="ml-4 w-9"></div>
        </div>
      </div>
    </div>
  </div>
</template>


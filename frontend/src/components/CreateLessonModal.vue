<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  XMarkIcon,
  CloudArrowUpIcon,
  CheckIcon,
  DocumentIcon,
} from '@heroicons/vue/24/outline'
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'
import { uploadApi } from '@/api/upload'
import { lessonsApi } from '@/api/lessons'
import { coursesApi } from '@/api/courses'
import { themesApi } from '@/api/themes'
import { tasksApi } from '@/api/tasks'
import { usersApi, type ClerkUser } from '@/api/users'
import { useAuth } from '@/composables/useAuth'
import { useToast } from '@/composables/useToast'
import type { Course, Theme } from '@/api/types'

const props = defineProps<{
  isOpen: boolean
  defaultCourseId?: number | null
}>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'created'): void
}>()

const { t } = useI18n()
const toast = useToast()
const { user } = useAuth()
const currentUserId = computed(() => user.value?.id ?? null)

const selectedFile = ref<File | null>(null)
const title = ref('')
const date = ref('')
const courseId = ref<number | null>(null)
const themeIds = ref<number[]>([])
const isUploading = ref(false)

const courses = ref<Course[]>([])
const themes = ref<Theme[]>([])
const users = ref<ClerkUser[]>([])
const editorIds = ref<string[]>([])
const fileInput = ref<HTMLInputElement | null>(null)

const audioDuration = ref<number | null>(null)

const getAudioDuration = (file: File): Promise<number | null> => {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file)
    const audio = new Audio(url)
    audio.addEventListener('loadedmetadata', () => {
      const duration = isFinite(audio.duration) ? audio.duration : null
      URL.revokeObjectURL(url)
      resolve(duration)
    })
    audio.addEventListener('error', () => {
      URL.revokeObjectURL(url)
      resolve(null)
    })
  })
}

const onFileSelected = (event: Event) => {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) handleFile(file)
}

const parseFilename = (filename: string) => {
  const nameWithoutExt = filename.replace(/\.[^/.]+$/, '')
  const datePattern = /[_\-](\d{8})$/
  const match = nameWithoutExt.match(datePattern)
  if (match) {
    const dateStr = match[1]
    const year = dateStr.substring(0, 4)
    const month = dateStr.substring(4, 6)
    const day = dateStr.substring(6, 8)
    date.value = `${year}-${month}-${day}`
    title.value = nameWithoutExt.substring(0, match.index).replace(/[_-]/g, ' ').trim()
  } else {
    title.value = nameWithoutExt.replace(/[_-]/g, ' ').trim()
    date.value = new Date().toISOString().slice(0, 10)
  }
}

const isDragging = ref(false)

const handleFile = async (file: File) => {
  if (!file.type.startsWith('audio/')) {
    toast.error(t('lessons.invalidAudioFile'))
    return
  }
  selectedFile.value = file
  parseFilename(file.name)
  audioDuration.value = await getAudioDuration(file)
}

const onDragOver = (event: DragEvent) => {
  event.preventDefault()
  isDragging.value = true
}

const onDragLeave = () => {
  isDragging.value = false
}

const onDrop = (event: DragEvent) => {
  event.preventDefault()
  isDragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) handleFile(file)
}

const selectFile = () => {
  fileInput.value?.click()
}

const removeFile = () => {
  selectedFile.value = null
  title.value = ''
  date.value = ''
  audioDuration.value = null
  if (fileInput.value) fileInput.value.value = ''
}

const toggleTheme = (themeId: number) => {
  const index = themeIds.value.indexOf(themeId)
  if (index === -1) {
    themeIds.value.push(themeId)
  } else {
    themeIds.value.splice(index, 1)
  }
}

const toggleEditor = (userId: string) => {
  const index = editorIds.value.indexOf(userId)
  if (index === -1) {
    editorIds.value.push(userId)
  } else {
    editorIds.value.splice(index, 1)
  }
}

const editorRoleUsers = computed(() =>
  users.value.filter((u) => {
    const role = (u.role || '').toLowerCase()
    return ['editor', 'publisher', 'admin'].includes(role) || u.id === currentUserId.value
  }),
)

const getDefaultEditorIds = (): string[] => {
  if (!currentUserId.value) return []
  const currentUserExists = users.value.some((u) => u.id === currentUserId.value)
  return currentUserExists ? [currentUserId.value] : []
}

const ensureDefaultEditorSelected = () => {
  if (!props.isOpen || editorIds.value.length > 0) return
  const defaults = getDefaultEditorIds()
  if (defaults.length > 0) editorIds.value = defaults
}

const canCreateLesson = computed(
  () =>
    !isUploading.value &&
    !!selectedFile.value &&
    !!title.value &&
    courseId.value !== null &&
    editorIds.value.length > 0,
)

const fetchCourses = async () => {
  try { courses.value = await coursesApi.list() } catch { /* silent */ }
}

const fetchThemes = async () => {
  try { themes.value = await themesApi.list() } catch { /* silent */ }
}

const fetchUsers = async () => {
  try { users.value = await usersApi.list() } catch { /* silent */ }
}

const createLesson = async () => {
  if (!selectedFile.value || !title.value) {
    toast.error(t('lessons.fillRequired'))
    return
  }
  if (courseId.value === null) {
    toast.error(t('lessons.courseRequired'))
    return
  }
  if (editorIds.value.length === 0) {
    toast.error(t('lessons.editorsRequired'))
    return
  }
  try {
    isUploading.value = true
    const { filename: uploadedFilename } = await uploadApi.audio(selectedFile.value)
    const lesson = await lessonsApi.create({
      title: title.value,
      filename: uploadedFilename,
      date: date.value ? new Date(date.value).toISOString() : new Date().toISOString(),
      course_id: courseId.value,
      duration: audioDuration.value,
      theme_ids: themeIds.value.length > 0 ? themeIds.value : null,
      editor_ids: editorIds.value.length > 0 ? editorIds.value : null,
    })
    // Automatically create a transcription task for the new lesson
    await tasksApi.create({
      task_type: 'transcription',
      parameters: { lesson_id: lesson.id },
    })
    resetForm()
    emit('created')
    emit('close')
  } catch {
    toast.error(t('lessons.createFailed'))
  } finally {
    isUploading.value = false
  }
}

const resetForm = () => {
  selectedFile.value = null
  title.value = ''
  date.value = ''
  courseId.value = props.defaultCourseId ?? null
  themeIds.value = []
  editorIds.value = getDefaultEditorIds()
  audioDuration.value = null
  if (fileInput.value) fileInput.value.value = ''
}

const close = () => {
  if (!isUploading.value) {
    resetForm()
    emit('close')
  }
}

watch(
  () => props.isOpen,
  async (isOpen) => {
    if (isOpen) {
      courseId.value = props.defaultCourseId ?? null
      await Promise.all([fetchCourses(), fetchThemes(), fetchUsers()])
      ensureDefaultEditorSelected()
    }
  },
)

watch(
  [() => user.value?.id, editorRoleUsers, () => props.isOpen],
  () => {
    ensureDefaultEditorSelected()
  },
)
</script>

<template>
  <Dialog :open="isOpen" @close="close" class="relative z-50">
    <div class="fixed inset-0 bg-black/30 backdrop-blur-sm" aria-hidden="true" />
    
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="mx-auto max-w-2xl w-full bg-white dark:bg-gray-800 rounded-lg shadow-xl">
        <!-- Header -->
        <div class="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <DialogTitle class="text-xl font-semibold text-gray-900 dark:text-white">
            {{ t('lessons.createLesson') }}
          </DialogTitle>
          <button
            @click="close"
            :disabled="isUploading"
            class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
          >
            <XMarkIcon class="h-6 w-6" />
          </button>
        </div>
        
        <!-- Content -->
        <div class="p-6 space-y-6">
          <!-- File Upload -->
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {{ t('lessons.audioFile') }} *
            </label>
            
            <input
              ref="fileInput"
              type="file"
              accept="audio/*"
              @change="onFileSelected"
              class="hidden"
            />
            
            <div v-if="!selectedFile">
              <button
                @click="selectFile"
                @dragover="onDragOver"
                @dragleave="onDragLeave"
                @drop="onDrop"
                :class="[
                  'w-full flex flex-col items-center justify-center px-6 py-8 border-2 border-dashed rounded-lg transition-colors',
                  isDragging
                    ? 'border-indigo-500 dark:border-indigo-400 bg-indigo-50 dark:bg-indigo-900/20'
                    : 'border-gray-300 dark:border-gray-600 hover:border-indigo-500 dark:hover:border-indigo-400'
                ]"
              >
                <CloudArrowUpIcon class="h-12 w-12 text-gray-400 dark:text-gray-500 mb-2" />
                <span class="text-sm text-gray-600 dark:text-gray-400">
                  {{ t('lessons.clickOrDrop') }}
                </span>
                <span class="text-xs text-gray-500 dark:text-gray-500 mt-1">
                  MP3, WAV, M4A, etc.
                </span>
              </button>
            </div>
            
            <div v-else class="flex items-center gap-3 p-4 bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700">
              <DocumentIcon class="h-8 w-8 text-indigo-600 dark:text-indigo-400" />
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium text-gray-900 dark:text-white truncate">
                  {{ selectedFile.name }}
                </p>
                <p class="text-xs text-gray-500 dark:text-gray-400">
                  {{ (selectedFile.size / 1024 / 1024).toFixed(2) }} MB
                </p>
              </div>
              <button
                @click="removeFile"
                :disabled="isUploading"
                class="text-gray-400 hover:text-red-600 dark:hover:text-red-400 transition-colors"
              >
                <XMarkIcon class="h-5 w-5" />
              </button>
            </div>
          </div>
          
          <!-- Title -->
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {{ t('lessons.lessonTitle') }} *
            </label>
            <input
              v-model="title"
              type="text"
              :disabled="isUploading"
              class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-50"
              :placeholder="t('lessons.titlePlaceholder')"
            />
          </div>
          
          <!-- Date -->
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {{ t('lessons.date') }}
            </label>
            <input
              v-model="date"
              type="date"
              :disabled="isUploading"
              class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-50"
            />
          </div>
          
          <!-- Course -->
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {{ t('lessons.course') }} *
            </label>
            <select
              v-model="courseId"
              :disabled="isUploading"
              class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-50"
            >
              <option :value="null" disabled>{{ t('lessons.selectCourse') }}</option>
              <option v-for="course in courses" :key="course.id" :value="course.id">
                {{ course.name }}
              </option>
            </select>
          </div>
          
          <!-- Themes -->
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {{ t('lessons.themes') }}
            </label>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="theme in themes"
                :key="theme.id"
                @click="toggleTheme(theme.id)"
                :disabled="isUploading"
                :class="[
                  'px-3 py-1.5 rounded-full text-sm font-medium transition-colors disabled:opacity-50',
                  themeIds.includes(theme.id)
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                ]"
              >
                {{ theme.name }}
              </button>
            </div>
          </div>

          <!-- Editors -->
          <div v-if="editorRoleUsers.length > 0">
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {{ t('lessons.editors') }} *
            </label>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="user in editorRoleUsers"
                :key="user.id"
                @click="toggleEditor(user.id)"
                :disabled="isUploading"
                :class="[
                  'px-3 py-1.5 rounded-full text-sm font-medium transition-colors disabled:opacity-50',
                  editorIds.includes(user.id)
                    ? 'bg-sky-600 text-white'
                    : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                ]"
              >
                {{ [user.first_name, user.last_name].filter(Boolean).join(' ') || user.email || user.id }}
              </button>
            </div>
          </div>
        </div>
        
        <!-- Footer -->
        <div class="flex justify-end gap-3 px-6 py-4 bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700">
          <button
            @click="close"
            :disabled="isUploading"
            class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-md transition-colors disabled:opacity-50"
          >
            {{ t('lessons.cancel') }}
          </button>
          <button
            @click="createLesson"
            :disabled="!canCreateLesson"
            class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-md transition-colors"
          >
            <CheckIcon class="h-4 w-4" />
            {{ isUploading ? t('lessons.uploading') : t('lessons.create') }}
          </button>
        </div>
      </DialogPanel>
    </div>
  </Dialog>
</template>

